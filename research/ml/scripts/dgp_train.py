"""Trainer для DGP-Net поверх ultralytics.

Принцип врезки: переопределяем ровно три хука DetectionTrainer и ничего больше.
Всё остальное — расписание LR, EMA, AMP, warmup, чекпоинты, DDP, ранняя
остановка — берём у ultralytics как есть. Чем меньше мы патчим, тем меньше
ломается при обновлении версии.

  get_model      -> DGPNet вместо DetectionModel
  build_dataset  -> DGPDataset (доп. метки + condition-аугментации)
  get_validator  -> валидатор, который дополнительно считает метрики aux-голов

Известное ограничение валидации
-------------------------------
Метки daytime/weather порождаются аугментациями, а на валидации аугментации
выключены — значит `aux/daytime_acc` и `aux/weather_acc` на чистом val-сплите
не считаются (в results.csv их просто нет, и это не баг). Чтобы их измерять,
нужен отдельный «сплит устойчивости»: те же кадры, прогнанные через
ConditionAugment с зафиксированным seed. Он же служит набором для замера
деградации mAP по условиям — см. docs/ML_PLAN.md, раздел про ablation.

Имена слагаемых лосса подхватываются автоматически: ultralytics берёт
loss_names из словаря, который вернул criterion на первом батче, а DGPLoss
дописывает туда stage_loss / season_loss / daytime_loss / weather_loss.

Запуск:
    python ml/scripts/dgp_train.py --data ml/configs/dgp.yaml \
        --model yolo26s-p2.yaml --imgsz 1280 --epochs 120 --batch 8
"""
from __future__ import annotations

import argparse
import os
import sys
from copy import copy

import numpy as np
import torch
from ultralytics.data.build import build_dataloader  # noqa: F401  (используется базой)
from ultralytics.models import yolo
from ultralytics.models.yolo.detect import DetectionTrainer, DetectionValidator
from ultralytics.utils import DEFAULT_CFG, LOGGER, colorstr
from ultralytics.utils.torch_utils import unwrap_model

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dgpnet import DGPNet, STAGES, SEASONS, DAYTIMES, WEATHERS  # noqa: E402
from dgp_dataset import DGPDataset, ConditionAugment  # noqa: E402


