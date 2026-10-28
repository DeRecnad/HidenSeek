"""GitHub: поля публичного профиля и email в ваших публичных коммитах."""
from __future__ import annotations

from .base import Fact, Module, ModuleError, ModuleResult, NewFact, RawFinding, RunContext, expect_json

API = "https://api.github.com"
PROFILE_FIELDS = ("name", "company", "blog", "location", "email", "bio", "twitter_username")


class GitHubModule(Module):
    name = "github"
    title = "GitHub API"
    input_type = "github"
    outputs = ("profile_fields", "public_email_in_commits")
    description = "Поля вашего публичного профиля и адреса, попавшие в ваши публичные коммиты."

    def _headers(self, ctx: RunContext) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if ctx.settings.github_token:
            h["Authorization"] = f"Bearer {ctx.settings.github_token}"
        return h

    async def run(self, fact: Fact, ctx: RunContext) -> ModuleResult:
        login = fact.value
        h = self._headers(ctx)
        user = expect_json(await ctx.client.get(f"{API}/users/{login}", headers=h), dict)
        if not user.get("login"):
            raise ModuleError("в ответе нет поля login", retry=False)
        res = ModuleResult()
        fields = {k: user.get(k) for k in PROFILE_FIELDS if user.get(k)}
        res.findings.append(RawFinding(
            type="profile_fields", value=f"github.com/{user['login']}", url=user.get("html_url"),
            confidence=1.0, data={"fields": fields},
        ))

        # Только коммиты, автор которых — этот (подтверждённый) аккаунт: адреса других участников не берём.
        search = expect_json(await ctx.client.get(
            f"{API}/search/commits", params={"q": f"author:{login}", "per_page": 100, "sort": "author-date"},
            headers=h,
        ), dict)
        emails: dict[str, dict] = {}
        for item in search.get("items") or []:
            author_login = ((item.get("author") or {}).get("login") or "").lower()
            if author_login != login.lower():
                continue
            commit_author = (item.get("commit") or {}).get("author") or {}
            email = (commit_author.get("email") or "").lower()
            if not email or email.endswith("@users.noreply.github.com"):
                continue
            e = emails.setdefault(email, {"count": 0, "repos": set(), "names": set(), "example": item.get("html_url")})
            e["count"] += 1
            e["repos"].add((item.get("repository") or {}).get("full_name", "?"))
            if commit_author.get("name"):
                e["names"].add(commit_author["name"])
        for email, e in emails.items():
            res.findings.append(RawFinding(
                type="public_email_in_commits", value=email, url=e["example"], confidence=1.0,
                data={"email": email, "commits": e["count"], "repos": sorted(e["repos"])[:20],
                      "author_names": sorted(e["names"])},
            ))
            # GitHub привязывает коммит к аккаунту только по подтверждённому на нём адресу.
            res.new_facts.append(NewFact("email", email, inherits=True,
                                         reason="адрес привязан к подтверждённому GitHub-аккаунту"))
        if not emails:
            res.note = "в публичных коммитах только noreply-адреса или коммитов нет"
        return res
