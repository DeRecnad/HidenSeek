"""Реестр модулей. Новый источник = новый модуль с тем же интерфейсом (раздел 11).

Правило: модуль принимает только подтверждаемые типы (email / github / domain / username)
и отвечает на вопрос «что видно обо мне». Модули, раскрывающие круг общения,
местоположение или активность человека, в проект не входят.
"""
from __future__ import annotations

from .base import Module
from .crtsh_mod import CrtShModule
from .github_mod import GitHubModule
from .hibp_mod import HibpModule
from .holehe_mod import HoleheModule
from .maigret_mod import MaigretModule


def real_registry() -> dict[str, Module]:
    mods: list[Module] = [GitHubModule(), CrtShModule(), MaigretModule(), HoleheModule(), HibpModule()]
    return {m.name: m for m in mods}
