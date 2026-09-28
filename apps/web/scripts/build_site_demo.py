"""Демо-проекты раздела «Площадка» из данных прототипа СтройКонтур v22.

Из prototypes/stroykontur-v22/dist берётся только то, что можно показать честно:

* «Площадка №8» — 22 реальных кадра пяти камер датасета
  nickpudovkin/const-video-v2i-yolo26 с их настоящим временем съёмки;
* «Torre H» — 5 реальных кадров долгосрочного наблюдения датасета
  nickpudovkin/dataset-object-identication-training-construction;
* «Сценарий смены этапов» — 6 кадров, где техника вставлена поверх реальных
  фонов. Весь проект помечен как синтетический.

Рамки — эталонная разметка датасетов (source=annotation) или синтетика
(source=synthetic); результатов модели здесь нет. Прототип переписывал время
кадров на сетку 08:00 + 20 мин и сводил разные площадки в одну; здесь время
остаётся исходным, а площадки — раздельными.

    python apps/web/scripts/build_site_demo.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "prototypes/stroykontur-v22/dist"
MAPPING = ROOT / "prototypes/stroykontur-v22/mapping/stage_equipment_map.json"

# русские названия классов методики → слаги интерфейса
RU_TO_SLUG = {
    "самосвал": "dump-truck", "экскаватор": "excavator", "каток": "roller",
    "кран-манипулятор": "manipulator", "бетоносмеситель": "mixer", "бульдозер": "bulldozer",
    "грузовик": "truck", "автокран": "mobile-crane", "башенный кран": "tower-crane",
    "буровая": "drill", "бетононасос": "pump", "погрузчик": "loader",
    "автогрейдер": "grader", "асфальтоукладчик": "paver",
}
OUT = ROOT / "apps/web/static/demo/site"

DATASET_8 = "https://www.kaggle.com/datasets/nickpudovkin/const-video-v2i-yolo26"
DATASET_10 = "https://www.kaggle.com/datasets/nickpudovkin/dataset-object-identication-training-construction"

# настройки камер прототипа: какие проверки включены на каком ракурсе
CAMERA_RULES = {
    "Камера 4": {"checkExtra": True, "checkZones": True, "trackIdle": []},
    "Камера 5": {"checkExtra": True, "checkZones": True, "trackIdle": []},
    "Камера 7": {"checkExtra": True, "checkZones": True, "trackIdle": []},
    "Камера 8": {"checkExtra": True, "checkZones": True, "trackIdle": ["excavator"]},
    "Камера 9": {"checkExtra": True, "checkZones": True, "trackIdle": []},
}

# пример запретной зоны из прототипа (камера 9) — правило-образец, а не результат алгоритма
EXAMPLE_ZONE = {
    "id": "zone-storage-example",
    "name": "Склад материалов",
    "equipment": ["excavator"],
    "points": [[67, 37], [98, 37], [98, 97], [81, 96], [66, 59]],
    "example": True,
}


def camera_id(name: str) -> str:
    digits = "".join(ch for ch in name if ch.isdigit())
    return f"cam-{digits}" if digits else "cam-" + name.lower().replace(" ", "-")


def copy_image(src_rel: str, project: str) -> tuple[str, str | None]:
    """Копирует кадр и его лёгкое превью; возвращает веб-пути."""
    src = SRC / src_rel
    dst = OUT / "img" / project / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    preview = SRC / "assets/previews" / Path(src_rel).relative_to("assets").with_suffix(".jpg")
    preview_url = None
    if preview.exists():
        pdst = OUT / "img" / project / "previews" / preview.name
        pdst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(preview, pdst)
        preview_url = f"/demo/site/img/{project}/previews/{preview.name}"
    return f"/demo/site/img/{project}/{src.name}", preview_url


def boxes(items: list[dict], source: str) -> list[dict]:
    out = []
    for b in items:
        out.append({
            "slug": b["classSlug"],
            "label": b["className"],
            "bbox": [round(v, 5) for v in b["bbox"]],
            "confidence": b.get("confidence", 1),
            "source": "synthetic" if b.get("synthetic") else source,
        })
    return out


def methodology() -> dict:
    """25 профилей «этап → техника» и сопоставление всех 377 строк XLSX из прототипа."""
    d = json.loads(MAPPING.read_text(encoding="utf-8"))
    slug = lambda names: [RU_TO_SLUG[n] for n in names]
    profiles = [{
        "id": p["id"], "name": p["name"],
        "required": {c: 1 for c in slug(p["required"])},
        "anyOf": [slug(group) for group in p["required_any"]],
        "optional": slug(p["optional"]),
        "gesn": p.get("gesn_tables", []), "note": p.get("note", ""),
        "windowMinutes": p.get("observation_window_minutes", 30),
        "sourceRefs": p.get("source_refs", []),
    } for p in d["profiles"]]
    stages = [{"row": r["row"], "code": r["code"], "name": " ".join(r["name"].split()),
               "l1": r["l1"], "l2": r["l2"], "profileId": r["profile_id"],
               "confidence": r["confidence"]} for r in d["rows"]]
    return {"method": d["methodology"], "sources": d["official_sources"],
            "profiles": profiles, "stages": stages}


def stage(row: int, days: int, rows: dict) -> dict:
    """Этап плана = строка XLSX с её профилем техники."""
    r = rows[row]
    return {"id": f"row-{row}", "name": r["name"], "days": days, "profileId": r["profileId"], "row": row}


def build() -> None:
    data = json.loads((SRC / "data/real-session.json").read_text(encoding="utf-8"))
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    projects = []
    method = methodology()
    rows = {r["row"]: r for r in method["stages"]}

    # --- Площадка №8: пять камер одного дня, настоящее время кадров -------------------------
    frames, cams = [], {}
    for item in sorted(data["incidentEvidence"], key=lambda x: x["timestamp"]):
        image, preview = copy_image(item["image"], "site-8")
        cid = camera_id(item["camera"])
        cams[cid] = item["camera"]
        vlm = data.get("vlmObservations", {}).get(item["id"])
        frames.append({
            "id": item["id"],
            "cameraId": cid,
            "timestamp": item["timestamp"],
            "image": image,
            "preview": preview,
            "boxes": boxes(item["boxes"], "annotation"),
            **({"vlm": {"model": vlm["model"], "code": vlm["scene_code"], "scene": vlm["scene"]}} if vlm else {}),
        })
    cross = data.get("crossCamera", {})
    projects.append({
        "id": "site-8",
        "name": "Площадка №8",
        "subtitle": "5 камер · смена 25.07.2024",
        "kind": "dataset",
        "provenance": {
            "boxes": "annotation",
            "text": "Реальные кадры пяти камер одной площадки. Рамки — эталонная разметка датасета, "
                    "не результат модели. Время кадров исходное: камеры снимали в разные часы смены.",
            "sources": [{"name": "nickpudovkin/const-video-v2i-yolo26", "url": DATASET_8}],
        },
        "shiftHours": 12,
        "cameras": [{"id": cid, "name": name, "rules": CAMERA_RULES.get(name, {})}
                    for cid, name in sorted(cams.items(), key=lambda kv: int(kv[0].split("-")[1]))],
        "frames": frames,
        "plan": {"start": "2024-05-27", "example": True, "stages": [
            stage(47, 21, rows), stage(74, 28, rows), stage(85, 45, rows), stage(87, 40, rows)]},
        "zones": {"cam-9": [EXAMPLE_ZONE]},
        "geometry": {
            "note": "SIFT + отбор выбросов RANSAC по парам кадров; статистика расчёта прототипа.",
            "cameras": [{"cameraId": camera_id(c["cameraId"]), "keypoints": c["keypoints"],
                         "matches": c["matches"], "inliers": c["inliers"],
                         "inlierRatio": c["inlierRatio"], "rmse": c["rmse"], "spanSec": c["spanSec"]}
                        for c in data.get("calibration", [])],
            "pairs": [
                {"from": "cam-8", "to": "cam-9", "kind": "epipolar",
                 **{k: cross["epipolar"][k] for k in ("keypoints", "matches", "inliers", "inlierRatio", "rmse")}},
                {"from": "cam-9", "to": "cam-8", "kind": "homography",
                 **{k: cross["mapHomography"][k] for k in ("keypoints", "matches", "inliers", "inlierRatio", "rmse", "matrix")}},
            ] if cross else [],
        },
    })

    # --- Torre H: одна камера, три месяца наблюдения ---------------------------------------
    frames = []
    for item in data["session"]["frames"]:
        image, preview = copy_image(item["image"], "torre-h")
        frames.append({"id": Path(item["image"]).stem, "cameraId": "cam-torre-h",
                       "timestamp": item["timestamp"], "image": image, "preview": preview,
                       "boxes": boxes(item["boxes"], "annotation")})
    projects.append({
        "id": "torre-h",
        "name": "Torre H",
        "subtitle": "1 камера · ноябрь 2020 — февраль 2021",
        "kind": "dataset",
        "provenance": {
            "boxes": "annotation",
            "text": "Долгосрочное наблюдение одной площадки. Рамки — эталонная разметка датасета, "
                    "не результат модели.",
            "sources": [{"name": "nickpudovkin/dataset-object-identication-training-construction", "url": DATASET_10}],
        },
        "shiftHours": 24 * 120,
        "cameras": [{"id": "cam-torre-h", "name": "Камера Torre H",
                     "rules": {"checkExtra": True, "checkZones": True, "trackIdle": []}}],
        "frames": frames,
        "plan": {"start": "2020-09-28", "example": True, "stages": [
            stage(47, 21, rows), stage(74, 28, rows), stage(85, 35, rows), stage(88, 45, rows)]},
        "zones": {},
        "geometry": None,
    })

    # --- Синтетический сценарий смены этапов ------------------------------------------------
    frames, cams = [], {}
    for item in data["stageTimeline"]:
        if not any(b.get("synthetic") for b in item["boxes"]):
            continue
        image, preview = copy_image(item["image"], "scenario")
        cid = camera_id(item["camera"])
        cams[cid] = item["camera"]
        frames.append({"id": item["id"], "cameraId": cid, "timestamp": item["timestamp"],
                       "image": image, "preview": preview, "boxes": boxes(item["boxes"], "synthetic")})
    projects.append({
        "id": "scenario",
        "name": "Сценарий смены этапов",
        "subtitle": "синтетика · котлован → сваи",
        "kind": "synthetic",
        "provenance": {
            "boxes": "synthetic",
            "text": "Синтетический сценарий: изображения техники вставлены поверх реальных фонов, "
                    "рамки известны точно. Нужен, чтобы показать смену этапов и расчёт отставания.",
            "sources": [],
        },
        "shiftHours": 24,
        "cameras": [{"id": cid, "name": name,
                     "rules": {"checkExtra": True, "checkZones": True, "trackIdle": []}}
                    for cid, name in sorted(cams.items())],
        "frames": frames,
        "plan": {"start": "2020-09-21", "example": True, "stages": [
            stage(47, 21, rows), stage(74, 28, rows), stage(85, 60, rows)]},
        "zones": {},
        "geometry": None,
    })

    (OUT / "methodology.json").write_text(json.dumps(method, ensure_ascii=False) + "\n", encoding="utf-8")
    for p in projects:
        (OUT / f"{p['id']}.json").write_text(json.dumps(p, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    index = [{k: p[k] for k in ("id", "name", "subtitle", "kind")} |
             {"frames": len(p["frames"]), "cameras": len(p["cameras"])} for p in projects]
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"{len(projects)} проекта, {sum(len(p['frames']) for p in projects)} кадров, {size / 1e6:.1f} МБ → {OUT}")


if __name__ == "__main__":
    build()
