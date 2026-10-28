"""Maigret: на каких сайтах занят ваш ник.

Рекурсивный поиск и извлечение ID со страниц отключены: Maigret не должен сам
добавлять новые ники в очередь — они не наследуют подтверждение.
Каждая находка помечается «проверьте вручную: ваш ли это аккаунт?» (коллизии популярных ников).
"""
from __future__ import annotations

import logging
import re

from ..config import Settings
from .base import Fact, Module, ModuleError, ModuleResult, RawFinding, RunContext

TOP_SITES = 500


def username_confidence(username: str) -> float:
    """Чем уникальнее ник, тем вероятнее, что найденный аккаунт ваш."""
    u = username.lower()
    score = 0.35
    score += min(len(u), 14) * 0.03
    if re.search(r"\d", u):
        score += 0.08
    if re.search(r"[._-]", u):
        score += 0.05
    if re.fullmatch(r"[a-z]+", u) and len(u) <= 6:
        score -= 0.15  # короткое словарное слово: persik, alex, max
    return round(max(0.15, min(score, 0.9)), 2)


class MaigretModule(Module):
    name = "maigret"
    title = "Maigret"
    input_type = "username"
    outputs = ("profile_url",)
    description = f"Проверяет ваш ник на {TOP_SITES} популярных сайтах."

    def available(self, settings: Settings) -> tuple[bool, str]:
        try:
            import maigret  # noqa: F401
        except ImportError:
            return False, "не установлен: pip install -r requirements-sources.txt"
        return True, ""

    async def run(self, fact: Fact, ctx: RunContext) -> ModuleResult:
        try:
            from maigret.checking import maigret as maigret_search
            from maigret.result import MaigretCheckStatus
            from maigret.sites import MaigretDatabase
            from maigret.db_updater import BUNDLED_DB_PATH
        except ImportError as e:
            raise ModuleError(f"maigret недоступен: {e}", retry=False) from e

        db = MaigretDatabase().load_from_path(BUNDLED_DB_PATH)
        sites = db.ranked_sites_dict(top=TOP_SITES, disabled=False)
        logger = logging.getLogger("hidenseek.maigret")
        logger.setLevel(logging.WARNING)
        results = await maigret_search(
            username=fact.value, site_dict=sites, logger=logger, timeout=10,
            is_parsing_enabled=False, is_enrich_enabled=False,
            no_progressbar=True, max_connections=20, retries=1,
        )
        conf = username_confidence(fact.value)
        res = ModuleResult()
        for site_name, r in (results or {}).items():
            status = r.get("status")
            if status is None or getattr(status, "status", None) != MaigretCheckStatus.CLAIMED:
                continue
            url = r.get("url_user") or getattr(status, "site_url_user", None)
            res.findings.append(RawFinding(
                type="profile_url", value=f"{site_name}: {fact.value}", url=url,
                confidence=conf, review=True,
                data={"site": site_name, "tags": list(getattr(status, "tags", []) or [])},
            ))
        return res
