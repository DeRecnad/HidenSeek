"""Шифрование сохранённых аудитов (Fernet). Ключ лежит вне репозитория.

Ключ берётся из HIDENSEEK_KEY или из файла HIDENSEEK_KEY_FILE
(по умолчанию ~/.config/hidenseek/key, создаётся с правами 600 при первом запуске).
Без пакета cryptography аудиты сохраняются открытым JSON — интерфейс об этом предупреждает.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class CipherError(Exception):
    pass


class Cipher:
    def __init__(self, key: bytes):
        from cryptography.fernet import Fernet

        self._f = Fernet(key)

    def encrypt(self, data: bytes) -> bytes:
        return self._f.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        from cryptography.fernet import InvalidToken

        try:
            return self._f.decrypt(token)
        except InvalidToken as e:
            raise CipherError("не тот ключ или файл повреждён") from e


def available() -> bool:
    try:
        import cryptography.fernet  # noqa: F401
    except ImportError:
        return False
    return True


def load_or_create_key(key_file: Path, env_key: str = "") -> bytes:
    if env_key:
        return env_key.encode()
    if key_file.is_file():
        return key_file.read_bytes().strip()
    from cryptography.fernet import Fernet

    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    return key


def make_cipher(enabled: bool, key_file: Path, env_key: str = "") -> Optional[Cipher]:
    if not enabled or not available():
        return None
    return Cipher(load_or_create_key(key_file, env_key))
