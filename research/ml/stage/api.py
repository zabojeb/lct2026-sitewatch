"""Входная точка для бэкенда: детекции всех камер за окно → отчёт по площадке.

    from api import SiteAnalyzer
    an = SiteAnalyzer("data/stage_equipment.md")
    report = an.analyze(detections, plan_rows=[74])      # JSON-сериализуемый dict

Детекции — список словарей {camera, frame, label, conf}. label — класс ЛЮБОГО
детектора: мост к ключам техники строится из словаря md (для меток известных
датасетов) плюс `extra_labels` для своего словаря. Поменялся набор техники —
меняется md, код не трогаем.
"""
from __future__ import annotations

import sys, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fusion import Detection, camera_evidence, early_fuse, late_fuse
from infer import StageScorer, plan_check, plan_prior
from matrix import load


# метки нашего дообученного детектора (ml/kaggle/finetune, 11 классов) → ключи md
FINETUNE_11 = {"dump_truck": "D", "excavator": "E", "roller": "R", "crane_manipulator": "M",
               "concrete_mixer": "X", "bulldozer": "B", "truck": "Q", "mobile_crane": "C",
               "tower_crane": "T", "drilling_rig": "V", "concrete_pump": "P"}


# итоговый каскад команды (YOLO26x → ConvNeXt-small, 22 класса + unknown, class_names.json
# пакета jepa-models) → ключи md. Цистерна, уборочная техника, люди, «прочий транспорт» и
# unknown в матрице этапов не участвуют: md прямо относит их к обслуживанию площадки.
JEPA_22 = {"dump_truck": "D", "excavator": "E", "motor_grader": "G", "roller": "R",
           "crane_manipulator": "M", "light_commercial_vehicle": "Z", "forklift": "F",
           "bucket_loader": "L", "concrete_mixer": "X", "bulldozer": "B", "truck": "Q",
           "trailer": "J", "mobile_crane": "C", "tower_crane": "T", "tractor": "Y",
           "concrete_pump": "P", "drilling_rig": "V", "pile_driver": "PD"}


class SiteAnalyzer:
    def __init__(self, md_path: str, dataset: str | None = None,
                 extra_labels: dict[str, str] | None = None,
                 confusion: dict | None = None,
                 key_weights: dict[str, float] | None = None,
                 conf_thr: float = 0.25, min_frac: float = 0.15,
                 plan_threshold: float = 3.5):
        """confusion — матрица ошибок детектора с ЕГО валидации
        (infer.confusion_from_counts). Без неё считаем детектор безошибочным:
        для хорошо обученного это верно, для zero-shot — нет."""
        self.M = load(md_path)
        orphan = {lb: k for lb, k in (extra_labels or {}).items() if k not in self.M.keys}
        if orphan:
            warnings.warn(f"ключей нет в md, метки пойдут в unmapped_labels: {orphan}")
        self.dataset, self.extra = dataset, extra_labels
        self.kw, self.conf_thr, self.min_frac = key_weights, conf_thr, min_frac
        self.thr = plan_threshold
        self.sc = StageScorer(self.M, "bayes", confusion=confusion)

    def _stage(self, s):
        return {"row": s.row, "name": s.name.replace("\n", " ")}

    def analyze(self, detections: list[dict], plan_rows: list[int] | None = None,
                frames_per_camera: dict[str, int] | None = None, top_k: int = 5) -> dict:
        dets = [Detection(d["camera"], str(d["frame"]), d["label"], float(d.get("conf", 1.0)))
                for d in detections]
        ev = camera_evidence(dets, self.M, self.dataset, frames_per_camera, self.conf_thr,
                             self.min_frac, self.extra, self.kw)
        obs = early_fuse(ev)
        prior = plan_prior(self.M, plan_rows) if plan_rows else None
        ranked = self.sc.rank(obs, prior=prior)
        groups = self.sc.groups(self.sc.rank(obs))            # без плана — чистая картина улик
        rep = {
            "equipment": {k: {"name": self.M.keys[k], "presence": round(v, 3),
                              "cameras": sorted(c for c, e in ev.per_camera.items() if k in e)}
                          for k, v in sorted(obs.items(), key=lambda t: -t[1])},
            "cameras": {c: {"frames": ev.frames.get(c, 0), "equipment": e}
                        for c, e in ev.per_camera.items()},
            "unmapped_labels": dict(ev.unmapped),
            "stage_groups": [{"p": round(p, 4), "stages": [self._stage(s) for s in mem],
                              "why": self.sc.explain(mem[0], obs)}
                             for p, mem in groups[:top_k]],
            "sections": [{"p": round(p, 4), **self._stage(s)}
                         for s, p in self.sc.rollup(self.sc.rank(obs))[:3]],
            "zones": [{"cameras": a.cameras, "stages": [self._stage(s) for s in a.members]}
                      for a in late_fuse(ev, self.sc)],
        }
        if plan_rows:
            chk = plan_check(self.sc, obs, plan_rows, self.thr)
            rep["plan"] = {
                "planned": [self._stage(self.M.stages[r]) for r in plan_rows if r in self.M.stages],
                "verdict": chk["verdict"], "log_likelihood_ratio": chk["lr"],
                "best_alternative": self._stage(chk["лучше объясняет"]) if "лучше объясняет" in chk else None,
                "equipment_outside_plan": chk.get("техника вне планового этапа", []),
                "plan_work_confirmed": chk.get("плановая работа подтверждена техникой", []),
                "most_likely_row": self._stage(ranked[0].stage),
            }
        return rep


if __name__ == "__main__":
    import json
    from fusion import load_const_video
    root = Path(__file__).resolve().parents[2]
    dets, frames = load_const_video(root / "data/external/const_video")
    an = SiteAnalyzer(root / "data/stage_equipment.md", dataset="L08")
    rep = an.analyze([d.__dict__ for d in dets], plan_rows=[74], frames_per_camera=frames)
    print(json.dumps({k: rep[k] for k in ("sections", "zones", "plan")}, ensure_ascii=False, indent=1)[:2200])
