"""Датасет для DGP-Net: бокы как обычно + метки этапа и условий съёмки.

Два источника вспомогательных меток
-----------------------------------
1. Сайдкар-файл `aux_labels.json` рядом с датасетом: {имя_файла: {...}}.
   Оттуда берётся этап (размечается человеком, но только для целевого домена —
   внешние датасеты остаются без метки этапа) и сезон (выводится из месяца
   в timestamp кадра, OCR правого нижнего угла).

2. Сам аугментационный пайплайн. Когда мы применяем к кадру группу «ночь» —
   мы тем самым ЗНАЕМ, что метка времени суток для этого сэмпла = «ночь».
   Разметка condition-головы получается бесплатно, без единого клика.

Разделение труда с ultralytics
------------------------------
Геометрию (mosaic, scale, flip, perspective) оставляем ultralytics: она уже
корректно пересчитывает боксы, и дублировать это albumentations'ом — напрашиваться
на рассинхрон. Наша врезка применяет только фотометрию и перекрытия, то есть
ровно те преобразования, которые боксы не двигают и при этом порождают метки
condition-головы.
"""
from __future__ import annotations

import json
import os
import cv2
import numpy as np
import torch
from ultralytics.data.dataset import YOLODataset

import augment as aug_mod
from dgpnet import STAGES, SEASONS, DAYTIMES, WEATHERS

UNKNOWN = -1

# какая группа аугментаций какую метку порождает
DAYTIME_BY_VARIANT = {0: "сумерки", 1: "день", 2: "сумерки", 3: "ночь"}
WEATHER_BY_VARIANT = {0: "осадки", 1: "осадки", 2: "туман", 3: "осадки", 4: "ясно"}
SEASON_BY_VARIANT = {0: "зима", 1: "осень", 2: "лето"}


class ConditionAugment:
    """Фотометрия и перекрытия + возврат меток, которые они порождают.

    Работает поверх label["img"] (HWC, uint8, BGR у ultralytics) и не трогает
    label["instances"], поэтому геометрия остаётся согласованной.

    Ключевая деталь: вариант внутри группы выбираем САМИ и применяем его
    напрямую, а не отдаём выбор A.OneOf. Иначе метка («ночь») и реально
    применённое преобразование («полдень») расходятся, и condition-голова
    учится на шуме — ошибка тем неприятнее, что тихая.
    """

    GROUPS = ("tod", "weather", "season", "camera")
    GROUP_P = (0.35, 0.25, 0.25, 0.15)

    def __init__(self, patches=None, p_photo=0.7, p_occl=0.35):
        self.variants = {
            "tod": _variants(aug_mod.time_of_day(1.0)),
            "weather": _variants(aug_mod.weather(1.0)),
            "season": _variants(aug_mod.season(1.0)),
            "camera": _variants(aug_mod.camera(1.0)),
        }
        self.occl = aug_mod.occlusion(patches, 1.0)
        self.p_photo, self.p_occl = p_photo, p_occl

    def __call__(self, label: dict) -> dict:
        # ultralytics грузит кадры через cv2, то есть в BGR. Наши цветовые
        # преобразования (HueSaturationValue, ToGray) написаны под RGB: на BGR
        # сдвиг тона уводит цвета не туда, и метка «осень» перестаёт
        # соответствовать картинке. Конвертируем на входе и обратно на выходе.
        img = cv2.cvtColor(label["img"], cv2.COLOR_BGR2RGB)
        if np.random.rand() < self.p_photo:
            # ОДНА группа за раз: стек из трёх дал бы кадр, про который нельзя
            # сказать, ночь это или туман, и метка превратилась бы в шум.
            which = np.random.choice(self.GROUPS, p=self.GROUP_P)
            variants = self.variants[which]
            idx = int(np.random.randint(len(variants)))
            img = variants[idx](image=img)["image"]
            if which == "tod":
                label["daytime"] = DAYTIMES.index(DAYTIME_BY_VARIANT[idx])
            elif which == "weather":
                label["weather"] = WEATHERS.index(WEATHER_BY_VARIANT[idx])
            elif which == "season":
                label["season"] = SEASONS.index(SEASON_BY_VARIANT[idx])
            # camera-группа условий съёмки не меняет: метки не трогаем
        if np.random.rand() < self.p_occl:
            img = self.occl(image=img)["image"]
        label["img"] = cv2.cvtColor(np.ascontiguousarray(img), cv2.COLOR_RGB2BGR)
        return label


