"""Сравнение аудитов, чек-лист, скрытые идентификаторы, шифрование, разбор своих страниц, отчёт, ассистент, CLI."""
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hidenseek.core import assistant as assistant_mod
from hidenseek.core import html_report, report
from hidenseek.core.crypto import make_cipher
from hidenseek.core.dispatcher import run_audit
from hidenseek.core.ingest import add_identity, remove_identity
from hidenseek.core.models import Audit, Finding, utcnow
from hidenseek.core.storage import AuditStore
from hidenseek.core.verify import VerificationError, Verifier
from hidenseek.modules.base import Fact, Module, ModuleResult, NewFact, RawFinding, RunContext
from hidenseek.modules.github_mod import GitHubModule
from hidenseek.webapp.app import create_app

H = {"X-HidenSeek": "1"}


@asynccontextmanager
async def no_client(settings):
    yield None


class Seq(Module):
    """Возвращает по очереди заданные результаты — для сравнения запусков."""

    def __init__(self, name, input_type, results):
        self.name, self.title, self.input_type, self.results = name, name, input_type, list(results)

    async def run(self, fact, ctx):
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def verified(a, t, v):
    i = add_identity(a, t, v)
    i.verified_by, i.verified_at = "email_code", utcnow()
    return i


def go(a, reg, settings, **kw):
    return asyncio.run(run_audit(a, reg, settings, client_factory=no_client, **kw))


def res(*values, data=None):
    return ModuleResult(findings=[RawFinding("registered_service", v, data=dict(data or {})) for v in values])


def test_diff_between_runs(settings):
    a = Audit()
    verified(a, "email", "me@example.com")
    mod = Seq("m", "email", [res("a.example", "b.example"), res("b.example", "c.example", data={"x": 1})])
    go(a, {"m": mod}, settings)
    assert a.history == [] and report.build(a, settings)["diff"] is None  # первый запуск не с чем сравнивать
    go(a, {"m": mod}, settings)
    d = report.build(a, settings)["diff"]
    by = {f.id: f.value for f in a.findings}
    assert [by[i] for i in d["new"]] == ["c.example"]
    assert [by[i] for i in d["gone"]] == ["a.example"]
    assert [by[i] for i in d["changed"]] == ["b.example"]
    gone = next(f for f in a.findings if f.value == "a.example")
    assert gone.gone_at and not any(e.finding_id == gone.id for e in a.exposures)


def test_failed_module_does_not_mark_gone(settings):
    class Boom(Module):
        name = title = "m"
        input_type = "email"

        async def run(self, fact, ctx):
            from hidenseek.modules.base import ModuleError
            raise ModuleError("down", retry=False)

    a = Audit()
    verified(a, "email", "me@example.com")
    go(a, {"m": Seq("m", "email", [res("a.example")])}, settings)
    go(a, {"m": Boom()}, settings)
    assert all(f.gone_at is None for f in a.findings)


def test_removed_inherited_identity_does_not_return(settings):
    a = Audit()
    verified(a, "username", "me")
    src = Seq("src", "username", [ModuleResult(new_facts=[NewFact("email", "mine@example.com", inherits=True)])])
    go(a, {"src": src}, settings)
    child = next(i for i in a.identities if i.value == "mine@example.com")
    remove_identity(a, child.id)
    go(a, {"src": src}, settings)
    assert not any(i.value == "mine@example.com" for i in a.identities)
    add_identity(a, "email", "mine@example.com")  # вручную — снова можно
    assert "email:mine@example.com" not in a.suppressed


def test_email_resend_cooldown(settings):
    v = Verifier(settings, send_email=lambda to, code: None)
    a = Audit()
    i = add_identity(a, "email", "me@example.com")
    v.start_email(i)
    with pytest.raises(VerificationError, match="повторно"):
        v.start_email(i)


def test_domain_token_lives_in_identity(settings):
    a = Audit()
    d = add_identity(a, "domain", "example.com")
    token = Verifier(settings).domain_token(d)
    assert d.verify_token == token == Verifier(settings).domain_token(d)  # «перезапуск» — тот же токен


def test_encrypted_storage(settings, tmp_path):
    cipher = make_cipher(True, tmp_path / "key")
    store = AuditStore(tmp_path, cipher)
    a = Audit(save=True)
    a.owner_profile.full_name = "Секрет Секретов"
    store.add(a)
    path = tmp_path / "audits" / f"{a.id}.json.enc"
    assert path.exists() and "Секрет".encode() not in path.read_bytes()
    assert AuditStore(tmp_path, cipher).get(a.id).owner_profile.full_name == "Секрет Секретов"
    wrong = AuditStore(tmp_path, make_cipher(True, tmp_path / "other-key"))
    assert wrong.get(a.id) is None and wrong.unreadable == [path.name]


def test_plaintext_file_is_reencrypted(settings, tmp_path):
    a = Audit(save=True)
    AuditStore(tmp_path).add(a)  # без шифрования
    assert (tmp_path / "audits" / f"{a.id}.json").exists()
    store = AuditStore(tmp_path, make_cipher(True, tmp_path / "key"))
    store.persist(store.get(a.id))
    assert not (tmp_path / "audits" / f"{a.id}.json").exists()
    assert (tmp_path / "audits" / f"{a.id}.json.enc").exists()


def wait_done(c, aid):
    for _ in range(300):
        a = c.get(f"/api/audits/{aid}").json()
        if not a["running"]:
            return a
        time.sleep(0.02)
    raise AssertionError("audit did not finish")


def demo_run(c, persona="alice"):
    a = c.post("/api/audits", json={"mode": "demo", "persona": persona}, headers=H).json()
    c.post(f"/api/audits/{a['id']}/run", json={}, headers=H)
    return wait_done(c, a["id"])


