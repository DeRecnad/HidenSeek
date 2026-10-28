"""Хранение аудитов. Без отметки «сохранить аудит» на диск ничего не пишется.

С шифрованием (по умолчанию, если установлен cryptography) файлы — data/audits/<id>.json.enc,
без него — <id>.json. Старые открытые файлы при следующем сохранении переписываются зашифрованными.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from .crypto import Cipher, CipherError
from .models import SCHEMA_VERSION, Audit


class AuditStore:
    def __init__(self, data_dir: Path, cipher: Optional[Cipher] = None):
        self.dir = Path(data_dir) / "audits"
        self.cipher = cipher
        self._audits: dict[str, Audit] = {}
        self.unreadable: list[str] = []
        self._load()

    @property
    def encrypted(self) -> bool:
        return self.cipher is not None

    def _load(self) -> None:
        if not self.dir.is_dir():
            return
        for p in sorted(self.dir.glob("aud_*.json*")):
            try:
                raw = p.read_bytes()
                if p.suffix == ".enc":
                    if not self.cipher:
                        raise CipherError("файл зашифрован, а ключа или пакета cryptography нет")
                    raw = self.cipher.decrypt(raw)
                a = Audit.model_validate_json(raw)
            except Exception:  # noqa: BLE001 — битый или чужой файл не мешает остальным
                self.unreadable.append(p.name)
                continue
            a.running = False
            a.schema_version = SCHEMA_VERSION
            self._audits[a.id] = a

    def _paths(self, audit_id: str) -> tuple[Path, Path]:
        return self.dir / f"{audit_id}.json", self.dir / f"{audit_id}.json.enc"

    def all(self) -> list[Audit]:
        return sorted(self._audits.values(), key=lambda a: a.created_at, reverse=True)

    def get(self, audit_id: str) -> Optional[Audit]:
        return self._audits.get(audit_id)

    def add(self, audit: Audit) -> Audit:
        self._audits[audit.id] = audit
        self.persist(audit)
        return audit

    def persist(self, audit: Audit) -> None:
        plain, enc = self._paths(audit.id)
        if not audit.save:
            for p in (plain, enc):
                if p.exists():
                    p.unlink()
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        data = audit.model_dump_json(indent=1).encode("utf-8")
        target, stale = (enc, plain) if self.cipher else (plain, enc)
        if self.cipher:
            data = self.cipher.encrypt(data)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        if stale.exists():
            stale.unlink()

    def delete(self, audit_id: str) -> None:
        self._audits.pop(audit_id, None)
        for p in self._paths(audit_id):
            if p.exists():
                p.unlink()

    def wipe(self) -> None:
        self._audits.clear()
        self.unreadable.clear()
        if self.dir.exists():
            shutil.rmtree(self.dir)


def export_json(audit: Audit) -> str:
    return json.dumps(audit.model_dump(mode="json"), ensure_ascii=False, indent=2)
