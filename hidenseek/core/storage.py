"""Хранение аудитов. Без отметки «сохранить аудит» на диск ничего не пишется.

Шифрование базы (Fernet) — следующий этап; пока файлы лежат в data/ (в .gitignore).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from .models import Audit


class AuditStore:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "audits"
        self._audits: dict[str, Audit] = {}
        self._load()

    def _load(self) -> None:
        if not self.dir.is_dir():
            return
        for p in sorted(self.dir.glob("aud_*.json")):
            try:
                a = Audit.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — битый файл не мешает остальным
                continue
            a.running = False
            self._audits[a.id] = a

    def _path(self, audit_id: str) -> Path:
        return self.dir / f"{audit_id}.json"

    def all(self) -> list[Audit]:
        return sorted(self._audits.values(), key=lambda a: a.created_at, reverse=True)

    def get(self, audit_id: str) -> Optional[Audit]:
        return self._audits.get(audit_id)

    def add(self, audit: Audit) -> Audit:
        self._audits[audit.id] = audit
        self.persist(audit)
        return audit

    def persist(self, audit: Audit) -> None:
        p = self._path(audit.id)
        if audit.save:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(audit.model_dump_json(indent=1), encoding="utf-8")
            tmp.replace(p)
        elif p.exists():
            p.unlink()

    def delete(self, audit_id: str) -> None:
        self._audits.pop(audit_id, None)
        p = self._path(audit_id)
        if p.exists():
            p.unlink()

    def wipe(self) -> None:
        self._audits.clear()
        if self.dir.exists():
            shutil.rmtree(self.dir)


def export_json(audit: Audit) -> str:
    return json.dumps(audit.model_dump(mode="json"), ensure_ascii=False, indent=2)