def test_mine_reads_own_page_and_finds_city_conflict(settings):
    with TestClient(create_app(settings, demo_delay=0.0)) as c:
        a = demo_run(c)
        fid = lambda v: next(f["id"] for f in a["findings"] if f["value"] == v)  # noqa: E731
        a = c.post(f"/api/audits/{a['id']}/findings/{fid('DemoDev: alice-testova-demo')}/review",
                   json={"verdict": "mine"}, headers=H).json()
        item = next(i for i in a["report"]["items"] if i["finding"]["value"] == "DemoDev: alice-testova-demo")
        assert {"real_name", "city"} <= {e["what"] for e in item["exposures"]} and item["severity"] == 3
        a = c.post(f"/api/audits/{a['id']}/findings/{fid('PhotoSite-demo: persik')}/review",
                   json={"verdict": "mine"}, headers=H).json()
        assert a["report"]["conflicts"], "Новосибирск vs Москва — оба значения с источником"


def test_resolve_checklist_and_demo_rerun_diff(settings):
    with TestClient(create_app(settings, demo_delay=0.0)) as c:
        a = demo_run(c)
        old = next(f for f in a["findings"] if f["value"] == "oldsocial.example")
        a = c.post(f"/api/audits/{a['id']}/findings/{old['id']}/resolve", json={"done": True}, headers=H).json()
        assert a["report"]["totals"]["resolved"] == 1
        c.post(f"/api/audits/{a['id']}/run", json={}, headers=H)
        a = wait_done(c, a["id"])
        d = a["report"]["diff"]
        assert old["id"] in d["gone"] and len(d["new"]) == 1
        assert "С прошлого аудита" in a["report"]["summary"]


def test_schedule_and_due_run(settings):
    with TestClient(create_app(settings, demo_delay=0.0)) as c:
        a = c.post("/api/audits", json={"mode": "real"}, headers=H).json()
        assert c.put(f"/api/audits/{a['id']}/schedule", json={"hours": 5}, headers=H).status_code == 400
        assert c.put(f"/api/audits/{a['id']}/schedule", json={"hours": 24}, headers=H).json()["schedule_hours"] == 24
        audit = c.app.state.store.get(a["id"])
        audit.created_at = utcnow() - timedelta(days=2)
        assert c.app.state.scheduler_tick() == []  # нет подтверждённых — не запускается
        demo = c.post("/api/audits", json={"mode": "demo"}, headers=H).json()
        assert c.put(f"/api/audits/{demo['id']}/schedule", json={"hours": 24}, headers=H).status_code == 400


def test_html_report_escapes(settings):
    a = Audit()
    a.findings.append(Finding(type="profile_fields", value="<script>alert(1)</script>", source="x", identity_id="i",
                              data={"fields": {"email": "x@y.zz"}}))
    from hidenseek.core import matcher
    matcher.apply(a)
    page = html_report.render(a, report.build(a, settings), 90)
    assert "<script>alert" not in page and "&lt;script&gt;" in page


def test_export_html_endpoint(settings):
    with TestClient(create_app(settings, demo_delay=0.0)) as c:
        a = demo_run(c)
        r = c.get(f"/api/audits/{a['id']}/export.html")
        assert r.status_code == 200 and "Что закрыть" in r.text and "DemoShop" in r.text


def test_assistant_masks_and_requires_consent(settings, monkeypatch):
    assert assistant_mod.mask("пишите alice.testova@example.com или +7 900 123-45-67") == \
        "пишите a***@example.com или +• ••• •••-••-67"
    with TestClient(create_app(settings, demo_delay=0.0)) as c:
        a = c.post("/api/audits", json={"mode": "real"}, headers=H).json()
        url = f"/api/audits/{a['id']}/assistant"
        assert c.post(url, json={"message": "?"}, headers=H).status_code == 400  # нет ключа
        settings.anthropic_api_key = "sk-test"
        assert c.post(url, json={"message": "?"}, headers=H).status_code == 403  # нет согласия
        seen = {}

        async def fake_ask(s, rep, question, history):
            seen["ctx"] = assistant_mod.report_context(rep)
            return "ответ"

        monkeypatch.setattr(assistant_mod, "ask", fake_ask)
        c.put(f"/api/audits/{a['id']}/assistant-consent", json={"consent": True}, headers=H)
        assert c.post(url, json={"message": "что делать?"}, headers=H).json() == {"answer": "ответ"}


def test_github_pagination(settings):
    calls = []

    def handler(req):
        if req.url.path == "/users/octo":
            return httpx.Response(200, json={"login": "octo"})
        page = int(req.url.params["page"])
        calls.append(page)
        n = 100 if page == 1 else 30
        items = [{"author": {"login": "octo"}, "commit": {"author": {"email": f"e{page}@example.com"}},
                  "repository": {"full_name": "octo/r"}}] * n
        return httpx.Response(200, json={"total_count": 130, "items": items})

    ctx = RunContext(settings=settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = asyncio.run(GitHubModule().run(Fact("github", "octo", "i"), ctx))
    assert calls == [1, 2]
    assert {f.value for f in r.findings if f.type == "public_email_in_commits"} == {"e1@example.com", "e2@example.com"}
    assert "GITHUB_TOKEN" in r.note


def test_cli_demo_shows_diff():
    from hidenseek.cli import app

    out = CliRunner().invoke(app, ["demo", "alice", "--runs", "2"], env={"COLUMNS": "200"})
    assert out.exit_code == 0, out.output
    text = " ".join(out.output.split())  # rich переносит строки
    assert "С прошлого аудита" in text and "DemoShop" in text
