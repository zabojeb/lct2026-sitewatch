"""Copy-paste аугментация: вставка вырезанной техники в реальные кадры площадок.

Зачем именно на этой задаче
---------------------------
Метод известный (Ghiasi et al., 2021), но здесь он попадает в три наши проблемы сразу:

1. **Масштаб.** Медианный объект — 35 px, разброс огромен. Вставляя ОДНУ И ТУ ЖЕ
   машину с размером от 20 до 250 px, мы покрываем весь диапазон. Ключевое отличие
   от обычного resize: меняется масштаб МАШИНЫ, а не кадра. Resize всего кадра
   двигает и фон, и сохраняет соотношение «машина / сцена» — то есть как раз не
   моделирует «машина дальше от камеры».
2. **Редкие классы.** Катка, грейдера и крана-манипулятора мало в любом датасете.
   Вставить их можно сколько угодно раз.
3. **Разметка бесплатна и точна.** Мы сами положили объект — знаем класс и маску
   с точностью до пикселя. Это единственный источник разметки, который не стоит
   человеко-часов.

Плюс сценарий «часть площадки закрыта»: вставляя машину частично за существующий
объект, получаем перекрытие с корректной меткой.

Три вещи, без которых метод ломается
------------------------------------
* **Откуда берутся вырезки.** Каталожные PNG техники — это съёмка с уровня земли,
  фронтально, при студийном свете. Наш домен — верхний ракурс, 35 px, дымка.
  Вставив каталожное фото, мы научим модель, что экскаватор выглядит сбоку с
  уровня глаз — ровно тому, чего она в кадре не увидит. Поэтому основной источник —
  вырезки из САМИХ кадров площадок (их даёт preannotate.py по маскам YOLOE), а
  также AIDCON (съёмка с БПЛА). Каталожные PNG допустимы только для классов, где
  своих примеров нет вовсе, и только мелко и сильно деградированно.
* **Геометрическая правдоподобность.** Размер вставки берём из эмпирической
  модели «типичная высота объекта в строке y», построенной по уже имеющейся
  разметке. Иначе получим двухметровый экскаватор на переднем плане и испортим
  метрический приор из scale_prior.py.
* **Вид склейки.** Резкий край, несовпадающий свет и отсутствие тени — это
  признаки, по которым модель научится находить «вставку», а не технику. Поэтому
  растушёвка альфы, гармонизация цвета под локальный фон, дымка по глубине,
  согласование резкости, отбрасываемая тень и общий JPEG в конце.

Валидация: синтетические кадры НИКОГДА не попадают в val. Иначе мы измеряем
качество собственного генератора.
"""
from __future__ import annotations

import glob
import os
import random

import cv2
import numpy as np


class CutoutBank:
    """Вырезки техники с альфой, сгруппированные по классу."""

    def __init__(self, root: str, classes: list[str] | None = None, min_px: int = 24,
                 min_instances: int = 5, verbose: bool = True):
        """min_instances — порог на число вырезок в классе.

        Класс, представленный одной-двумя вырезками, вставлять НЕЛЬЗЯ. Если эта
        единственная вырезка ошибочна (а предразметка open-vocab ошибается —
        у нас единственный `roller` оказался бетонной трубой), copy-paste
        размножит ошибку по всему синтетическому корпусу. Разнообразие источника
        здесь важнее его количества: одна картинка, вставленная 500 раз, учит
        модель узнавать эту картинку, а не класс.
        """
        self.by_class: dict[str, list[str]] = {}
        self.dropped: dict[str, int] = {}
        for d in sorted(glob.glob(os.path.join(root, "*"))):
            if not os.path.isdir(d):
                continue
            cls = os.path.basename(d)
            if classes and cls not in classes:
                continue
            files = sorted(glob.glob(os.path.join(d, "*.png")))
            if len(files) >= min_instances:
                self.by_class[cls] = files
            elif files:
                self.dropped[cls] = len(files)
        self.min_px = min_px
        self.min_instances = min_instances
        self._cache: dict[str, np.ndarray] = {}
        if verbose and self.dropped:
            print("не используются (мало вырезок, порог "
                  f"{min_instances}): " +
                  ", ".join(f"{c}×{n}" for c, n in sorted(self.dropped.items())))

    def __len__(self):
        return sum(len(v) for v in self.by_class.values())

    def sample(self, cls: str | None = None) -> tuple[str, np.ndarray] | None:
        if not self.by_class:
            return None
        cls = cls or random.choice(list(self.by_class))
        files = self.by_class.get(cls)
        if not files:
            return None
        path = random.choice(files)
        img = self._cache.get(path)
        if img is None:
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is None or img.ndim != 3 or img.shape[2] != 4:
                return None
            self._cache[path] = img
        if min(img.shape[:2]) < self.min_px:
            return None
        return cls, img