def load_occluder_patches(img_dir: str, n: int = 40) -> list:
    """Нарезать фрагменты площадок для реалистичных перекрытий.

    Берём куски из самих обучающих кадров: перекрывающий объект получает
    текстуру стройплощадки, а не становится чёрным прямоугольником, на который
    модель быстро научится не обращать внимания.
    """
    import glob
    import cv2
    files = sorted(glob.glob(os.path.join(img_dir, "*")))[:n]
    patches = []
    for f in files:
        im = cv2.imread(f)
        if im is None:
            continue
        H, W = im.shape[:2]
        patches += [im[int(H * 0.72):, : W // 3], im[: H // 5, W // 2:],
                    im[H // 3: H // 2, : W // 4]]
    return [p for p in patches if p.size]


class DGPValidator(DetectionValidator):
    """Штатная валидация детекции + точность вспомогательных голов.

    Aux-метрики считаются на тех же forward'ах, что и детекция: включаем
    model.return_aux, и логиты появляются в model.last_aux. Второго прохода
    по валидации не делаем.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dgp = None
        self._aux_hits = {}
        self._aux_total = {}
        self._stage_tp = self._stage_fp = self._stage_fn = 0

    def init_metrics(self, model):
        """Единственное место, где валидатор получает модель.

        В ultralytics `model` внутри __call__ — локальная переменная, и в
        self её нет. Хук init_metrics вызывается ровно с ней, поэтому ссылку
        сохраняем здесь и включаем aux, чтобы логиты появились в last_aux
        на тех же forward'ах, что и детекция.
        """
        super().init_metrics(model)
        m = unwrap_model(model)
        self._dgp = m if isinstance(m, DGPNet) else None
        if self._dgp is not None:
            self._dgp.return_aux = True

    def update_metrics(self, preds, batch):
        super().update_metrics(preds, batch)
        aux = getattr(self._dgp, "last_aux", None) if self._dgp is not None else None
        if aux is None:
            return

        for key, vocab in (("season", SEASONS), ("daytime", DAYTIMES), ("weather", WEATHERS)):
            if key not in batch:
                continue
            tgt = batch[key].to(aux[key].device)
            mask = tgt >= 0                      # -1 = метка неизвестна
            if mask.any():
                pred = aux[key].argmax(1)
                self._aux_hits[key] = self._aux_hits.get(key, 0) + int((pred[mask] == tgt[mask]).sum())
                self._aux_total[key] = self._aux_total.get(key, 0) + int(mask.sum())

        # этапы: multi-label -> считаем micro-F1 по порогу 0.5
        if "stage" in batch:
            valid = batch.get("stage_valid")
            rows = (valid > 0) if valid is not None else torch.ones(len(batch["stage"]), dtype=torch.bool)
            if rows.any():
                p = (aux["stage"][rows].sigmoid() > 0.5)
                t = batch["stage"][rows].to(p.device) > 0.5
                self._stage_tp += int((p & t).sum())
                self._stage_fp += int((p & ~t).sum())
                self._stage_fn += int((~p & t).sum())

    def get_stats(self):
        stats = super().get_stats()
        for key in ("season", "daytime", "weather"):
            if self._aux_total.get(key):
                stats[f"aux/{key}_acc"] = self._aux_hits[key] / self._aux_total[key]
        if self._stage_tp + self._stage_fp + self._stage_fn:
            prec = self._stage_tp / max(self._stage_tp + self._stage_fp, 1)
            rec = self._stage_tp / max(self._stage_tp + self._stage_fn, 1)
            stats["aux/stage_f1"] = 2 * prec * rec / max(prec + rec, 1e-9)
        self._aux_hits, self._aux_total = {}, {}
        self._stage_tp = self._stage_fp = self._stage_fn = 0
        return stats


class DGPTrainer(DetectionTrainer):
    """DetectionTrainer с подменой модели, датасета и валидатора."""

    def __init__(self, cfg=DEFAULT_CFG, overrides=None, _callbacks=None):
        overrides = overrides or {}
        # свои гиперпараметры снимаем ДО вызова базы: ultralytics валидирует
        # набор ключей и на незнакомых ругается
        self.aux_file = overrides.pop("aux_file", None)
        self.w_stage = float(overrides.pop("w_stage", 0.3))
        self.w_cond = float(overrides.pop("w_cond", 0.1))
        self.use_cond_aug = bool(overrides.pop("cond_aug", True))
        super().__init__(cfg, overrides, _callbacks)
        self._patches = None

    def get_model(self, cfg=None, weights=None, verbose=True):
        model = DGPNet(cfg or "yolo26s-p2.yaml", nc=self.data["nc"],
                       ch=self.data["channels"], verbose=verbose)
        model.w_stage, model.w_cond = self.w_stage, self.w_cond
        if weights:
            # strict=False: backbone из COCO-весов переносится полностью, шея и
            # голова P2 — нет (другая нумерация слоёв и размерности конкатенаций).
            # Это ожидаемо, см. docs/ARCH.md.
            model.load(weights)
        return self.set_model_names_for_load(model)

    def build_dataset(self, img_path, mode="train", batch=None):
        gs = max(int(unwrap_model(self.model).stride.max()), 32)
        cond = None
        if mode == "train" and self.use_cond_aug:
            if self._patches is None:
                self._patches = load_occluder_patches(img_path)
                LOGGER.info(f"{colorstr('DGP:')} нарезано {len(self._patches)} фрагментов-перекрытий")
            cond = ConditionAugment(self._patches)
        return DGPDataset(
            img_path=img_path,
            imgsz=self.args.imgsz,
            batch_size=batch,
            augment=mode == "train",
            hyp=self.args,
            rect=self.args.rect or (mode == "val"),
            cache=self.args.cache or None,
            single_cls=self.args.single_cls or False,
            stride=gs,
            pad=0.0 if mode == "train" else 0.5,
            prefix=colorstr(f"{mode}: "),
            task=self.args.task,
            classes=self.args.classes,
            data=self.data,
            fraction=self.args.fraction if mode == "train" else 1.0,
            aux_file=self.aux_file,
            cond_aug=cond,
        )

    def get_validator(self):
        return DGPValidator(self.test_loader, save_dir=self.save_dir,
                            args=copy(self.args), _callbacks=self.callbacks)


def main():
    ap = argparse.ArgumentParser(description="Обучение DGP-Net")
    ap.add_argument("--data", required=True, help="yaml датасета в формате ultralytics")
    ap.add_argument("--model", default="yolo26s-p2.yaml")
    ap.add_argument("--weights", default="yolo26s.pt", help="стартовые веса (переносится backbone)")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default="0")
    ap.add_argument("--aux-file", default=None, help="json с метками этапа/сезона")
    ap.add_argument("--w-stage", type=float, default=0.3)
    ap.add_argument("--w-cond", type=float, default=0.1)
    ap.add_argument("--no-cond-aug", action="store_true")
    ap.add_argument("--name", default="dgpnet")
    ap.add_argument("--close-mosaic", type=int, default=20,
                    help="отключить mosaic за N эпох до конца: он вредит локализации мелких объектов")
    a = ap.parse_args()

    trainer = DGPTrainer(overrides=dict(
        model=a.model, data=a.data, imgsz=a.imgsz, epochs=a.epochs, batch=a.batch,
        device=a.device, name=a.name, pretrained=a.weights, close_mosaic=a.close_mosaic,
        aux_file=a.aux_file, w_stage=a.w_stage, w_cond=a.w_cond,
        cond_aug=not a.no_cond_aug,
    ))
    trainer.train()


if __name__ == "__main__":
    main()
