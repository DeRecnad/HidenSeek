"""Подтверждение владения идентификатором (раздел 4 роадмапа).

| Идентификатор | Как подтверждается                                   |
|---------------|------------------------------------------------------|
| email         | 6-значный код на почту (SMTP из .env)                |
| github        | вход через GitHub OAuth                              |
| domain        | TXT-запись hidenseek-verify=<token>                  |
| username      | наследуется от GitHub или ссылкой с подтверждённого домена |

Неподтверждённый идентификатор можно хранить в профиле, но модули он не запускает.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import smtplib
import ssl
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Awaitable, Callable, Optional
from urllib.parse import urlencode

import httpx

from ..config import Settings
from .models import Audit, Identity, IdentityType, utcnow
from .normalizer import normalize_username

CODE_TTL_SECONDS = 15 * 60
CODE_MAX_ATTEMPTS = 5
TXT_PREFIX = "hidenseek-verify="
WELL_KNOWN_PATH = "/.well-known/hidenseek.txt"


class VerificationError(Exception):
    pass


EmailSender = Callable[[str, str], None]  # (to, code)
TxtResolver = Callable[[str], Awaitable[list[str]]]
TextFetcher = Callable[[str], Awaitable[Optional[str]]]


def mark_verified(identity: Identity, method: str, parent: Optional[Identity] = None) -> None:
    identity.verified_by = method
    identity.verified_at = utcnow()
    identity.parent_id = parent.id if parent else None


def add_inherited(audit: Audit, type_: IdentityType, value: str, parent: Identity, method: str) -> Identity:
    """Добавить (или переподтвердить) идентификатор, который наследует подтверждение от parent."""
    existing = next((i for i in audit.identities if i.type == type_ and i.value.lower() == value.lower()), None)
    if existing and existing.verified_by and not existing.parent_id:
        return existing  # уже подтверждён напрямую — прямое подтверждение сильнее наследованного
    ident = existing or Identity(type=type_, value=value)
    mark_verified(ident, method, parent)
    if not existing:
        audit.identities.append(ident)
    return ident


def smtp_sender(settings: Settings) -> EmailSender:
    def send(to: str, code: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"HidenSeek: код подтверждения {code}"
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg.set_content(
            f"Ваш код подтверждения адреса для локального аудита HidenSeek: {code}\n\n"
            f"Код действует 15 минут. Если вы не запускали аудит, просто проигнорируйте письмо."
        )
        ctx = ssl.create_default_context()
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx, timeout=20) as s:
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
                s.starttls(context=ctx)
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)

    return send


async def doh_txt_resolver(name: str) -> list[str]:
    """TXT-записи через DNS-over-HTTPS (без системных зависимостей)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://dns.google/resolve", params={"name": name, "type": "TXT"})
        r.raise_for_status()
        answers = r.json().get("Answer") or []
    out = []
    for a in answers:
        if a.get("type") == 16:
            out.append("".join(part for part in a.get("data", "").split('"') if part.strip()))
    return out


