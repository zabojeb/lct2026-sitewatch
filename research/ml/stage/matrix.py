"""Матрица «этап → техника» из techника-по-этапам.md.

Файл — первоисточник для этого направления, поэтому ничего не хардкодим: и
словарь техники, и соответствие этапам читаются из него. Если набор техники
поменяется, меняется только md — код остаётся тем же. Внутри движка техника —
это абстрактные ключи (E, D, B, …), а не классы конкретного детектора.

Что достаём:
  * keys        — ключ → название техники;
  * labels      — (датасет, id, метка) → ключ: мост от классов детектора к ключам;
  * stages      — строка XLSX → название, ключи «при выполнении работы» (work),
                  ключи «доставка/подача» (delivery), условие;
  * hierarchy   — сводные строки («Свод … по строкам XLSX a–b») и их дети.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

KEY_RE = re.compile(r"\*\*([A-Z]{1,3})\*\*")
LABEL_RE = re.compile(r"(L\d{2}):(\d+|XML без ID)\s*`([^`]+)`")
SUMMARY_RE = re.compile(r"строкам XLSX\s+(\d+)\s*[–-]\s*(\d+)")


@dataclass
class Stage:
    row: int                      # номер строки Excel — однозначная ссылка на исходник
    name: str
    work: frozenset[str]          # техника самой операции
    delivery: frozenset[str]      # логистика: присутствие не доказывает этап
    condition: str
    children: tuple[int, ...] = ()   # для сводных строк — диапазон дочерних строк

    @property
    def is_summary(self) -> bool:
        return bool(self.children)

    @property
    def observable(self) -> bool:
        """Этап, у которого нет техники ни в работе, ни в доставке, по камере не
        распознать в принципе — отдаём его как «не наблюдаемо», а не угадываем."""
        return bool(self.work or self.delivery)

    @property
    def signature(self) -> tuple[frozenset, frozenset]:
        return (self.work, self.delivery)


@dataclass
class StageMatrix:
    keys: dict[str, str]
    labels: dict[tuple[str, str], str]           # (датасет, метка в нижнем регистре) -> ключ
    stages: dict[int, Stage] = field(default_factory=dict)

    # --- мост от детектора к ключам ---------------------------------------
    def key_for(self, label: str, dataset: str | None = None) -> str | None:
        """Ключ техники для метки детектора.

        Сначала ищем точное совпадение в указанном датасете, затем — по одной
        метке среди всех датасетов (если она однозначна). Регистр и разделители
        не важны: `Dump truck`, `dump_truck`, `dump-truck` — одно и то же.
        """
        norm = _norm(label)
        if dataset and (dataset, norm) in self.labels:
            return self.labels[(dataset, norm)]
        hits = {k for (ds, lb), k in self.labels.items() if lb == norm}
        return hits.pop() if len(hits) == 1 else None

    @property
    def leaves(self) -> list[Stage]:
        """Наблюдаемые листовые этапы — кандидаты для распознавания.

        Сводные строки — это объединение детей, а не отдельная работа. Если
        оставить их кандидатами, они будут выигрывать просто потому, что их
        набор техники шире; их вероятность получаем суммой по детям.
        """
        return [s for s in self.stages.values() if s.observable and not s.is_summary]

    def parents_of(self, row: int) -> list[Stage]:
        return [s for s in self.stages.values() if row in s.children]


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", s.strip().lower())


def _cells(line: str) -> list[str]:
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return parts


def load(md_path: str | Path) -> StageMatrix:
    text = Path(md_path).read_text(encoding="utf-8")
    lines = text.splitlines()

    keys, labels = {}, {}
    sec = None
    stages: dict[int, Stage] = {}
    for line in lines:
        if line.startswith("## "):
            sec = line[3:].strip()
            continue
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        c = _cells(line)
        if sec and sec.startswith("Словарь") and len(c) >= 3 and c[0] != "Ключ":
            k = c[0].strip()
            keys[k] = c[1].strip()
            for ds, _id, lb in LABEL_RE.findall(c[2]):
                labels[(ds, _norm(lb))] = k
        elif sec and sec.startswith("Полное") and len(c) >= 5 and c[0].isdigit():
            row = int(c[0])
            # название этапа может содержать «|» — берём всё между первой и тремя последними
            name = " | ".join(c[1:-3]).replace("<br>", "\n")
            work = frozenset(KEY_RE.findall(c[-3]))
            deliv = frozenset(KEY_RE.findall(c[-2]))
            cond = c[-1]
            m = SUMMARY_RE.search(cond)
            kids = tuple(range(int(m.group(1)), int(m.group(2)) + 1)) if m else ()
            stages[row] = Stage(row, name, work, deliv, cond, kids)

    unknown = {k for s in stages.values() for k in s.work | s.delivery} - set(keys)
    if unknown:
        raise ValueError(f"в матрице есть ключи, которых нет в словаре: {unknown}")
    return StageMatrix(keys, labels, stages)


if __name__ == "__main__":
    import sys
    from collections import Counter
    M = load(sys.argv[1] if len(sys.argv) > 1 else "data/stage_equipment.md")
    st = list(M.stages.values())
    print(f"ключей техники: {len(M.keys)} | меток датасетов в мосту: {len(M.labels)}")
    print(f"строк XLSX: {len(st)} | сводных: {sum(s.is_summary for s in st)} | "
          f"ненаблюдаемых (нет техники): {sum(not s.observable for s in st)} | "
          f"листовых-кандидатов: {len(M.leaves)}")
    sig = Counter(s.signature for s in M.leaves)
    print(f"уникальных наборов техники среди кандидатов: {len(sig)} "
          f"(крупнейшая группа неразличимых этапов: {max(sig.values())})")
    kf = Counter(k for s in M.leaves for k in s.work)
    print("в скольких этапах встречается ключ (work):",
          ", ".join(f"{k}={n}" for k, n in kf.most_common()))