def fit_size_vs_y(labels: list[tuple[float, float]], img_h: int) -> tuple[float, float]:
    """Эмпирическая модель «высота бокса в пикселях как функция строки y».

    labels: список (y_центра_px, высота_px) по уже размеченным объектам.
    Возвращает (a, b) для h(y) = a*y + b. Заменяет калибровку камеры: нам нужна
    не метрика, а правдоподобный размер вставки на данной высоте кадра.
    """
    if len(labels) < 4:
        return (0.0, img_h * 0.06)          # запасной вариант: 6 % высоты кадра
    ys = np.array([p[0] for p in labels], float)
    hs = np.array([p[1] for p in labels], float)
    a, b = np.polyfit(ys, hs, 1)
    if a <= 0:                               # вырожденный случай — размер не растёт вниз
        return (0.0, float(np.median(hs)))
    return float(a), float(b)


def _harmonise(patch_bgr: np.ndarray, alpha: np.ndarray, bg_region: np.ndarray,
               strength: float = 0.45) -> np.ndarray:
    """Подогнать цветовую статистику вставки под локальный фон.

    Сдвигаем среднее и масштабируем разброс по каналам в сторону фона.
    strength=0 оставляет исходный вид, 1 полностью подменяет статистику.
    Частичная сила важна: полное выравнивание убивает фирменную окраску
    (оранжевый Hitachi, бирюзовый Kobelco), а она — полезный признак.
    """
    m = alpha > 0
    if m.sum() < 10 or bg_region.size == 0:
        return patch_bgr
    out = patch_bgr.astype(np.float32)
    bg = bg_region.reshape(-1, 3).astype(np.float32)
    bg_mu, bg_sd = bg.mean(0), bg.std(0) + 1e-6
    fg_mu = out[m].mean(0)
    fg_sd = out[m].std(0) + 1e-6
    gain = np.clip(bg_sd / fg_sd, 0.6, 1.6)
    target = (out - fg_mu) * gain + bg_mu
    out[m] = (1 - strength) * out[m] + strength * target[m]
    return np.clip(out, 0, 255).astype(np.uint8)