async def https_fetch_text(url: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        return r.text[:20000]


@dataclass
class _PendingCode:
    digest: str
    expires: float
    attempts: int = 0


@dataclass
class Verifier:
    settings: Settings
    send_email: Optional[EmailSender] = None
    resolve_txt: TxtResolver = doh_txt_resolver
    fetch_text: TextFetcher = https_fetch_text
    _codes: dict[str, _PendingCode] = field(default_factory=dict)
    _domain_tokens: dict[str, str] = field(default_factory=dict)
    _oauth_states: dict[str, tuple[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.send_email is None and self.settings.smtp_configured:
            self.send_email = smtp_sender(self.settings)

    # ---------- email ----------
    @staticmethod
    def _digest(identity_id: str, code: str) -> str:
        return hashlib.sha256(f"{identity_id}:{code}".encode()).hexdigest()

    def start_email(self, identity: Identity) -> None:
        if identity.type != IdentityType.EMAIL:
            raise VerificationError("Это не email")
        if not self.send_email:
            raise VerificationError("SMTP не настроен: заполните SMTP_* в .env (см. .env.example)")
        code = f"{secrets.randbelow(10**6):06d}"
        self._codes[identity.id] = _PendingCode(self._digest(identity.id, code), time.time() + CODE_TTL_SECONDS)
        try:
            self.send_email(identity.value, code)
        except Exception as e:  # noqa: BLE001 — показать пользователю причину
            self._codes.pop(identity.id, None)
            raise VerificationError(f"Не удалось отправить письмо: {e}") from e

    def confirm_email(self, identity: Identity, code: str) -> None:
        pending = self._codes.get(identity.id)
        if not pending or pending.expires < time.time():
            self._codes.pop(identity.id, None)
            raise VerificationError("Код истёк или не запрашивался — отправьте новый")
        pending.attempts += 1
        if pending.attempts > CODE_MAX_ATTEMPTS:
            self._codes.pop(identity.id, None)
            raise VerificationError("Слишком много попыток — отправьте новый код")
        if not hmac.compare_digest(pending.digest, self._digest(identity.id, (code or "").strip())):
            raise VerificationError("Неверный код")
        self._codes.pop(identity.id, None)
        mark_verified(identity, "email_code")

    # ---------- domain ----------
    def domain_token(self, identity: Identity) -> str:
        if identity.type != IdentityType.DOMAIN:
            raise VerificationError("Это не домен")
        return self._domain_tokens.setdefault(identity.id, secrets.token_urlsafe(18))

    async def check_domain(self, identity: Identity) -> None:
        token = self._domain_tokens.get(identity.id)
        if not token:
            raise VerificationError("Сначала получите токен для TXT-записи")
        expected = TXT_PREFIX + token
        try:
            records = await self.resolve_txt(identity.value)
        except Exception as e:  # noqa: BLE001
            raise VerificationError(f"DNS-запрос не удался: {e}") from e
        if expected not in [r.strip() for r in records]:
            raise VerificationError(
                f"TXT-запись не найдена. Добавьте в DNS {identity.value}: {expected} (обновление DNS может занять время)"
            )
        mark_verified(identity, "dns_txt")

    # ---------- username via verified domain ----------
    async def check_username_via_domain(self, audit: Audit, identity: Identity) -> Identity:
        """Ник подтверждён, если он указан в https://<подтверждённый домен>/.well-known/hidenseek.txt."""
        if identity.type != IdentityType.USERNAME:
            raise VerificationError("Это не ник")
        ttl = self.settings.verify_ttl_days
        domains = [i for i in audit.identities if i.type == IdentityType.DOMAIN and i.is_verified(ttl)]
        if not domains:
            raise VerificationError("Нет подтверждённого домена — сначала подтвердите домен через TXT-запись")
        wanted = normalize_username(identity.value).lower()
        for d in domains:
            try:
                text = await self.fetch_text(f"https://{d.value}{WELL_KNOWN_PATH}")
            except Exception:  # noqa: BLE001
                continue
            if not text:
                continue
            names = {normalize_username(line.split("#")[0]).lower() for line in text.splitlines()}
            if wanted in names:
                mark_verified(identity, f"domain_link:{d.id}", d)
                return d
        raise VerificationError(
            f"Ник не найден в {WELL_KNOWN_PATH} подтверждённых доменов. "
            f"Положите туда файл со строкой «{identity.value}»"
        )

    # ---------- GitHub OAuth ----------
    def github_authorize_url(self, audit_id: str, redirect_uri: str) -> str:
        if not self.settings.github_oauth_configured:
            raise VerificationError("GitHub OAuth не настроен: GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET в .env")
        now = time.time()
        self._oauth_states = {k: v for k, v in self._oauth_states.items() if v[1] > now}
        state = secrets.token_urlsafe(24)
        self._oauth_states[state] = (audit_id, now + 600)
        q = urlencode({
            "client_id": self.settings.github_client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": state,
            "allow_signup": "false",
        })
        return f"https://github.com/login/oauth/authorize?{q}"

    def pop_oauth_state(self, state: str) -> str:
        entry = self._oauth_states.pop(state or "", None)
        if not entry or entry[1] < time.time():
            raise VerificationError("OAuth state недействителен или истёк — начните вход заново")
        return entry[0]

    async def github_exchange(self, code: str, redirect_uri: str) -> tuple[str, list[str]]:
        """Возвращает (login, подтверждённые на GitHub email-адреса)."""
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": self.settings.github_client_id,
                    "client_secret": self.settings.github_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            token = r.json().get("access_token")
            if not token:
                raise VerificationError("GitHub не выдал токен: " + str(r.json().get("error_description", "")))
            h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
            user = (await client.get("https://api.github.com/user", headers=h)).json()
            emails_resp = await client.get("https://api.github.com/user/emails", headers=h)
            emails = emails_resp.json() if emails_resp.status_code == 200 else []
        login = user.get("login")
        if not login:
            raise VerificationError("Не удалось получить логин GitHub")
        verified = [e["email"] for e in emails if isinstance(e, dict) and e.get("verified") and e.get("email")
                    and not e["email"].endswith("@users.noreply.github.com")]
        return login, verified


def apply_github_login(audit: Audit, login: str, verified_emails: list[str]) -> Identity:
    """GitHub-аккаунт подтверждён OAuth → ник и подтверждённые на GitHub адреса наследуют подтверждение."""
    gh = next((i for i in audit.identities if i.type == IdentityType.GITHUB and i.value.lower() == login.lower()), None)
    if not gh:
        gh = Identity(type=IdentityType.GITHUB, value=login)
        audit.identities.append(gh)
    mark_verified(gh, "github_oauth")
    add_inherited(audit, IdentityType.USERNAME, login, gh, f"inherited:{gh.id}")
    for email in verified_emails:
        add_inherited(audit, IdentityType.EMAIL, email.lower(), gh, "github_oauth_email")
    return gh
