"""FastAPI: JSON API + статика Ghost Terminal. Работает локально, данные не покидают машину."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import __version__
from ..config import Settings, settings as default_settings
from ..core import graph as graph_mod
from ..core import report as report_mod
from ..core import matcher
from ..core.dispatcher import run_audit
from ..core.ingest import IngestError, add_identity, remove_identity, set_profile
from ..core.models import Audit
from ..core.normalizer import phone_e164, translit, username_variants
from ..core.storage import AuditStore, export_json
from ..core.verify import TXT_PREFIX, WELL_KNOWN_PATH, VerificationError, Verifier, apply_github_login
from ..demo.personas import PERSONAS, build_demo_audit, mock_registry
from ..modules import real_registry
from ..modules.base import Module

STATIC = Path(__file__).parent / "static"


class NewAudit(BaseModel):
    mode: str = "real"
    persona: Optional[str] = None


class ProfileIn(BaseModel):
    full_name: str = ""
    city: str = ""
    phones: list[str] = []


class IdentityIn(BaseModel):
    type: str
    value: str


class CodeIn(BaseModel):
    code: str


class ReviewIn(BaseModel):
    verdict: Optional[str] = None  # mine | not_mine | None (сброс)


class ToggleIn(BaseModel):
    enabled: bool


class SaveIn(BaseModel):
    save: bool


class RunIn(BaseModel):
    module: Optional[str] = None


class NormalizeIn(BaseModel):
    value: str


def audit_view(a: Audit, settings: Settings, registry: dict[str, Module]) -> dict:
    """Всё, что нужно интерфейсу об одном аудите: идентификаторы, находки, модули, отчёт, граф."""
    ttl = settings.verify_ttl_days
    idents = []
    for i in a.identities:
        d = i.model_dump(mode="json")
        d["state"] = "verified" if a.is_verified(i, ttl) else i.verification_state(ttl)
        d["runs_modules"] = d["state"] == "verified"
        idents.append(d)
    modules = []
    for m in registry.values():
        info = m.info(settings)
        info["enabled"] = m.name not in a.disabled_modules
        st = a.sources.get(m.name)
        info["status"] = st.model_dump(mode="json") if st else None
        modules.append(info)
    data = a.model_dump(mode="json", exclude={"identities", "findings", "exposures", "sources"})
    data.update({
        "identities": idents,
        "findings": [f.model_dump(mode="json") for f in a.findings],
        "modules": modules,
        "report": report_mod.build(a, settings),
        "graph": graph_mod.build(a, settings),
        "verify_ttl_days": ttl,
    })
    return data


def config_view(settings: Settings) -> dict:
    return {
        "version": __version__,
        "smtp_configured": settings.smtp_configured,
        "github_oauth_configured": settings.github_oauth_configured,
        "hibp_configured": bool(settings.hibp_api_key),
        "verify_ttl_days": settings.verify_ttl_days,
        "personas": {k: {"title": v["title"], "description": v["description"]} for k, v in PERSONAS.items()},
        "txt_prefix": TXT_PREFIX,
        "well_known_path": WELL_KNOWN_PATH,
    }


def create_app(
    settings: Settings = default_settings,
    verifier: Optional[Verifier] = None,
    registry: Optional[dict[str, Module]] = None,
    demo_delay: float = 0.35,
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver"),
) -> FastAPI:
    app = FastAPI(title="HidenSeek", version=__version__, docs_url="/api/docs", redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    store = AuditStore(settings.data_dir)
    verifier = verifier or Verifier(settings)
    real = registry or real_registry()
    demo = mock_registry(real, demo_delay)
    tasks: dict[str, asyncio.Task] = {}
    app.state.store, app.state.verifier, app.state.tasks = store, verifier, tasks

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # Любой сайт в браузере может отправить POST на localhost; кастомный заголовок требует CORS-preflight,
        # которого мы не разрешаем, — так чужие страницы не смогут управлять аудитом.
        if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("x-hidenseek") != "1":
                return JSONResponse({"detail": "missing X-HidenSeek header"}, status_code=403)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        return resp

    def registry_for(audit: Audit) -> dict[str, Module]:
        return demo if audit.mode == "demo" else real

    def get_audit(audit_id: str) -> Audit:
        a = store.get(audit_id)
        if not a:
            raise HTTPException(404, "Аудит не найден")
        return a

    def ensure_idle(a: Audit) -> None:
        if a.running:
            raise HTTPException(409, "Аудит выполняется — дождитесь окончания")

    def touch(a: Audit) -> None:
        matcher.apply(a, settings)
        store.persist(a)

    def view(a: Audit) -> dict:
        return audit_view(a, settings, registry_for(a))

    # ---------- config / meta ----------
    @app.get("/api/config")
    def config():
        return config_view(settings)

    @app.post("/api/normalize")
    def normalize(body: NormalizeIn):
        v = body.value[:200]
        out = username_variants(v)
        if any(ch.isdigit() for ch in v) and sum(ch.isdigit() for ch in v) >= 10:
            out["Телефон (E.164)"] = phone_e164(v)
        out["Латиница для сверки имён"] = translit(v)
        return {"variants": out}

    # ---------- audits ----------
    @app.get("/api/audits")
    def list_audits():
        return [{"id": a.id, "mode": a.mode, "persona": a.persona, "created_at": a.created_at,
                 "save": a.save, "findings": len(a.findings), "name": a.owner_profile.full_name}
                for a in store.all()]

    @app.post("/api/audits")
    def create_audit(body: NewAudit):
        if body.mode == "demo":
            try:
                a = build_demo_audit(body.persona or "alice")
            except KeyError:
                raise HTTPException(400, "Нет такого персонажа")
        else:
            a = Audit(mode="real")
            a.add_log("INFO", "NEW AUDIT ....... добавьте и подтвердите свои идентификаторы")
        store.add(a)
        return view(a)

    @app.get("/api/audits/{audit_id}")
    def get_one(audit_id: str):
        return view(get_audit(audit_id))

    @app.delete("/api/audits/{audit_id}")
    def delete_audit(audit_id: str):
        a = get_audit(audit_id)
        ensure_idle(a)
        store.delete(audit_id)
        return {"ok": True}

    @app.delete("/api/data")
    def wipe():
        for t in tasks.values():
            t.cancel()
        store.wipe()
        return {"ok": True}

    @app.put("/api/audits/{audit_id}/save")
    def set_save(audit_id: str, body: SaveIn):
        a = get_audit(audit_id)
        a.save = body.save
        a.add_log("INFO", "STORAGE ....... " + ("аудит сохраняется на диск" if body.save else "только в памяти, файл удалён"))
        store.persist(a)
        return view(a)

    @app.get("/api/audits/{audit_id}/export")
    def export(audit_id: str):
        a = get_audit(audit_id)
        payload = {"audit": json.loads(export_json(a)), "report": report_mod.build(a, settings)}
        return Response(json.dumps(payload, ensure_ascii=False, indent=2, default=str), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="hidenseek_{a.id}.json"'})

    # ---------- profile / identities ----------
    @app.put("/api/audits/{audit_id}/profile")
    def put_profile(audit_id: str, body: ProfileIn):
        a = get_audit(audit_id)
        set_profile(a, body.full_name, body.city, body.phones)
        a.add_log("INFO", "PROFILE UPDATED ....... эталон для сверки (поиск не запускает)")
        touch(a)
        return view(a)

    @app.post("/api/audits/{audit_id}/identities")
    def post_identity(audit_id: str, body: IdentityIn):
        a = get_audit(audit_id)
        ensure_idle(a)
        try:
            i = add_identity(a, body.type, body.value)
        except IngestError as e:
            raise HTTPException(400, str(e))
        a.add_log("INFO", f"IDENTITY ADDED ....... {i.type.value}:{i.value} — ждёт подтверждения")
        touch(a)
        return view(a)

    @app.delete("/api/audits/{audit_id}/identities/{identity_id}")
    def delete_identity(audit_id: str, identity_id: str):
        a = get_audit(audit_id)
        ensure_idle(a)
        if not a.identity(identity_id):
            raise HTTPException(404, "Нет такого идентификатора")
        remove_identity(a, identity_id)
        a.add_log("INFO", "IDENTITY REMOVED ....... вместе с унаследованными и их находками")
        touch(a)
        return view(a)

    def real_identity(a: Audit, identity_id: str):
        if a.mode == "demo":
            raise HTTPException(400, "В учебном режиме подтверждение не выполняется — данные синтетические")
        i = a.identity(identity_id)
        if not i:
            raise HTTPException(404, "Нет такого идентификатора")
        return i

    @app.post("/api/audits/{audit_id}/identities/{identity_id}/email/start")
    def email_start(audit_id: str, identity_id: str):
        a = get_audit(audit_id)
        i = real_identity(a, identity_id)
        try:
            verifier.start_email(i)
        except VerificationError as e:
            raise HTTPException(400, str(e))
        a.add_log("INFO", f"VERIFY EMAIL ....... код отправлен на {i.value}")
        return {"ok": True}

    @app.post("/api/audits/{audit_id}/identities/{identity_id}/email/confirm")
    def email_confirm(audit_id: str, identity_id: str, body: CodeIn):
        a = get_audit(audit_id)
        i = real_identity(a, identity_id)
        try:
            verifier.confirm_email(i, body.code)
        except VerificationError as e:
            raise HTTPException(400, str(e))
        a.add_log("OK", f"VERIFIED ....... {i.value} (код из письма)")
        touch(a)
        return view(a)

    @app.post("/api/audits/{audit_id}/identities/{identity_id}/domain/token")
    def domain_token(audit_id: str, identity_id: str):
        a = get_audit(audit_id)
        i = real_identity(a, identity_id)
        try:
            token = verifier.domain_token(i)
        except VerificationError as e:
            raise HTTPException(400, str(e))
        return {"record": TXT_PREFIX + token, "host": i.value}

    @app.post("/api/audits/{audit_id}/identities/{identity_id}/domain/check")
    async def domain_check(audit_id: str, identity_id: str):
        a = get_audit(audit_id)
        i = real_identity(a, identity_id)
        try:
            await verifier.check_domain(i)
        except VerificationError as e:
            raise HTTPException(400, str(e))
        a.add_log("OK", f"VERIFIED ....... {i.value} (TXT-запись)")
        touch(a)
        return view(a)

    @app.post("/api/audits/{audit_id}/identities/{identity_id}/username/check")
    async def username_check(audit_id: str, identity_id: str):
        a = get_audit(audit_id)
        i = real_identity(a, identity_id)
        try:
            d = await verifier.check_username_via_domain(a, i)
        except VerificationError as e:
            raise HTTPException(400, str(e))
        a.add_log("OK", f"VERIFIED ....... ник {i.value} (ссылка с {d.value})")
        touch(a)
        return view(a)

    @app.get("/auth/github/start")
    def github_start(request: Request, audit_id: str):
        a = get_audit(audit_id)
        if a.mode == "demo":
            raise HTTPException(400, "В учебном режиме вход через GitHub не нужен")
        redirect_uri = str(request.url_for("github_callback"))
        try:
            url = verifier.github_authorize_url(a.id, redirect_uri)
        except VerificationError as e:
            raise HTTPException(400, str(e))
        return RedirectResponse(url)

    @app.get("/auth/github/callback", name="github_callback")
    async def github_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        try:
            audit_id = verifier.pop_oauth_state(state)
            a = get_audit(audit_id)
            if error or not code:
                raise VerificationError("Вход отменён на стороне GitHub")
            login, emails = await verifier.github_exchange(code, str(request.url_for("github_callback")))
        except (VerificationError, HTTPException) as e:
            msg = getattr(e, "detail", None) or str(e)
            return RedirectResponse(f"/?verify_error={quote_plus(msg)}#identities")
        apply_github_login(a, login, emails)
        a.add_log("OK", f"VERIFIED ....... github:{login} (OAuth); ник и {len(emails)} адрес(ов) наследуют подтверждение")
        touch(a)
        return RedirectResponse(f"/?audit={a.id}#identities")

    # ---------- run / review ----------
    @app.post("/api/audits/{audit_id}/run")
    async def run(audit_id: str, body: RunIn):
        a = get_audit(audit_id)
        ensure_idle(a)
        reg = registry_for(a)
        if body.module and body.module not in reg:
            raise HTTPException(400, "Нет такого модуля")
        if not any(a.is_verified(i, settings.verify_ttl_days) for i in a.identities):
            raise HTTPException(400, "Нет подтверждённых идентификаторов — поиск не запускается")
        a.running = True

        async def job():
            try:
                await run_audit(a, reg, settings, only_module=body.module, on_progress=store.persist)
            except asyncio.CancelledError:
                a.running = False
                raise
            except Exception as e:  # noqa: BLE001
                a.running = False
                a.add_log("ERROR", f"AUDIT CRASHED — {e}")
            finally:
                tasks.pop(a.id, None)

        tasks[a.id] = asyncio.create_task(job())
        return view(a)

    @app.post("/api/audits/{audit_id}/findings/{finding_id}/review")
    def review(audit_id: str, finding_id: str, body: ReviewIn):
        a = get_audit(audit_id)
        f = a.finding(finding_id)
        if not f:
            raise HTTPException(404, "Нет такой находки")
        if body.verdict not in (None, "mine", "not_mine"):
            raise HTTPException(400, "verdict: mine | not_mine | null")
        if body.verdict is None:
            f.status = "review" if f.type == "profile_url" else "confirmed"
        else:
            f.status = body.verdict
        a.add_log("OK" if f.status == "mine" else "INFO", f"MANUAL REVIEW ....... {f.value} → {f.status.upper()}")
        touch(a)
        return view(a)

    @app.put("/api/audits/{audit_id}/modules/{module}")
    def toggle_module(audit_id: str, module: str, body: ToggleIn):
        a = get_audit(audit_id)
        if module not in registry_for(a):
            raise HTTPException(404, "Нет такого модуля")
        if body.enabled:
            a.disabled_modules = [m for m in a.disabled_modules if m != module]
        elif module not in a.disabled_modules:
            a.disabled_modules.append(module)
        store.persist(a)
        return view(a)

    # ---------- static ----------
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/favicon.ico")
    def favicon():
        return FileResponse(STATIC / "img" / "favicon-32.png")

    return app

