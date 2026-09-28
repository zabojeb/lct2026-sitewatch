#!/usr/bin/env python3
"""Launch the packaged СтройКонтур static demo with Python's standard library."""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
import webbrowser


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"


def main() -> None:
    parser = argparse.ArgumentParser(description="Запуск демонстрации СтройКонтур")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if not (DIST / "index.html").is_file():
        raise SystemExit(f"Не найден готовый сайт: {DIST / 'index.html'}")

    handler = partial(SimpleHTTPRequestHandler, directory=os.fspath(DIST))
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as error:
        raise SystemExit(
            f"Не удалось занять порт {args.port}: {error}\n"
            f"Попробуйте: python3 serve.py --port 8080"
        ) from error

    url = f"http://{args.host}:{args.port}"
    print(f"СтройКонтур запущен: {url}")
    print("Для остановки нажмите Ctrl+C.")
    if not args.no_browser:
        Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервис остановлен.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

