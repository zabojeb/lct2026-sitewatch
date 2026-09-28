"""DGP-Net — детектор с дополнительными головами на общем backbone.

Зачем это, а не «YOLO + отдельный VLM»
--------------------------------------
Детектор отвечает на вопрос «какая техника в кадре». Для сопоставления с графиком
нужен ещё ответ на «какой этап тут вообще идёт»: состав техники у этапов 12.3.1
(котлован) и 12.3.7 (земляные работы) почти совпадает, различает их вид сцены —
разработан ли котлован, есть ли опалубка, смонтирован ли каркас. Обычно за этим
идут к VLM, но VLM на 4B параметров не влезает в требование ТЗ «демонстрируется
на обычном ноутбуке» и стоит сотни миллисекунд на кадр.

Признаки для ответа на оба вопроса backbone уже вычислил. Достаточно снять с P5
ещё две головы — это ~0.3 МБ параметров и единицы процентов времени.

Головы
------
1. detect     — штатная голова YOLO26 (P2/P3/P4[/P5]).
2. stage      — multi-label по наблюдаемым этапам. Multi-label, а не softmax:
                на площадке одновременно идут несколько этапов (свайные работы
                в одном углу, котлован в другом).
3. condition  — вспомогательная: сезон (4) x время суток (3) x погода (4).
                Нужна по двум причинам. Во-первых, даёт модели явный сигнал о
                домене и работает как регуляризатор. Во-вторых — и это главное —
                её разметка бесплатна: метки берём из аугментационного пайплайна
                (мы знаем, что применили) и из месяца в timestamp кадра. Ноль
                ручной разметки на целую задачу.

Почему condition-голова окупается на практике: она даёт интерфейсу основание
написать «уверенность снижена: ночная съёмка в снегопад», вместо молчаливой
выдачи пустого списка техники. Критерий 8.3 — обоснованность предупреждений.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from ultralytics.nn.tasks import DetectionModel
from ultralytics.utils.loss import E2EDetectLoss

STAGES = [
    "подготовка_территории", "снос", "котлован", "сваи_бурение",
    "монолит_подземный", "монолит_надземный", "фасад_стены",
    "дорожная_одежда", "простой",
]
SEASONS = ["зима", "весна", "лето", "осень"]
DAYTIMES = ["день", "сумерки", "ночь"]
WEATHERS = ["ясно", "облачно", "осадки", "туман"]


class AuxHead(nn.Module):
    """Лёгкая голова классификации поверх карты признаков P5.

    Свёртка 1x1 для сжатия каналов -> GAP -> линейный слой. Сознательно без
    скрытых полносвязных слоёв: на нашем объёме данных (тысячи кадров, не
    миллионы) более ёмкая голова переобучится раньше, чем что-то выучит.
    """

    def __init__(self, in_ch: int, out_dims: dict[str, int], hidden: int = 128):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Conv2d(in_ch, hidden, 1, bias=False),
            nn.BatchNorm2d(hidden),
            nn.SiLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
        )
        self.heads = nn.ModuleDict({k: nn.Linear(hidden, v) for k, v in out_dims.items()})

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        z = self.proj(x)
        return {k: h(z) for k, h in self.heads.items()}


class DGPNet(DetectionModel):
    """YOLO26 + stage/condition головы.

    Врезаемся в forward один раз: запоминаем признаки предпоследнего уровня шеи
    (P5 после C2PSA) и пропускаем их через AuxHead. Детект-ветвь не трогаем —
    любые веса YOLO26 грузятся как есть, а головы инициализируются с нуля.
    """

    def __init__(self, cfg="yolo26s-p2.yaml", ch=3, nc=None, verbose=True,
                 aux_layer: int = 10):
        super().__init__(cfg, ch, nc, verbose)
        self.aux_layer = aux_layer          # индекс слоя backbone, с которого снимаем признаки
        self._aux_feat: torch.Tensor | None = None
        self.last_aux: dict[str, torch.Tensor] | None = None
        self.return_aux = False             # включается валидатором, чтобы считать aux-метрики
        self.w_stage, self.w_cond = 0.3, 0.1
        self.model[aux_layer].register_forward_hook(self._grab)

        # один прогон, чтобы узнать число каналов на aux_layer. Идём через
        # _predict_once, а не forward: forward уже переопределён и полезет за
        # self.aux, которого на этом шаге ещё нет.
        with torch.no_grad():
            self._predict_once(torch.zeros(1, ch, 256, 256))
        aux_ch = self._aux_feat.shape[1]

        self.aux = AuxHead(aux_ch, {
            "stage": len(STAGES),
            "season": len(SEASONS),
            "daytime": len(DAYTIMES),
            "weather": len(WEATHERS),
        })

    def _grab(self, module, inp, out):
        self._aux_feat = out

    def forward(self, x, *args, **kwargs):
        """Возвращает РОВНО то же, что обычный DetectionModel.

        Логиты вспомогательных голов кладём в self.last_aux, а не в возвращаемое
        значение. Это сознательное решение: ultralytics в десятке мест —
        validator, exporter, predictor, callbacks — ожидает от forward штатную
        структуру. Возврат кортежа потребовал бы патчить каждое из этих мест,
        а атрибут не ломает ничего.
        """
        out = super().forward(x, *args, **kwargs)
        # `aux` появляется в конце __init__, а базовый класс вызывает forward
        # раньше — при расчёте stride. До этого момента ведём себя как обычный YOLO.
        if getattr(self, "aux", None) is None:
            return out
        self.last_aux = self.aux(self._aux_feat) if (self.training or self.return_aux) else None
        return out

    def init_criterion(self):
        """Точка, через которую BaseModel.loss() получает функцию потерь."""
        return DGPLoss(self, w_stage=self.w_stage, w_cond=self.w_cond)


class DGPLoss:
    """Детекционный лосс YOLO26 + BCE по этапам + CE по условиям съёмки.

    Веса подобраны так, чтобы вспомогательные задачи не перетягивали градиент:
    детекция — основная задача, остальное обязано ей помогать, а не конкурировать.
    Кандидат на ablation: при w_stage > ~0.5 детекция начинает проседать.
    """

    def __init__(self, model, w_stage=0.3, w_cond=0.1):
        self.det = E2EDetectLoss(model)
        self.model = model
        self.w_stage, self.w_cond = w_stage, w_cond
        # reduction="none": часть сэмплов может быть без меток этапа, усредняем сами
        self.bce = nn.BCEWithLogitsLoss(reduction="none")
        self.ce = nn.CrossEntropyLoss(ignore_index=-1)

    def __call__(self, preds, batch):
        loss, items = self.det(preds, batch)
        aux = getattr(self.model, "last_aux", None)
        if aux is None:
            return loss, items   # aux отключены — ведём себя как обычный детектор

        # Набор ключей обязан быть ОДИНАКОВЫМ на каждом батче: ultralytics
        # фиксирует loss_names по первому батчу и потом усредняет по этим ключам.
        # Если в батче не оказалось ни одной валидной метки погоды и мы просто
        # не добавим weather_loss — на следующем батче будет KeyError.
        zero = torch.zeros((), device=loss.device if torch.is_tensor(loss) else None)
        for k in ("stage_loss", "season_loss", "daytime_loss", "weather_loss"):
            items[k] = zero.clone()

        # Этапы: multi-label. `stage_valid` отмечает сэмплы, для которых метка
        # этапа вообще известна: размечать этап для каждого кадра внешнего
        # датасета мы не будем, и эти кадры не должны портить голову.
        if "stage" in batch:
            per = self.bce(aux["stage"], batch["stage"].float()).mean(dim=1)
            valid = batch.get("stage_valid")
            if valid is not None:
                valid = valid.to(per.device).float()
                denom = valid.sum().clamp(min=1.0)
                l_stage = (per * valid).sum() / denom
            else:
                l_stage = per.mean()
            loss = loss + self.w_stage * l_stage
            items["stage_loss"] = l_stage.detach()


        # Условия съёмки: три независимых softmax, -1 = метка неизвестна
        for key in ("season", "daytime", "weather"):
            if key in batch:
                l = self.ce(aux[key], batch[key].to(aux[key].device).long())
                # все метки в батче = -1 -> CE возвращает nan; слагаемое пропускаем,
                # но ключ остаётся нулевым (см. выше про стабильность loss_names)
                if torch.isfinite(l):
                    loss = loss + self.w_cond * l
                    items[f"{key}_loss"] = l.detach()
        return loss, items
