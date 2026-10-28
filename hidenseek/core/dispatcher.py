"""Диспетчер: факт → модули с подходящим input_type → запуск.

1. Подтверждённый факт (type, value) → в очередь
2. Цикл: факт → модули с подходящим input_type → запуск
3. Найденное → в отчёт; новый факт идёт в очередь, только если он наследует подтверждение
4. Сбой модуля не роняет процесс: «недоступен» + причина
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional

import httpx

from ..config import Settings
from ..modules.base import Fact, Module, ModuleResult, RunContext
from . import matcher
from .models import SEARCHABLE_TYPES, Audit, Finding, IdentityType, SourceStatus, utcnow
from .queue import FactQueue, RateLimiter, with_retry
from .verify import add_inherited

MODULE_TIMEOUT = 600


@asynccontextmanager
async def default_client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": settings.user_agent},
                                 follow_redirects=True) as client:
        yield client


def _merge(audit: Audit, mod: Module, fact: Fact, result: ModuleResult) -> int:
    """Добавить находки; повторный запуск обновляет существующие, сохраняя вашу отметку «мой / не мой»."""
    index = {(f.source, f.type, f.value.lower()): f for f in audit.findings}
    added = 0
    for raw in result.findings:
        key = (mod.name, raw.type, raw.value.lower())
        existing = index.get(key)
        if existing:
            existing.url, existing.data, existing.confidence = raw.url, raw.data, raw.confidence
            existing.found_at = utcnow()
            continue
        f = Finding(type=raw.type, value=raw.value, source=mod.name, url=raw.url, confidence=raw.confidence,
                    status="review" if raw.review else "confirmed", identity_id=fact.identity_id, data=raw.data)
        audit.findings.append(f)
        index[key] = f
        added += 1
    return added


async def run_audit(
    audit: Audit,
    registry: dict[str, Module],
    settings: Settings,
    only_module: Optional[str] = None,
    client_factory: Callable = default_client,
    on_progress: Optional[Callable[[Audit], None]] = None,
) -> Audit:
    ttl = settings.verify_ttl_days
    queue = FactQueue(max_depth=settings.max_depth, max_facts=settings.max_facts)
    limiter = RateLimiter(settings.module_delay)
    progress = on_progress or (lambda a: None)
    audit.running = True
    audit.add_log("INFO", "AUDIT START" + (f" / ONLY {only_module.upper()}" if only_module else ""))

    for ident in audit.identities:
        if audit.is_verified(ident, ttl):
            queue.push(Fact(ident.type.value, ident.value, ident.id, 0))
        else:
            state = ident.verification_state(ttl)
            audit.add_log("WARN", f"SKIP {ident.type.value}:{ident.value} — {'истёк срок подтверждения' if state == 'expired' else 'не подтверждён'}, модули не запускаются")

    active = [m for m in registry.values() if m.name not in audit.disabled_modules
              and (only_module is None or m.name == only_module)]
    for m in active:
        ok, reason = m.available(settings)
        st = audit.sources.setdefault(m.name, SourceStatus(module=m.name))
        st.state, st.detail = ("queued", "") if ok else ("skipped", reason)
    progress(audit)

    try:
        async with client_factory(settings) as client:
            ctx = RunContext(settings=settings, client=client)
            while (fact := queue.pop()) is not None:
                for mod in active:
                    if mod.input_type != fact.type or not mod.available(settings)[0]:
                        continue
                    await _run_one(audit, mod, fact, ctx, limiter, queue, settings)
                    progress(audit)
    finally:
        for fact, why in queue.dropped:
            audit.add_log("WARN", f"FACT DROPPED {fact.type}:{fact.value} — {why}")
        for st in audit.sources.values():
            if st.state in ("queued", "running"):
                st.state = "done" if st.runs else "idle"
                if not st.runs:
                    st.detail = "нет подтверждённых идентификаторов подходящего типа"
        matcher.apply(audit, settings)
        audit.running = False
        audit.add_log("OK", f"AUDIT DONE ....... {len(audit.findings)} FINDINGS / {len(audit.exposures)} EXPOSURES")
        progress(audit)
    return audit


async def _run_one(audit: Audit, mod: Module, fact: Fact, ctx: RunContext, limiter: RateLimiter,
                   queue: FactQueue, settings: Settings) -> None:
    st = audit.sources.setdefault(mod.name, SourceStatus(module=mod.name))
    st.state, st.detail = "running", f"{fact.type}:{fact.value}"
    audit.add_log("INFO", f"RUN {mod.name.upper()} ....... {fact.type}:{fact.value}")

    async def call():
        await limiter.wait(mod.name)
        return await asyncio.wait_for(mod.run(fact, ctx), timeout=MODULE_TIMEOUT)

    def on_retry(n: int, e: Exception) -> None:
        audit.add_log("WARN", f"RETRY {mod.name.upper()} #{n} — {e}")

    try:
        result = await with_retry(call, settings.module_retries, max(settings.module_delay, 0.5), on_retry)
    except Exception as e:  # noqa: BLE001 — сбой модуля не роняет аудит
        st.state, st.detail = "failed", f"недоступен: {e or type(e).__name__}"
        st.runs += 1
        st.last_run = utcnow()
        audit.add_log("ERROR", f"{mod.name.upper()} FAILED — {e or type(e).__name__}")
        return

    added = _merge(audit, mod, fact, result)
    st.runs += 1
    st.findings += added
    st.last_run = utcnow()
    st.state, st.detail = "done", result.note or f"{len(result.findings)} находок"
    audit.add_log("OK", f"{mod.name.upper()} DONE ....... {len(result.findings)} FOUND / {added} NEW")

    parent = audit.identity(fact.identity_id)
    for nf in result.new_facts:
        if not nf.inherits or nf.type not in SEARCHABLE_TYPES or parent is None:
            audit.add_log("INFO", f"NOT QUEUED {nf.type}:{nf.value} — не наследует подтверждение")
            continue
        child = add_inherited(audit, IdentityType(nf.type), nf.value, parent, f"inherited:{parent.id}")
        if queue.push(Fact(nf.type, nf.value, child.id, fact.depth + 1)):
            audit.add_log("OK", f"QUEUED {nf.type}:{nf.value} — {nf.reason or 'наследует подтверждение'}")
