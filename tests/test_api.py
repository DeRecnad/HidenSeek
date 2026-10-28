import time

from fastapi.testclient import TestClient

from hidenseek.core.verify import Verifier
from hidenseek.webapp.app import create_app

H = {"X-HidenSeek": "1"}


def client(settings, **kw):
    return TestClient(create_app(settings, demo_delay=0.0, **kw))


def wait_done(c, aid):
    for _ in range(200):
        a = c.get(f"/api/audits/{aid}").json()
        if not a["running"]:
            return a
        time.sleep(0.02)
    raise AssertionError("audit did not finish")


def test_demo_audit_end_to_end(settings):
    with client(settings) as c:
        a = c.post("/api/audits", json={"mode": "demo", "persona": "alice"}, headers=H).json()
        c.post(f"/api/audits/{a['id']}/run", json={}, headers=H)
        a = wait_done(c, a["id"])
        rep = a["report"]
        assert rep["max_severity"] == 4
        assert rep["totals"]["review"] > 0
        assert any(i["value"] == "alisa.t@example.net" and i["state"] == "verified" for i in a["identities"])
        unverified = next(i for i in a["identities"] if i["value"] == "a.testova@work.example")
        assert not any(f["identity_id"] == unverified["id"] for f in a["findings"])
        # «не мой» убирает раскрытие
        fid = next(f["id"] for f in a["findings"] if f["status"] == "review")
        before = len([e for i in a["report"]["items"] for e in i["exposures"]])
        a = c.post(f"/api/audits/{a['id']}/findings/{fid}/review", json={"verdict": "not_mine"}, headers=H).json()
        after = len([e for i in a["report"]["items"] for e in i["exposures"]])
        assert after == before - 1


def test_csrf_header_required(settings):
    with client(settings) as c:
        assert c.post("/api/audits", json={"mode": "real"}).status_code == 403


def test_foreign_host_rejected(settings):
    with client(settings) as c:
        assert c.get("/api/config", headers={"Host": "evil.example"}).status_code == 400


def test_real_audit_cannot_run_without_verified(settings):
    with client(settings) as c:
        a = c.post("/api/audits", json={"mode": "real"}, headers=H).json()
        r = c.post(f"/api/audits/{a['id']}/identities", json={"type": "email", "value": "me@example.com"}, headers=H)
        assert r.status_code == 200
        assert c.post(f"/api/audits/{a['id']}/run", json={}, headers=H).status_code == 400
        assert c.post(f"/api/audits/{a['id']}/identities", json={"type": "phone", "value": "+79000000000"},
                      headers=H).status_code == 400


def test_email_verification_via_api(settings):
    sent = {}
    v = Verifier(settings, send_email=lambda to, code: sent.update(code=code))
    with client(settings, verifier=v) as c:
        a = c.post("/api/audits", json={"mode": "real"}, headers=H).json()
        a = c.post(f"/api/audits/{a['id']}/identities", json={"type": "email", "value": "me@example.com"}, headers=H).json()
        iid = a["identities"][0]["id"]
        assert c.post(f"/api/audits/{a['id']}/identities/{iid}/email/start", headers=H).status_code == 200
        a = c.post(f"/api/audits/{a['id']}/identities/{iid}/email/confirm", json={"code": sent["code"]}, headers=H).json()
        assert a["identities"][0]["state"] == "verified"


def test_demo_cannot_be_verified(settings):
    with client(settings) as c:
        a = c.post("/api/audits", json={"mode": "demo", "persona": "alice"}, headers=H).json()
        iid = next(i["id"] for i in a["identities"] if i["state"] == "unverified")
        assert c.post(f"/api/audits/{a['id']}/identities/{iid}/email/start", headers=H).status_code == 400


def test_save_persist_and_wipe(settings):
    with client(settings) as c:
        a = c.post("/api/audits", json={"mode": "real"}, headers=H).json()
        path = settings.data_dir / "audits" / f"{a['id']}.json"
        assert not path.exists()
        c.put(f"/api/audits/{a['id']}/save", json={"save": True}, headers=H)
        assert path.exists()
        c.put(f"/api/audits/{a['id']}/save", json={"save": False}, headers=H)
        assert not path.exists()
        c.put(f"/api/audits/{a['id']}/save", json={"save": True}, headers=H)
        c.delete("/api/data", headers=H)
        assert not path.exists() and c.get("/api/audits").json() == []


def test_export_is_json(settings):
    with client(settings) as c:
        a = c.post("/api/audits", json={"mode": "demo", "persona": "boris"}, headers=H).json()
        r = c.get(f"/api/audits/{a['id']}/export")
        assert r.status_code == 200 and r.json()["audit"]["schema_version"] == 1
