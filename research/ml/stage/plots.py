"""Графики направления «камеры → этап» для презентации."""
import json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import PercentFormatter

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ml/runs/stage"
OUT.mkdir(parents=True, exist_ok=True)

SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
S1, S2 = "#2a78d6", "#eb6834"                       # категориальные слоты 1–2
RAMP = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
                     "axes.edgecolor": GRID, "axes.labelcolor": INK2, "text.color": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
                     "font.size": 11, "legend.frameon": False, "axes.formatter.useoffset": False})


def label_end(ax, x, y, text, color, dy=0):
    ax.annotate(text, (x[-1], y[-1]), xytext=(8, dy), textcoords="offset points",
                va="center", color=INK2, fontsize=10)
    ax.plot(x[-1], y[-1], "o", ms=6, color=color, mec=SURF, mew=2, zorder=5)


sim = json.load(open(ROOT / "ml/runs/stage_experiments.json"))

# 1. шум детектора: «всё в set» против фильтра устойчивости
fp = sim["fp"]
x = [float(k) * 100 for k in fp]
fig, ax = plt.subplots(figsize=(7.2, 4.2))
for key, col, txt in (("persist_noisyor", S1, "фильтр устойчивости + слияние"),
                      ("union_raw", S2, "«всё, что мелькнуло, — в set»")):
    y = [v[key] for v in fp.values()]
    ax.plot(x, y, color=col, lw=2.2)
    label_end(ax, x, y, txt, col, dy=14 if key == "union_raw" else 0)
ax.axhline(1 / 55, color=INK2, lw=1, ls=(0, (4, 3)))
ax.text(8.5, 1 / 55 - 0.006, "случайное угадывание", ha="right", va="top", color=INK2, fontsize=9)
ax.set_xlabel("мигание детектора: ложная метка в кадре, % (на класс)")
ax.set_ylabel("этап угадан (top-1, по группам)")
ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0)); ax.set_ylim(0, 0.45); ax.set_xlim(0, 8.6)
ax.set_title("Без фильтра по кадрам объединение камер ломается\nуже от 0,5% ложных срабатываний",
             loc="left", fontsize=12)
fig.tight_layout(); fig.savefig(OUT / "noise.png", dpi=160); plt.close(fig)

# 2. число камер
cams = sim["cams"]
x = [int(k) for k in cams]
fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.9), sharex=True)
for ax, idx, title in ((axes[0], 0, "этап — лучший ответ (top-1)"), (axes[1], 1, "этап среди 5 лучших (top-5)")):
    for m, col, txt in (("bayes", S1, "байесовский"), ("jaccard", S2, "Jaccard")):
        y = [v[m][idx] for v in cams.values()]
        ax.plot(x, y, color=col, lw=2.2, marker="o", ms=5, mec=SURF, mew=1.5, label=txt)
    ax.set_title(title, loc="left", fontsize=11)
    ax.set_xlabel("камер на площадке"); ax.set_xticks(x); ax.set_xlim(0.6, 8.4)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
axes[0].set_ylim(0, 0.45); axes[1].set_ylim(0.4, 0.85)
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper right", ncol=2, bbox_to_anchor=(0.99, 1.02))
fig.suptitle("Выигрыш от камер набирается к четырём,\nдальше — плато",
             x=0.01, ha="left", fontsize=12, y=1.06)
fig.tight_layout(); fig.savefig(OUT / "cameras.png", dpi=160, bbox_inches="tight"); plt.close(fig)

# 3. ROC сверки с планом
pl = sim["plan"]
roc = np.array(pl["roc"])
fig, ax = plt.subplots(figsize=(5.4, 5.0))
ax.plot([0, 1], [0, 1], color=INK2, lw=1, ls=(0, (4, 3)))
ax.plot(roc[:, 0], roc[:, 1], color=S1, lw=2.2)
ax.plot(pl["fpr_at_3.5"], pl["recall_at_3.5"], "o", ms=9, color=S1, mec=SURF, mew=2.5, zorder=5)
ax.annotate(f"порог по умолчанию:\nложных тревог {pl['fpr_at_3.5']:.0%}\nпоймано {pl['recall_at_3.5']:.0%}",
            (pl["fpr_at_3.5"], pl["recall_at_3.5"]), xytext=(0.15, 0.66), textcoords="data", va="top",
            color=INK2, fontsize=10, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.set_xlabel("ложная тревога (план верен, но система ругается)")
ax.set_ylabel("поймано отклонений от плана")
ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0)); ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
ax.set_xlim(0, 1); ax.set_ylim(0, 1.02); ax.set_aspect("equal")
ax.set_title(f"Сверка с календарным планом, AUC = {pl['auc']:.2f}", loc="left", fontsize=12)
fig.tight_layout(); fig.savefig(OUT / "plan_roc.png", dpi=160); plt.close(fig)

