#!/usr/bin/env python3
"""Читаемый вывод логов Kaggle-ядра.

`kaggle kernels logs` отдаёт сырой JSON со stdout/stderr вперемешку и
экранированными переводами строк — глазами это не читается. Скрипт собирает
потоки обратно в текст и по умолчанию показывает хвост.

    python ml/kaggle/klog.py zabojeb/lct2026-yolo-comparison [-n 60] [--err] [--grep ТЕКСТ]
"""
import argparse, json, subprocess, sys


def fetch(slug: str) -> list[dict]:
    r = subprocess.run(["kaggle", "kernels", "logs", slug], capture_output=True, text=True)
    body = "\n".join(l for l in r.stdout.splitlines() if not l.startswith("Warning:"))
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(body[-4000:] or r.stderr[-2000:], file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("-n", type=int, default=60, help="сколько строк хвоста показать")
    ap.add_argument("--err", action="store_true", help="только stderr")
    ap.add_argument("--grep", default=None)
    a = ap.parse_args()

    msgs = fetch(a.slug)
    text = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if a.err and m.get("stream_name") != "stderr":
            continue
        text.extend(str(m.get("data", "")).splitlines())

    # шум Kaggle-раннера, который не несёт информации о нашем коде
    NOISE = ("Debugger warning", "frozen modules", "PYDEVD_DISABLE", "MissingIDField",
             "SyntaxWarning", "NbConvertApp", "validate(nb)", "0.00s -")
    text = [l for l in text if l.strip() and not any(x in l for x in NOISE)]
    if a.grep:
        text = [l for l in text if a.grep.lower() in l.lower()]
    print("\n".join(text[-a.n:]))


if __name__ == "__main__":
    main()
