"""python -m hidenseek — запустить локальный сайт (по умолчанию http://127.0.0.1:8000)."""
from __future__ import annotations

import argparse

import uvicorn

from .config import settings
from .webapp.app import create_app


def main() -> None:
    p = argparse.ArgumentParser(prog="hidenseek", description="HidenSeek — аудит собственного цифрового следа")
    p.add_argument("--host", default=settings.host)
    p.add_argument("--port", type=int, default=settings.port)
    args = p.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        print("Внимание: сайт рассчитан на локальный запуск; доступ извне не защищён авторизацией.")
    uvicorn.run(create_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
