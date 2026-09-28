"""«Данные по технике поменяются»: добавляем машину, не трогая код.

В md асфальтоукладчика нет («отдельным классом в проверенных списках не
найден»), а в списке 14 машин коллеги он есть. Добавляем ключ AP в КОПИЮ md —
строку словаря и ячейки «при выполнении работы» у асфальтовых этапов — и
сравниваем, что видит система до и после.

    python ml/stage/new_equipment_demo.py
"""
import re, sys, tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from api import SiteAnalyzer
from matrix import load

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/stage_equipment.md"
PAVER = "Асфальтоукладчик"


def with_paver(text: str) -> tuple[str, list[int]]:
    out, rows, sec = [], [], None
    for line in text.splitlines():
        if line.startswith("## "):
            sec = line[3:]
        if sec and sec.startswith("Словарь") and line.startswith("| Y |"):
            out += [line, f"| AP | {PAVER} | свой детектор: `asphalt_paver` |"]
            continue
        c = line.split(" | ")
        if sec and sec.startswith("Полное") and PAVER in line and "**R**" in line:
            # колонка «при выполнении работы» — третья с конца
            c[-3] += f"<br>**AP** — {PAVER}"
            rows.append(int(re.match(r"\|\s*(\d+)", line).group(1)))
            line = " | ".join(c)
        out.append(line)
    return "\n".join(out) + "\n", rows


def groups(M):
    return Counter(s.signature for s in M.leaves)


# детекции площадки, где кладут асфальт: каток, укладчик, самосвалы со смесью
DETS = [{"camera": f"cam{c}", "frame": str(f), "label": lb, "conf": 0.8}
        for c in (1, 2) for f in range(20) for lb in ("roller", "asphalt_paver", "dump_truck")]
LABELS = {"roller": "R", "dump_truck": "D", "asphalt_paver": "AP"}

text, rows = with_paver(SRC.read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as tmp:
    new_md = Path(tmp) / "stage_equipment_ap.md"
    new_md.write_text(text, encoding="utf-8")
    M0, M1 = load(SRC), load(new_md)
    print(f"асфальтовые этапы, куда добавлен AP: {rows}")
    print(f"ключей техники: {len(M0.keys)} → {len(M1.keys)}; "
          f"различимых групп этапов: {len(groups(M0))} → {len(groups(M1))}")
    for tag, md in (("md как есть", SRC), ("md + AP", new_md)):
        an = SiteAnalyzer(md, extra_labels=LABELS)
        rep = an.analyze(DETS, plan_rows=[rows[0]])
        paving = sum(g["p"] for g in rep["stage_groups"]
                     if any(s["row"] in rows for s in g["stages"]))
        top = rep["stage_groups"][0]
        print(f"\n[{tag}]")
        print(f"  техника: {', '.join(rep['equipment'])}; "
              f"не в словаре: {rep['unmapped_labels'] or '—'}")
        print(f"  лучшая группа: p={top['p']:.2f}  строки {[s['row'] for s in top['stages']]}  "
              f"«{top['stages'][0]['name'][:60]}»")
        print(f"  вероятность асфальтовых этапов (в топ-5 групп): {paving:.2f}")
        print(f"  план = строка {rows[0]} → {rep['plan']['verdict']} "
              f"(LR={rep['plan']['log_likelihood_ratio']})")
