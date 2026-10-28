"""Сборка онлайн-демо HidenSeek: одна HTML-страница без сервера (учебный режим).

Учебные аудиты считаются настоящим кодом (core + мок-источники), снимки состояния
вшиваются в страницу, а tools/static_demo_shim.js подменяет fetch вместо API.

    python tools/build_static_demo.py build/hidenseek-demo.html
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hidenseek.config import Settings  # noqa: E402
from hidenseek.core import matcher, report  # noqa: E402
from hidenseek.core.dispatcher import run_audit  # noqa: E402
from hidenseek.demo.personas import PERSONAS, build_demo_audit, mock_registry  # noqa: E402
from hidenseek.modules import real_registry  # noqa: E402
from hidenseek.webapp.app import audit_view, config_view  # noqa: E402

STATIC = ROOT / "hidenseek" / "webapp" / "static"
FONT_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&display=swap">')


def persona_data(key: str, settings: Settings) -> dict:
    reg = mock_registry(real_registry(), delay=0)
    audit = build_demo_audit(key)
    initial = audit_view(audit, settings, reg)
    steps: list[dict] = []

    @asynccontextmanager
    async def no_client(_settings):
        yield None

    asyncio.run(run_audit(audit, reg, settings, client_factory=no_client,
                          on_progress=lambda a: steps.append(audit_view(a, settings, reg))))
    variants: dict[str, dict] = {}
    for f in audit.findings:
        original = f.status
        variants[f.id] = {}
        for status in ("confirmed", "review", "mine", "not_mine"):
            f.status = status
            matcher.apply(audit, settings)
            item = next(i for i in report.build(audit, settings)["items"] if i["finding"]["id"] == f.id)
            item.pop("finding")
            variants[f.id][status] = item
        f.status = original
    return {"initial": initial, "steps": steps, "variants": variants}


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def build(out: Path) -> None:
    settings = Settings()
    settings.module_delay = 0.0
    settings.smtp_host = settings.smtp_from = ""
    settings.github_client_id = settings.github_client_secret = settings.hibp_api_key = ""
    demo = {"config": config_view(settings),
            "personas": {k: persona_data(k, settings) for k in PERSONAS}}

    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = "\n".join((STATIC / "css" / n).read_text(encoding="utf-8") for n in ("ghost.css", "hidenseek.css"))
    css = re.sub(r"@font-face\{[^}]*\}\n?", "", css)
    css += "\n:root{color-scheme:dark}\nbody{background:var(--bg)}\n"
    app_js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    shim = (ROOT / "tools" / "static_demo_shim.js").read_text(encoding="utf-8")

    for name in ("favicon-32.png", "apple-touch-icon.png", "brand-mark.png"):
        html = html.replace(f"/static/img/{name}", data_uri(STATIC / "img" / name))
    head = html[html.index("<head>") + 6:html.index("</head>")]
    head = re.sub(r'<meta charset[^>]*>\s*|<meta name="viewport"[^>]*>\s*|<link rel="stylesheet"[^>]*>\s*', "", head)
    head = head.replace("<title>HidenSeek — мой цифровой след</title>", "<title>HidenSeek</title>")
    body = html[html.index("<body>") + 6:html.index("</body>")]
    body = body.replace('<script src="/static/js/app.js"></script>', "")
    payload = json.dumps(demo, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    page = (f"{head.strip()}\n{FONT_LINK}\n<style>\n{css}\n</style>\n{body.strip()}\n"
            f"<script>window.HS_DEMO={payload};</script>\n<script>\n{shim}\n</script>\n<script>\n{app_js}\n</script>\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"{out} — {len(page) / 1024:.0f} KB")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "hidenseek-demo.html")
