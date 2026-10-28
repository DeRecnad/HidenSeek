import asyncio
from datetime import timedelta

import pytest

from hidenseek.core.ingest import IngestError, add_identity, remove_identity
from hidenseek.core.models import Audit, IdentityType, utcnow
from hidenseek.core.verify import TXT_PREFIX, VerificationError, Verifier, apply_github_login


def run(coro):
    return asyncio.run(coro)


def test_email_code_flow(settings):
    sent = {}
    v = Verifier(settings, send_email=lambda to, code: sent.update(to=to, code=code))
    a = Audit()
    i = add_identity(a, "email", "Me@Example.com")
    assert i.value == "me@example.com"
    v.start_email(i)
    assert sent["to"] == "me@example.com" and len(sent["code"]) == 6
    with pytest.raises(VerificationError):
        v.confirm_email(i, "000000" if sent["code"] != "000000" else "111111")
    v.confirm_email(i, sent["code"])
    assert a.is_verified(i, 90) and i.verified_by == "email_code"


def test_email_code_attempt_limit(settings):
    sent = {}
    v = Verifier(settings, send_email=lambda to, code: sent.update(code=code))
    a = Audit()
    i = add_identity(a, "email", "me@example.com")
    v.start_email(i)
    wrong = "000000" if sent["code"] != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(VerificationError):
            v.confirm_email(i, wrong)
    with pytest.raises(VerificationError, match="Слишком много"):
        v.confirm_email(i, sent["code"])
    assert not i.verified_by


def test_email_without_smtp_is_refused(settings):
    v = Verifier(settings)
    a = Audit()
    i = add_identity(a, "email", "me@example.com")
    with pytest.raises(VerificationError, match="SMTP"):
        v.start_email(i)


def test_domain_txt(settings):
    records = []

    async def resolver(name):
        return records

    v = Verifier(settings, resolve_txt=resolver)
    a = Audit()
    d = add_identity(a, "domain", "https://www.Example.com/path")
    assert d.value == "example.com"
    token = v.domain_token(d)
    with pytest.raises(VerificationError):
        run(v.check_domain(d))
    records.append(TXT_PREFIX + token)
    run(v.check_domain(d))
    assert d.verified_by == "dns_txt"


def test_username_via_verified_domain(settings):
    async def fetch(url):
        assert url == "https://example.com/.well-known/hidenseek.txt"
        return "# мои ники\npersik\n"

    v = Verifier(settings, fetch_text=fetch)
    a = Audit()
    u = add_identity(a, "username", "@persik")
    with pytest.raises(VerificationError, match="домен"):
        run(v.check_username_via_domain(a, u))
    d = add_identity(a, "domain", "example.com")
    d.verified_by, d.verified_at = "dns_txt", utcnow()
    run(v.check_username_via_domain(a, u))
    assert a.is_verified(u, 90) and u.parent_id == d.id


def test_github_login_inherits_username_and_emails():
    a = Audit()
    gh = apply_github_login(a, "octo", ["octo@example.com"])
    types = {(i.type, i.value) for i in a.identities}
    assert (IdentityType.USERNAME, "octo") in types and (IdentityType.EMAIL, "octo@example.com") in types
    assert all(a.is_verified(i, 90) for i in a.identities)
    remove_identity(a, gh.id)
    assert a.identities == []


def test_expiry_and_inheritance_chain():
    a = Audit()
    gh = apply_github_login(a, "octo", [])
    child = next(i for i in a.identities if i.type == IdentityType.USERNAME)
    gh.verified_at = utcnow() - timedelta(days=100)
    assert gh.verification_state(90) == "expired"
    assert not a.is_verified(child, 90)  # родитель истёк — наследник тоже не запускает поиск


def test_demo_verification_only_counts_in_demo_mode():
    a = Audit(mode="real")
    i = add_identity(a, "email", "me@example.com")
    i.verified_by, i.verified_at = "demo", utcnow()
    assert not a.is_verified(i, 90)


def test_unverifiable_types_rejected():
    a = Audit()
    for t in ("phone", "full_name", "city"):
        with pytest.raises(IngestError):
            add_identity(a, t, "x")
    with pytest.raises(IngestError, match="OAuth"):
        add_identity(a, "github", "octo")