# 4. реальная площадка: что видит каждая камера и что даёт слияние
from matrix import load
from fusion import load_const_video, camera_evidence, early_fuse
from infer import StageScorer
M = load(ROOT / "data/stage_equipment.md")
dets, frames = load_const_video(ROOT / "data/external/const_video")
ev = camera_evidence(dets, M, "L08", frames)
sc = StageScorer(M, "bayes")
fused = early_fuse(ev)
keys = sorted(fused, key=lambda k: -sum(k in e for e in ev.per_camera.values()))
cams_ = sorted(ev.per_camera, key=lambda c: int(c[3:]))
rows = cams_ + ["слияние"]
A = np.array([[ev.per_camera[c].get(k, 0) for k in keys] for c in cams_] + [[fused[k] for k in keys]])
answers = []
for c in cams_:
    if ev.per_camera[c]:
        p, mem = sc.groups(sc.rank(ev.per_camera[c]))[0]
        answers.append(f"{mem[0].name[:46]}  ({p:.0%})")
    else:
        answers.append("нет техники из словаря")
p, mem = sc.groups(sc.rank(fused))[0]
answers.append(f"{mem[0].name[:46]}  ({p:.0%})")
cmap = LinearSegmentedColormap.from_list("s", RAMP)
fig, ax = plt.subplots(figsize=(12.4, 5.2))
ax.pcolormesh(A, cmap=cmap, vmin=0, vmax=1, edgecolors=SURF, linewidth=2)
ax.invert_yaxis(); ax.grid(False)
short = {k: M.keys[k].split(" /")[0].replace("Грузовик общего класса", "Грузовик") for k in keys}
ax.set_xticks(np.arange(len(keys)) + 0.5, [short[k] for k in keys], rotation=35, ha="right")
ax.set_yticks(np.arange(len(rows)) + 0.5, rows)
ax.tick_params(length=0)
ax.axhline(len(cams_), color=INK, lw=2.5)
for i, t in enumerate(answers):
    ax.text(len(keys) + 0.25, i + 0.5, t, va="center", fontsize=10,
            color=INK if i == len(answers) - 1 else INK2,
            fontweight="bold" if i == len(answers) - 1 else "normal")
ax.set_xlim(0, len(keys) + 7.4)
for s in ax.spines.values():
    s.set_visible(False)
ax.set_title("Датасет №8: ни одна камера не видит весь комплект техники этапа — его собирает слияние\n"
             "(доля кадров, где видна техника; справа — лучший этап по камере и по слиянию)",
             loc="left", fontsize=12)
fig.tight_layout(); fig.savefig(OUT / "site_cameras.png", dpi=160); plt.close(fig)

# 5. подмена классов и матрица ошибок детектора
sub = sim["sub"]
x = [float(k) * 100 for k in sub]
fig, ax = plt.subplots(figsize=(6.6, 4.0))
for m, col, txt in (("bayes+conf", S1, "с матрицей ошибок детектора"), ("bayes", S2, "без неё")):
    y = np.array([v["plan"][m]["recall_at_fpr5"][0] for v in sub.values()])
    se = np.array([v["plan"][m]["recall_at_fpr5"][1] for v in sub.values()]) / np.sqrt(5)
    ax.fill_between(x, y - se, y + se, color=col, alpha=0.15, lw=0)
    ax.plot(x, y, color=col, lw=2.2, marker="o", ms=5, mec=SURF, mew=1.5)
    label_end(ax, x, list(y), txt, col)
ax.text(1.0, -0.2, "полоса — ±1 ст. ошибка, 5 сидов × 1000 площадок", transform=ax.transAxes,
        ha="right", va="top", color=INK2, fontsize=8.5)
ax.set_xlabel("детектор подменяет класс «двойником», % машин")
ax.set_ylabel("поймано отклонений\nпри ≤5% ложных тревог")
ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0)); ax.set_xlim(-3, 110); ax.set_ylim(0.3, 0.8)
ax.set_xticks(x, [f"{v:.0f}" for v in x])
ax.set_title("С матрицей ошибок сверка держится при подмене\nклассов, без неё — падает", loc="left", fontsize=12)
fig.tight_layout(); fig.savefig(OUT / "substitution.png", dpi=160); plt.close(fig)
print("готово:", sorted(p.name for p in OUT.glob("*.png")))