def _brand_colour_jitter(patch_bgr: np.ndarray, alpha: np.ndarray,
                         hue_deg: float = 18.0) -> np.ndarray:
    """Сдвиг окраски МАШИНЫ, не всего кадра.

    Спецтехника окрашена по производителю: Hitachi оранжевая, Komatsu жёлтая,
    Kobelco бирюзовая, Liebherr синяя. Модель, обученная в основном на жёлтых
    машинах, на бирюзовой проседает. Джиттер по тону применяем к вставке
    отдельно — при аугментации всего кадра так сделать нельзя.
    """
    hsv = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV).astype(np.int16)
    m = alpha > 0
    dh = int(random.uniform(-hue_deg, hue_deg) / 2)     # OpenCV: hue в [0,180)
    ds = int(random.uniform(-25, 25))
    hsv[..., 0] = np.where(m, (hsv[..., 0] + dh) % 180, hsv[..., 0])
    hsv[..., 1] = np.where(m, np.clip(hsv[..., 1] + ds, 0, 255), hsv[..., 1])
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def _cast_shadow(canvas: np.ndarray, alpha: np.ndarray, x: int, y: int,
                 sun_dx: float, opacity: float = 0.35) -> None:
    """Тень на землю: сплющенная копия маски, сдвинутая по направлению света.

    Без тени вставка «висит» над поверхностью, и это заметное отличие от
    настоящего объекта — как раз тот признак, за который цепляется сеть.
    """
    h, w = alpha.shape
    sh_h = max(3, int(h * 0.22))
    sh = cv2.resize(alpha, (w, sh_h), interpolation=cv2.INTER_LINEAR)
    sh = cv2.GaussianBlur(sh, (0, 0), max(1.0, w * 0.03))
    sx = int(x + sun_dx * w * 0.3)
    sy = int(y + h - sh_h * 0.5)
    H, W = canvas.shape[:2]
    x0, y0 = max(0, sx), max(0, sy)
    x1, y1 = min(W, sx + w), min(H, sy + sh_h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = sh[y0 - sy: y1 - sy, x0 - sx: x1 - sx].astype(np.float32) / 255.0 * opacity
    canvas[y0:y1, x0:x1] = (canvas[y0:y1, x0:x1].astype(np.float32) *
                            (1 - sub[..., None])).astype(np.uint8)


def paste_one(canvas: np.ndarray, cutout: np.ndarray, x: int, y: int,
              target_h: int, depth: float, sun_dx: float,
              harmonise: float = 0.45) -> tuple[int, int, int, int] | None:
    """Вставить одну машину. Возвращает bbox (x1,y1,x2,y2) или None.

    depth в [0,1]: 0 — передний план, 1 — у горизонта. Управляет дымкой и
    размытием, чтобы дальняя вставка выглядела дальней, а не просто мелкой.
    """
    ch, cw = cutout.shape[:2]
    scale = target_h / ch
    nw, nh = max(6, int(cw * scale)), max(6, int(ch * scale))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    res = cv2.resize(cutout, (nw, nh), interpolation=interp)
    bgr, alpha = res[..., :3].copy(), res[..., 3]

    if random.random() < 0.5:
        bgr, alpha = bgr[:, ::-1].copy(), alpha[:, ::-1].copy()
    if random.random() < 0.7:
        bgr = _brand_colour_jitter(bgr, alpha)

    H, W = canvas.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + nw), min(H, y + nh)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    sx0, sy0 = x0 - x, y0 - y
    bgr = bgr[sy0: sy0 + (y1 - y0), sx0: sx0 + (x1 - x0)]
    alpha = alpha[sy0: sy0 + (y1 - y0), sx0: sx0 + (x1 - x0)]
    if alpha.max() == 0:
        return None

    region = canvas[y0:y1, x0:x1]
    bgr = _harmonise(bgr, alpha, region, strength=harmonise)

    # дымка и расфокус растут с расстоянием — так же, как у настоящего фона
    if depth > 0.15:
        haze = float(np.median(region.reshape(-1, 3), axis=0).mean())
        k = depth * 0.45
        bgr = np.clip(bgr.astype(np.float32) * (1 - k) + haze * k, 0, 255).astype(np.uint8)
        if depth > 0.5:
            bgr = cv2.GaussianBlur(bgr, (0, 0), 0.4 + depth * 0.9)

    # растушёвка альфы: резкий край — главный признак «вставки»
    a = cv2.GaussianBlur(alpha.astype(np.float32) / 255.0, (0, 0), 0.8)[..., None]
    a = np.clip(a, 0, 1)

    _cast_shadow(canvas, alpha, x0, y0, sun_dx)
    canvas[y0:y1, x0:x1] = (region.astype(np.float32) * (1 - a) +
                            bgr.astype(np.float32) * a).astype(np.uint8)
    return x0, y0, x1, y1