def _variants(group) -> list:
    """Развернуть A.OneOf в список вариантов.

    Функции групп в augment.py возвращают A.OneOf напрямую, поэтому
    `group.transforms` — это уже список вариантов. Разворачивать на уровень
    глубже нельзя: там лежит внутренность первого варианта (он сам может быть
    Compose из нескольких преобразований), и индексы разъедутся с *_BY_VARIANT.

    Порядок здесь обязан совпадать с порядком в augment.py — на этом держится
    соответствие «применённое преобразование <-> метка». Проверяется в
    _check_variant_maps() при импорте.
    """
    return list(getattr(group, "transforms", [group]))


def _check_variant_maps() -> None:
    """Сверить размеры словарей меток с числом вариантов в augment.py.

    Дешёвая страховка от тихого рассинхрона: добавили вариант погоды в
    augment.py и забыли словарь — падаем сразу, а не обучаем condition-голову
    на перепутанных метках.
    """
    for name, group, table in (
        ("time_of_day", aug_mod.time_of_day(1.0), DAYTIME_BY_VARIANT),
        ("weather", aug_mod.weather(1.0), WEATHER_BY_VARIANT),
        ("season", aug_mod.season(1.0), SEASON_BY_VARIANT),
    ):
        n = len(_variants(group))
        if n != len(table):
            raise RuntimeError(
                f"augment.{name}: {n} вариантов, а в таблице меток {len(table)}. "
                f"Обновите *_BY_VARIANT в dgp_dataset.py."
            )


_check_variant_maps()


class DGPDataset(YOLODataset):
    """YOLODataset + поля stage / season / daytime / weather."""

    def __init__(self, *args, aux_file: str | None = None, cond_aug=None, **kwargs):
        # оба поля нужны ДО super().__init__: он зовёт build_transforms и
        # update_labels_info, которые на них опираются
        self.cond_aug = cond_aug
        self.aux = {}
        if aux_file and os.path.exists(aux_file):
            self.aux = json.load(open(aux_file, encoding="utf-8"))
        super().__init__(*args, **kwargs)

    def update_labels_info(self, label: dict) -> dict:
        label = super().update_labels_info(label)
        stem = os.path.basename(label.get("im_file", ""))
        rec = self.aux.get(stem, {})

        stages = rec.get("stage")
        label["stage"] = ([1.0 if s in stages else 0.0 for s in STAGES]
                          if stages is not None else [0.0] * len(STAGES))
        label["stage_valid"] = 1.0 if stages is not None else 0.0
        label["season"] = _idx(rec.get("season"), SEASONS)
        label["daytime"] = _idx(rec.get("daytime"), DAYTIMES)
        label["weather"] = _idx(rec.get("weather"), WEATHERS)
        return label

    def build_transforms(self, hyp=None):
        """Вставить condition-аугментации ПЕРЕД Format.

        После Format кадр уже превращён в CHW-тензор, а albumentations ждёт
        HWC-массив. Поэтому врезаемся именно сюда, а не в __getitem__: тут
        label["img"] ещё numpy HWC, и геометрия ultralytics (mosaic, scale,
        flip) уже отработала — боксы согласованы, а мы их и не трогаем.
        """
        transforms = super().build_transforms(hyp)
        if self.cond_aug is not None and self.augment:
            transforms.transforms.insert(len(transforms.transforms) - 1, self.cond_aug)
        return transforms

    @staticmethod
    def collate_fn(batch: list[dict]) -> dict:
        """Штатная сборка + стек наших полей.

        Базовый collate_fn оставляет неизвестные ключи кортежами; для лосса
        нужны тензоры, поэтому собираем их здесь явно.
        """
        aux_keys = ("stage", "stage_valid", "season", "daytime", "weather")
        stripped = [{k: v for k, v in b.items() if k not in aux_keys} for b in batch]
        out = YOLODataset.collate_fn(stripped)
        out["stage"] = torch.tensor([b["stage"] for b in batch], dtype=torch.float32)
        out["stage_valid"] = torch.tensor([b["stage_valid"] for b in batch], dtype=torch.float32)
        for k in ("season", "daytime", "weather"):
            out[k] = torch.tensor([b[k] for b in batch], dtype=torch.long)
        return out


def _idx(value, vocab) -> int:
    return vocab.index(value) if value in vocab else UNKNOWN


def season_from_month(month: int) -> str:
    """Сезон по месяцу из timestamp кадра — источник меток без ручной разметки."""
    return {12: "зима", 1: "зима", 2: "зима", 3: "весна", 4: "весна", 5: "весна",
            6: "лето", 7: "лето", 8: "лето", 9: "осень", 10: "осень", 11: "осень"}[month]
