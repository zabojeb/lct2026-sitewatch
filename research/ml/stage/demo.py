"""Демо на датасете №8: 8 камер одной площадки → этап работ → сверка с планом.

    python ml/stage/demo.py                   # разметка как «идеальный детектор»
    python ml/stage/demo.py --yoloe           # плюс настоящий zero-shot детектор
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fusion import Detection, camera_evidence, early_fuse, late_fuse, load_const_video
from infer import StageScorer, lookalike_confusion, plan_check
from matrix import load

ROOT = Path(__file__).resolve().parents[2]


def name(s, n=62):
    return s.name.replace("\n", " ")[:n]


def report(title, ev, M, sc, plans):
    print(f"\n{'═' * 78}\n{title}\n{'═' * 78}")
    print("что видит каждая камера (доля кадров):")
    for c in sorted(ev.per_camera, key=lambda x: int(x[3:])):
        e = ev.per_camera[c]
        txt = "  ".join(f"{M.keys[k].split(' /')[0].split(' ')[0]}({k}) {v:.2f}" for k, v in sorted(e.items())) or "— нет техники из словаря"
        print(f"  {c:5s} {txt}")
    if ev.unmapped:
        print("  не входит в словарь md:", ", ".join(f"{k} ×{v}" for k, v in ev.unmapped.most_common()))

    obs = early_fuse(ev)
    ranked = sc.rank(obs)
    print("\nОДНА КАМЕРА vs СЛИЯНИЕ — лучшая группа этапов:")
    for c in sorted(ev.per_camera, key=lambda x: int(x[3:])):
        if ev.per_camera[c]:
            p, mem = sc.groups(sc.rank(ev.per_camera[c]))[0]
            print(f"  {c:5s} p={p:.2f}  {name(mem[0], 58)}")
    groups = sc.groups(ranked)
    print("\nслияние всех камер — топ-5 групп неразличимых этапов:")
    for p, mem in groups[:5]:
        rows = ", ".join(str(s.row) for s in mem[:6]) + ("…" if len(mem) > 6 else "")
        print(f"  p={p:.3f}  строки {rows:18s} {name(mem[0], 50)}")
    print("\nраздел перечня (сумма по дочерним строкам):")
    for s, p in sc.rollup(ranked)[:3]:
        print(f"  p={p:.3f}  строка {s.row}: {name(s, 55)}")
    top = groups[0][1][0]
    ex = sc.explain(top, obs)
    print("\nобоснование лидера:")
    for k, v in ex.items():
        print(f"  {k:28s} {', '.join(f'{M.keys[x]} ({x})' for x in v) or '—'}")

    print("\nнабор этапов, совместно объясняющий камеры (позднее слияние):")
    for a in late_fuse(ev, sc):
        print(f"  {', '.join(a.cameras):40s} → {name(a.members[0], 40)}")

    print("\nсверка с планом:")
    for row in plans:
        r = plan_check(sc, obs, [row])
        extra = ""
        if r["verdict"].startswith("расход"):
            extra = (f" | лучше объясняет: «{name(r['лучше объясняет'], 40)}»; "
                     f"вне плана: {', '.join(r['техника вне планового этапа'])}")
        print(f"  план = строка {row} «{name(M.stages[row], 40)}» → {r['verdict']} (LR={r['lr']}){extra}")
    return {"obs": obs, "top_group_rows": [s.row for s in groups[0][1]], "p_top": groups[0][0]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yoloe", action="store_true")
    a = ap.parse_args()
    M = load(ROOT / "data/stage_equipment.md")
    sc = StageScorer(M, "bayes")
    # план: сваи (совпадает с увиденным) и асфальт (заведомо не совпадает)
    asphalt = next(s.row for s in M.leaves if "покрыт" in s.name.lower() and "R" in s.work)
    plans = [74, asphalt]

    dets, frames = load_const_video(ROOT / "data/external/const_video")
    ev = camera_evidence(dets, M, dataset="L08", frames_per_camera=frames)
    gt = report("РАЗМЕТКА КАК ИДЕАЛЬНЫЙ ДЕТЕКТОР (словарь md как есть)", ev, M, sc, plans)

    ev2 = camera_evidence(dets, M, dataset="L08", frames_per_camera=frames, extra_labels={"kran": "T"})
    gt2 = report("ЧУВСТВИТЕЛЬНОСТЬ: kran → башенный кран (в md не сопоставлен)", ev2, M, sc, plans)

    out = {"gt": gt, "gt_kran_T": gt2}
    if a.yoloe:
        d = json.load(open(ROOT / "ml/runs/const_video_yoloe.json"))
        ydets = [Detection(x["camera"], x["frame"], x["label"], x["conf"]) for x in d["detections"]]
        ev3 = camera_evidence(ydets, M, frames_per_camera=d["frames"], conf_thr=0.25,
                              extra_labels=d["prompt_to_key"])
        out["yoloe"] = report("НАСТОЯЩИЙ ДЕТЕКТОР: zero-shot YOLOE, свой словарь промптов", ev3, M, sc, plans)
        # zero-shot путает похожие классы (буровая ↔ копёр) — учитываем это матрицей «двойников»
        sc_c = StageScorer(M, "bayes", confusion=lookalike_confusion(M.keys))
        out["yoloe_conf"] = report("ТОТ ЖЕ YOLOE + матрица ошибок «двойников»", ev3, M, sc_c, plans)
    json.dump({k: {**v, "obs": {kk: round(vv, 3) for kk, vv in v["obs"].items()}} for k, v in out.items()},
              open(ROOT / "ml/runs/stage_demo.json", "w"), ensure_ascii=False, indent=1)
