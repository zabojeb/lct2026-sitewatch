"""Метрический приор размера: разрешение классов по физическим габаритам.

Идея
----
Техника шириной 35 px различается плохо — стрела автокрана и стрела гусеничного
крана на таком размере это несколько пикселей. Но у них принципиально разные
РЕАЛЬНЫЕ габариты, а камера на площадке неподвижна. Значит, если знать масштаб
(сколько пикселей в метре в данной точке кадра), апparent size объекта
превращается в оценку его длины в метрах — и это признак, который детектор
по текстуре получить не может.

Как получаем масштаб без калибровки камеры
------------------------------------------
Не требуем от пользователя размечать опорные точки. Берём масштаб из самих
детекций объектов известного размера: человек ~1.7 м, легковой автомобиль ~4.4 м,
бытовка ~6 м. При плоском грунте и примерно горизонтальной камере видимый размер
объекта растёт по строке кадра приблизительно линейно, поэтому по нескольким
опорным детекциям строится px_per_m(y) = a*y + b методом наименьших квадратов.

Дальше правдоподобие класса считается по логнормальному распределению вокруг
типичного габарита и перемножается с softmax детектора.

Ограничения (честно)
--------------------
* Нужен хотя бы один опорный объект в кадре. Нет опорных — приор не применяется,
  возвращаем исходные вероятности без изменений.
* Модель плоского грунта. Для котлована глубиной 10 м оценка поедет; поэтому
  приор именно ПЕРЕВЗВЕШИВАЕТ, а не решает — сильный сигнал детектора он не перебьёт.
* На кадрах ДГП камер ~90 разных, калибровать нечего. Приор проектировался под
  боевой режим «одна камера — много дней», где он окупается полностью.
"""
from __future__ import annotations

import math
from typing import NamedTuple


class Scale(NamedTuple):
    """Линейная модель масштаба px_per_m(y) = a*y + b плюс диапазон валидности.

    Диапазон обязателен: вблизи горизонта px_per_m стремится к нулю, а оценка
    длины — к бесконечности. Хранить только (a, b) значит рано или поздно
    выдать объект длиной 143 метра.
    """
    a: float
    b: float
    y_lo: float      # верхняя граница применимости (наименьший y опор минус запас)
    y_hi: float      # нижняя граница

# Типичная габаритная ДЛИНА в метрах (медиана, геометрическое СКО).
# Источник — паспортные габариты распространённых на площадках Москвы моделей.
SIZE_PRIOR_M: dict[str, tuple[float, float]] = {
    "worker":         (0.6, 1.25),
    "truck":          (7.5, 1.30),
    "dump_truck":     (8.5, 1.25),
    "concrete_mixer": (9.0, 1.20),
    "concrete_pump":  (12.0, 1.30),
    "excavator":      (9.5, 1.35),
    "backhoe_loader": (5.8, 1.20),
    "wheel_loader":   (7.0, 1.25),
    "bulldozer":      (5.5, 1.25),
    "roller":         (5.0, 1.25),
    "grader":         (9.0, 1.20),
    "mobile_crane":   (13.0, 1.40),
    "knuckle_crane":  (9.5, 1.30),
    "crawler_crane":  (16.0, 1.45),
    "pile_rig":       (12.0, 1.40),
    "tower_crane":    (45.0, 1.50),   # по вылету стрелы
}

# Опорные объекты: класс -> габарит в метрах. Их детектор находит надёжно.
REFERENCES: dict[str, float] = {"worker": 0.6, "car": 4.4, "truck": 7.5}


MARGIN = 0.4          # допустимая экстраполяция за пределы опор, доля их размаха
MIN_PX_PER_M = 3.0    # жёсткий отказ: ниже этого масштаба оценка бессмысленна
RELIABLE_PX_PER_M = 10.0  # масштаб, начиная с которого приору доверяем полностью


def fit_scale(refs: list[tuple[float, float, str]]) -> Scale | None:
    """Оценить px_per_m(y) по опорным детекциям методом наименьших квадратов.

    refs: список (y_центра, ширина_в_px, класс_опоры).
    Возвращает Scale или None, если опор нет.
    """
    pts = [(y, w / REFERENCES[c]) for y, w, c in refs if c in REFERENCES and w > 0]
    if not pts:
        return None
    ys = [p[0] for p in pts]
    lo, hi = min(ys), max(ys)
    span = max(hi - lo, 1.0)
    lo, hi = lo - MARGIN * span, hi + MARGIN * span

    if len(pts) == 1:
        # одна опора — масштаб считаем постоянным, но только рядом с ней
        return Scale(0.0, pts[0][1], lo, hi)
    n = len(pts)
    sy = sum(p[0] for p in pts); ss = sum(p[1] for p in pts)
    syy = sum(p[0] * p[0] for p in pts); sys_ = sum(p[0] * p[1] for p in pts)
    denom = n * syy - sy * sy
    if abs(denom) < 1e-9:
        return Scale(0.0, ss / n, lo, hi)
    a = (n * sys_ - sy * ss) / denom
    b = (ss - a * sy) / n
    return Scale(a, b, lo, hi)


def _px_per_m(scale: Scale, y_center: float) -> float | None:
    """px_per_m в строке y, либо None если оценке нельзя доверять.

    Два отказа: выход за диапазон опорных строк (экстраполяция) и слишком
    мелкий масштаб (окрестность горизонта, где длина уходит в бесконечность).
    """
    if not (scale.y_lo <= y_center <= scale.y_hi):
        return None
    v = scale.a * y_center + scale.b
    return v if v >= MIN_PX_PER_M else None


def _lognorm_pdf(x: float, mu_m: float, sigma_geom: float) -> float:
    if x <= 0:
        return 1e-12
    s = math.log(sigma_geom)
    z = (math.log(x) - math.log(mu_m)) / s
    return math.exp(-0.5 * z * z) / (x * s * math.sqrt(2 * math.pi))


def apply(class_probs: dict[str, float], y_center: float, width_px: float,
          scale: Scale | None, weight: float = 0.5) -> dict[str, float]:
    """Перевзвесить вероятности классов метрическим приором.

    weight — насколько доверяем приору: 0 отключает, 1 даёт ему полный вес.
    По умолчанию 0.5: приор сдвигает решение в спорных случаях, но не перебивает
    уверенную детекцию.
    """
    if scale is None or not class_probs:
        return class_probs
    px_per_m = _px_per_m(scale, y_center)
    if px_per_m is None:
        return class_probs
    length_m = width_px / px_per_m

    # Чем мельче масштаб, тем больше относительная ошибка оценки длины:
    # у горизонта один пиксель стоит метров. Поэтому вес приора гасим плавно,
    # а не отсекаем порогом — резкая граница дала бы скачок решения на соседних
    # строках кадра.
    weight = weight * min(1.0, px_per_m / RELIABLE_PX_PER_M)
    if weight <= 1e-3:
        return class_probs

    out = {}
    for cls, p in class_probs.items():
        mu, sg = SIZE_PRIOR_M.get(cls, (None, None))
        if mu is None:
            out[cls] = p
            continue
        lik = _lognorm_pdf(length_m, mu, sg)
        out[cls] = p * (lik ** weight)
    z = sum(out.values()) or 1.0
    return {k: v / z for k, v in out.items()}


def estimated_length(y_center: float, width_px: float,
                     scale: Scale | None) -> float | None:
    """Оценка габарита объекта в метрах — для показа пользователю в интерфейсе."""
    if scale is None:
        return None
    px_per_m = _px_per_m(scale, y_center)
    return round(width_px / px_per_m, 1) if px_per_m is not None else None
