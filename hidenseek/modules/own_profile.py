"""Разбор ВАШИХ страниц: только находки, которые вы сами отметили «мой».

Maigret ищет без разбора страниц (иначе он сам добавлял бы новые ники в очередь).
Когда вы подтвердили, что аккаунт ваш, страницу можно прочитать, чтобы понять,
видно ли на ней ваше настоящее имя или город. Найденные поля идут только в сверку
с профилем «это я»: в очередь ничего не добавляется, по ссылкам со страницы не ходим.
"""
from __future__ import annotations

from typing import Optional

import httpx

from ..core.models import Finding

MAX_BYTES = 2_000_000
FIELD_MAP = {
    "fullname": "name", "full_name": "name", "name": "name",
    "location": "location", "city": "location", "country": "country",
    "bio": "bio", "description": "bio", "website": "blog",
}


def eligible(f: Finding) -> bool:
    return f.type == "profile_url" and f.status == "mine" and f.gone_at is None and bool(f.url) \
        and str(f.url).startswith(("http://", "https://"))


class ProfileEnricher:
    name = "own_profile"
    title = "Разбор моих страниц"

    def available(self) -> tuple[bool, str]:
        try:
            import socid_extractor  # noqa: F401  (ставится вместе с maigret)
        except ImportError:
            return False, "нужен socid_extractor: pip install -r requirements-sources.txt"
        return True, ""

    async def enrich(self, f: Finding, client: Optional[httpx.AsyncClient]) -> Optional[dict]:
        from socid_extractor import extract

        own = client is None
        client = client or httpx.AsyncClient(timeout=15, follow_redirects=True)
        try:
            r = await client.get(str(f.url))
        finally:
            if own:
                await client.aclose()
        if r.status_code != 200:
            return None
        raw = extract(r.text[:MAX_BYTES]) or {}
        fields: dict[str, str] = {}
        for key, value in raw.items():
            target = FIELD_MAP.get(str(key).lower())
            if target and value and target not in fields:
                fields[target] = str(value)[:300]
        if "country" in fields:
            loc = fields.pop("country")
            fields["location"] = f"{fields['location']}, {loc}" if "location" in fields else loc
        return fields or None


class DemoEnricher:
    """Учебный режим: заранее заданные поля для синтетических страниц."""
    name = "own_profile"
    title = "Разбор моих страниц (мок)"

    def __init__(self, data: dict[str, dict]):
        self.data = data

    def available(self) -> tuple[bool, str]:
        return True, ""

    async def enrich(self, f: Finding, client) -> Optional[dict]:
        return dict(self.data[f.url]) if f.url in self.data else None
