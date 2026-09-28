"""Все эксперименты направления одной командой — для воспроизводимости цифр.

    python ml/stage/experiments.py && python ml/stage/plots.py
"""
import json, statistics as st, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from infer import lookalike_confusion
from matrix import load
from simulate import Noise, roc, run, run_parallel, run_plan

ROOT = Path(__file__).resolve().parents[2]
M = load(ROOT / "data/stage_equipment.md")
C = lookalike_confusion(M.keys)
SEEDS = range(5)


def mean_sd(xs):
    return round(st.mean(xs), 4), round(st.stdev(xs), 4)


out = {}
# 1. методы × способы слияния
rs = [run(M, 600, Noise(), seed=s) for s in SEEDS]
out["main"] = {f"{m}|{f}": {"top1": mean_sd([r[(m, f)][0] for r in rs]),
                            "top5": mean_sd([r[(m, f)][1] for r in rs])}
               for (m, f) in rs[0]}
# 2. число камер
out["cams"] = {}
for n in (1, 2, 4, 6, 8):
    rr = [run(M, 500, Noise(n_cam=n), seed=s, methods=("jaccard", "bayes"), fusions=("persist_noisyor",))
          for s in range(3)]
    out["cams"][n] = {m: (st.mean(r[(m, "persist_noisyor")][0] for r in rr),
                          st.mean(r[(m, "persist_noisyor")][1] for r in rr)) for m in ("jaccard", "bayes")}
# 3. мигание детектора
out["fp"] = {}
for fp in (0.0, 0.005, 0.01, 0.02, 0.05):
    rr = [run(M, 500, Noise(p_fp=fp), seed=s, methods=("bayes",), fusions=("union_raw", "persist_noisyor"))
          for s in range(3)]
    out["fp"][fp] = {f: st.mean(r[("bayes", f)][0] for r in rr) for f in ("union_raw", "persist_noisyor")}
# 4. сверка с планом
plan_runs = [run_plan(M, 800, seed=s) for s in SEEDS]
pairs = sum((r[0] for r in plan_runs), [])
pts, auc, npos, nneg = roc(pairs)                       # общий пул — для кривой
d35 = [p for p in pts if p[2] <= 3.5][0]
seed_roc = [roc(r[0]) for r in plan_runs]               # по сидам — для разброса
seed_d35 = [[p for p in r[0] if p[2] <= 3.5][0] for r in seed_roc]
out["plan"] = {"exact_row_acc": mean_sd([r[1] for r in plan_runs]),
               "auc_seeds": mean_sd([r[1] for r in seed_roc]),
               "fpr_at_3.5_seeds": mean_sd([p[0] for p in seed_d35]),
               "recall_at_3.5_seeds": mean_sd([p[1] for p in seed_d35]),
               "auc": auc, "n_pos": npos, "n_neg": nneg, "fpr_at_3.5": d35[0], "recall_at_3.5": d35[1],
               "operating": {str(t): max((p for p in pts if p[0] <= t), key=lambda p: p[1])[1]
                             for t in (0.01, 0.05, 0.10)},
               "roc": [(x, y) for x, y, _ in pts]}
# 5. подмена классов и матрица ошибок
out["sub"] = {}
for p_sub in (0.0, 0.2, 0.4, 0.6):
    nz = Noise(p_sub=p_sub)
    rr = [run(M, 600, nz, seed=s, methods=("bayes",), fusions=("persist_noisyor",), confusion=C) for s in range(4)]
    row = {"top5": {m: st.mean(r[(m, "persist_noisyor")][1] for r in rr) for m in ("bayes", "bayes+conf")},
           "plan": {}}
    for nm, conf in (("bayes", None), ("bayes+conf", C)):
        per = []                                          # по сидам — чтобы видеть разброс
        for s in SEEDS:
            pts_, auc_, _, _ = roc(run_plan(M, 1000, nz, seed=s, confusion=conf)[0])
            per.append((auc_, max((p for p in pts_ if p[0] <= 0.05), key=lambda p: p[1])[1]))
        row["plan"][nm] = {"auc": mean_sd([a for a, _ in per]),
                           "recall_at_fpr5": mean_sd([r for _, r in per])}
    out["sub"][p_sub] = row
# 6. параллельные работы
out["parallel"] = {n: run_parallel(M, 400, Noise(n_cam=4), n_true=n) for n in (1, 2)}

json.dump(out, open(ROOT / "ml/runs/stage_experiments.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "plan"}, ensure_ascii=False, indent=1)[:3500])
print("plan:", {k: v for k, v in out["plan"].items() if k != "roc"})
