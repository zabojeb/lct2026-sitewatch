"""Сравнение архитектурных вариантов: цена P2-головы и отказа от P5.

Меряем то, что реально ограничивает решение:
  - params / GFLOPs
  - латентность на CPU ноутбука (ТЗ: «стандартные компьютеры, GPU не требуется»)
  - латентность на MPS
  - размер сетки предсказаний на каждом уровне (сколько ячеек приходится
    на объект в 35 px — это и есть обоснование P2)

Точность здесь не меряется: без разметки её измерить нечем. Эта таблица отвечает
на вопрос «сколько стоит», вопрос «сколько даёт» закрывается после разметки.
"""
import json, time, argparse
import torch
from ultralytics import YOLO
from ultralytics.utils.torch_utils import get_flops, model_info


def grid_cells(imgsz, strides, obj_px=35):
    """Сколько ячеек сетки приходится на объект obj_px на каждом уровне.

    Это и есть количественное обоснование P2: на stride 32 объект в 35 px
    занимает одну ячейку — локализовать его там нечем.
    """
    out = {}
    for s in strides:
        s = int(s)
        out[f"P{s.bit_length() - 1}/{s}"] = round(obj_px / s, 2)
    return out


def latency(model, imgsz, device, warmup=1, runs=3):
    """Латентность одного forward.

    ВАЖНО про CPU: это eager-режим PyTorch, а не то, что поедет в прод.
    Боевой инференс на ноутбуке — ONNX Runtime или OpenVINO, там в 3-5 раз
    быстрее. Цифра ниже годится для СРАВНЕНИЯ вариантов между собой, но не как
    абсолютная оценка «влезем ли в ноутбук»: этот замер делается после экспорта.
    """
    m = model.model.to(device).eval()
    x = torch.zeros(1, 3, imgsz, imgsz, device=device)
    with torch.inference_mode():
        for _ in range(warmup):
            m(x)
        if device == "mps":
            torch.mps.synchronize()
        t0 = time.perf_counter()
        for _ in range(runs):
            m(x)
        if device == "mps":
            torch.mps.synchronize()
    return (time.perf_counter() - t0) / runs * 1000  # ms


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nc", type=int, default=16)
    ap.add_argument("--sizes", type=int, nargs="+", default=[960, 1280])
    ap.add_argument("--out", default="ml/runs/bench_arch.json")
    a = ap.parse_args()

    variants = [
        ("yolo26n",        "yolo26n.yaml"),
        ("yolo26s",        "yolo26s.yaml"),
        ("yolo26m",        "yolo26m.yaml"),
        ("yolo26n-p2",     "yolo26n-p2.yaml"),
        ("yolo26s-p2",     "yolo26s-p2.yaml"),
        ("yolo26m-p2",     "yolo26m-p2.yaml"),
        ("yolo26n-p2slim", "ml/configs/models/yolo26n-p2slim.yaml"),
        ("yolo26s-p2slim", "ml/configs/models/yolo26s-p2slim.yaml"),
    ]
    out = {}
    for name, cfg in variants:
        model = YOLO(cfg)
        m = model.model
        rec = {"params_M": round(sum(p.numel() for p in m.parameters()) / 1e6, 3),
               "strides": [int(x) for x in m.stride],
               "cells_per_35px_object": grid_cells(1280, m.stride)}
        for sz in a.sizes:
            rec[f"GFLOPs@{sz}"] = round(float(get_flops(m, imgsz=sz)), 1)
            rec[f"cpu_ms@{sz}"] = round(latency(model, sz, "cpu"), 1)
            try:
                rec[f"mps_ms@{sz}"] = round(latency(model, sz, "mps"), 1)
            except Exception as e:
                rec[f"mps_ms@{sz}"] = f"err {type(e).__name__}"
            m.to("cpu")
        out[name] = rec
        print(name, json.dumps(rec), flush=True)

    json.dump(out, open(a.out, "w"), indent=2)
    print("DONE ->", a.out)