class CopyPasteComposer:
    """Собрать синтетический кадр: фон площадки + вставленная техника.

    Размещение: только в «земляной» полосе кадра (ниже линии горизонта),
    с ограничением на перекрытие с уже имеющимися объектами. Полностью
    накрывать существующую технику нельзя — её разметка останется в файле,
    а объекта на картинке уже не будет, и это прямая порча меток.
    """

    def __init__(self, bank: CutoutBank, classes: list[str],
                 n_range=(1, 5), ground_frac=0.55, max_iou_existing=0.35,
                 min_visible=0.6, rare_boost: dict[str, float] | None = None,
                 diversity_full=20):
        self.bank = bank
        self.classes = classes
        self.n_range = n_range
        # ОСНОВАНИЕ объекта ставим ниже этой доли кадра. Верхняя часть машины
        # (мачта, стрела) может уходить выше — так и в реальности, — но точка
        # опоры обязана быть на земле, а не в небе.
        self.ground_frac = ground_frac
        self.max_iou = max_iou_existing
        self.min_visible = min_visible      # доля объекта, обязанная попасть в кадр
        self.rare_boost = rare_boost or {}
        self.diversity_full = diversity_full

    def _pick_class(self) -> str | None:
        """Вероятность класса = редкостный буст, приглушённый разнообразием банка.

        Буст нужен, чтобы дотянуть редкие классы. Но если в классе 3 вырезки,
        то буст ×3 означает, что эти три картинки встретятся втрое чаще —
        переобучение на конкретный экземпляр, а не выучивание класса. Поэтому
        буст домножается на min(1, n/diversity_full).
        """
        avail = [c for c in self.bank.by_class if c in self.classes]
        if not avail:
            return None
        w = np.array([
            self.rare_boost.get(c, 1.0) *
            min(1.0, len(self.bank.by_class[c]) / self.diversity_full)
            for c in avail
        ], float)
        if w.sum() <= 0:
            return None
        return str(np.random.choice(avail, p=w / w.sum()))

    def __call__(self, img: np.ndarray, boxes_xyxy: list[list[float]],
                 cls_ids: list[int], size_model: tuple[float, float] | None = None):
        """img — BGR; boxes/cls — существующая разметка в пикселях.

        Возвращает (новый_img, новые_boxes, новые_cls).
        """
        canvas = img.copy()
        H, W = canvas.shape[:2]
        boxes = [list(b) for b in boxes_xyxy]
        ids = list(cls_ids)

        if size_model is None:
            pairs = [((b[1] + b[3]) / 2, b[3] - b[1]) for b in boxes_xyxy]
            size_model = fit_size_vs_y(pairs, H)
        a, b = size_model
        sun_dx = random.uniform(-1.0, 1.0)     # одно направление света на кадр
        y_base_min = int(H * self.ground_frac)

        for _ in range(random.randint(*self.n_range)):
            picked = self._pick_class()
            if picked is None:
                break
            got = self.bank.sample(picked)
            if got is None:
                continue
            cls, cut = got

            y = random.randint(y_base_min, H - 12)
            depth = float(np.clip((H - y) / max(H - y_base_min, 1), 0.0, 1.0))
            # типичный размер на этой строке, с разбросом: так вставка остаётся
            # геометрически правдоподобной, но не становится детерминированной
            base_h = max(10.0, a * y + b)
            target_h = int(np.clip(base_h * random.uniform(0.55, 1.9), 10, H * 0.75))
            # ширину вставки прикидываем по исходной пропорции, чтобы проверить
            # видимость ДО отрисовки
            ar = cut.shape[1] / max(cut.shape[0], 1)
            nw = max(6, int(target_h * ar))
            x = random.randint(int(-nw * (1 - self.min_visible)),
                               int(W - nw * self.min_visible))

            cand = (x, y - target_h, x + nw, y)
            if self._too_overlapping(cand, boxes):
                continue
            bb = paste_one(canvas, cut, x, y - target_h, target_h, depth, sun_dx)
            if bb is None:
                continue
            # отбрасываем «огрызки» у края кадра: бокс шириной в несколько
            # пикселей — это не объект, а испорченная метка
            if (bb[2] - bb[0]) < 8 or (bb[3] - bb[1]) < 8:
                continue
            if (bb[2] - bb[0]) < nw * self.min_visible * 0.8:
                continue
            boxes.append(list(bb))
            ids.append(self.classes.index(cls))

        # общий JPEG в конце: фон и вставки получают ОДИНАКОВЫЕ артефакты сжатия.
        # Без этого различие в статистике шума само по себе выдаёт вставку.
        q = random.randint(55, 92)
        ok, enc = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), q])
        if ok:
            canvas = cv2.imdecode(enc, cv2.IMREAD_COLOR)
        return canvas, boxes, ids

    def _too_overlapping(self, cand, boxes) -> bool:
        """Не даём вставке закрыть уже размеченный объект."""
        cx1, cy1, cx2, cy2 = cand
        for x1, y1, x2, y2 in boxes:
            ix = max(0, min(cx2, x2) - max(cx1, x1))
            iy = max(0, min(cy2, y2) - max(cy1, y1))
            inter = ix * iy
            if inter <= 0:
                continue
            area_existing = max((x2 - x1) * (y2 - y1), 1)
            if inter / area_existing > self.max_iou:
                return True
        return False
