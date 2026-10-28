"""CLI: python -m hidenseek <команда>. Без команды запускает сайт.

Работает с сохранёнными аудитами (отметка «сохранить аудит» на сайте) и с учебным режимом.
Подтверждение идентификаторов — на сайте: там вход через GitHub и ввод кода из письма.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import settings
from .core import crypto, html_report
from .core import report as report_mod
from .core.dispatcher import run_audit
from .core.models import Audit
from .core.storage import AuditStore, export_json

app = typer.Typer(add_completion=False, no_args_is_help=False, help="HidenSeek — аудит собственного цифрового следа")
console = Console()

SEV_STYLE = {4: "bold red", 3: "red", 2: "yellow", 1: "green", 0: "dim"}
SEV_LABEL = {4: "критично", 3: "высокая", 2: "средняя", 1: "низкая", 0: "инфо"}


def _store() -> AuditStore:
    return AuditStore(settings.data_dir, crypto.make_cipher(settings.encrypt, settings.key_file, settings.key))


def _get(store: AuditStore, audit_id: str) -> Audit:
    a = store.get(audit_id)
    if not a:
        console.print(f"[red]Аудит {audit_id} не найден.[/red] Сохранённые: hidenseek list")
        raise typer.Exit(1)
    return a


def print_report(a: Audit, limit: int = 30) -> None:
    rep = report_mod.build(a, settings)
    t = rep["totals"]
    console.print(f"[bold green]{a.id}[/] · {'учебный режим' if a.mode == 'demo' else 'аудит своего следа'} · "
                  f"запусков: {t['runs']} · подтверждено {t['identities_verified']}/{t['identities']} идентификаторов")
    console.print(rep["summary"], highlight=False)
    table = Table(show_lines=False, header_style="dim")
    for col in ("", "находка", "источник", "раскрывает", "статус", "первый шаг"):
        table.add_column(col, overflow="fold")
    for it in [i for i in rep["items"] if i["severity"] or i["gone"]][:limit]:
        f = it["finding"]
        mark = "исчезло" if it["gone"] else {"new": "новое", "changed": "изменилось"}.get(it.get("change") or "", "")
        status = f["status"] + (" ✓закрыто" if it["resolved"] else "") + (f" · {mark}" if mark else "")
        table.add_row(f"[{SEV_STYLE[it['severity']]}]{SEV_LABEL[it['severity']]}[/]", f["value"], f["source"],
                      ", ".join(e["what"] for e in it["exposures"]) or "—", status,
                      (it["recommendations"] or ["—"])[0])
    console.print(table)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        serve()


@app.command()
def serve(host: str = settings.host, port: int = settings.port) -> None:
    """Запустить локальный сайт (по умолчанию http://127.0.0.1:8000)."""
    import uvicorn

    from .webapp.app import create_app

    if host not in ("127.0.0.1", "localhost"):
        console.print("[yellow]Сайт рассчитан на локальный запуск; доступ извне не защищён авторизацией.[/]")
    uvicorn.run(create_app(settings), host=host, port=port)


@app.command()
def demo(persona: str = typer.Argument("alice", help="alice | boris"),
         runs: int = typer.Option(1, min=1, max=3, help="Сколько раз прогнать (2 — увидеть сравнение)")) -> None:
    """Учебный режим в терминале: синтетический персонаж, без сети."""
    from .demo.personas import PERSONAS, build_demo_audit, demo_enricher, mock_registry
    from .modules import real_registry

    if persona not in PERSONAS:
        console.print(f"[red]Нет персонажа {persona}.[/] Есть: {', '.join(PERSONAS)}")
        raise typer.Exit(1)
    a = build_demo_audit(persona)
    reg = mock_registry(real_registry(), delay=0)
    settings.module_delay = 0.0
    for _ in range(runs):
        with console.status("аудит…"):
            asyncio.run(run_audit(a, reg, settings, enricher=demo_enricher()))
    print_report(a)


@app.command("list")
def list_audits() -> None:
    """Сохранённые аудиты."""
    store = _store()
    table = Table(header_style="dim")
    for col in ("id", "режим", "создан", "находок", "запусков", "расписание"):
        table.add_column(col)
    for a in store.all():
        table.add_row(a.id, a.mode, a.created_at.strftime("%d.%m.%Y %H:%M"), str(len(a.findings)), str(len(a.runs)),
                      f"каждые {a.schedule_hours} ч" if a.schedule_hours else "—")
    console.print(table if store.all() else "Сохранённых аудитов нет. На сайте отметьте «Сохранить аудит на диск».")
    if store.unreadable:
        console.print(f"[yellow]Не удалось прочитать: {', '.join(store.unreadable)}[/]")


@app.command()
def show(audit_id: str) -> None:
    """Отчёт по сохранённому аудиту."""
    print_report(_get(_store(), audit_id))


@app.command()
def run(audit_id: str, module: Optional[str] = typer.Option(None, help="только этот источник")) -> None:
    """Повторный аудит сохранённого аудита (удобно для cron) и сравнение с прошлым."""
    from .modules import real_registry
    from .modules.own_profile import ProfileEnricher

    store = _store()
    a = _get(store, audit_id)
    if a.mode != "real":
        console.print("[red]Это учебный аудит — используйте hidenseek demo.[/]")
        raise typer.Exit(1)
    if not any(a.is_verified(i, settings.verify_ttl_days) for i in a.identities):
        console.print("[red]Нет подтверждённых идентификаторов — подтвердите их на сайте.[/]")
        raise typer.Exit(1)
    with console.status("аудит…"):
        asyncio.run(run_audit(a, real_registry(), settings, only_module=module, on_progress=store.persist,
                              enricher=ProfileEnricher()))
    store.persist(a)
    print_report(a)


@app.command()
def export(audit_id: str, fmt: str = typer.Option("html", "--format", help="html | json"),
           output: Optional[Path] = typer.Option(None, "-o", help="файл; по умолчанию hidenseek_<id>.<fmt>")) -> None:
    """Выгрузить отчёт в HTML или полный аудит в JSON."""
    a = _get(_store(), audit_id)
    if fmt == "html":
        text = html_report.render(a, report_mod.build(a, settings), settings.verify_ttl_days)
    elif fmt == "json":
        text = export_json(a)
    else:
        console.print("[red]--format: html или json[/]")
        raise typer.Exit(1)
    path = output or Path(f"hidenseek_{a.id}.{fmt}")
    path.write_text(text, encoding="utf-8")
    console.print(f"Сохранено: {path} — в файле ваши данные, храните его как личный документ.")
