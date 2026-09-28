"""Домен-ориентированные аугментации для снимков строительных камер.

Логика набора: перечислить факторы, которые реально меняются на площадке
между двумя снимками одной и той же камеры, и смоделировать каждый отдельной
группой. Группы именованы, чтобы их можно было включать/выключать по одной и
измерять вклад каждой в ablation (см. robustness.py), а не заявлять «мы всё учли».

Группы:
  time_of_day — рассвет/закат/сумерки/ночь (яркость, гамма, цветовая температура,
                ночной режим камеры = ч/б + ИК-подсветка + шум)
  weather     — дождь, снег, туман/дымка, блики и капли на объективе
  season      — снежный покров на земле, «зелень→охра», зимний низкий контраст
  camera      — расфокус, смаз, JPEG-артефакты, шум матрицы, виньетка, дисторсия
  geometry    — масштаб (главное для мелких объектов), поворот, перспектива,
                смена точки установки камеры
  occlusion   — техника перекрыта: забором, мачтой крана, отвалом грунта, бытовкой,
                краем кадра, тентом. Именно сценарий «часть площадки закрыта».

Все bbox-safe: используем формат yolo и min_visibility, чтобы объект, скрытый
почти полностью, выбывал из разметки, а не превращался в шум для лосса.
"""
import numpy as np
import albumentations as A
import cv2

BBOX = A.BboxParams(format="yolo", label_fields=["class_labels"],
                    min_visibility=0.25, min_area=16)


def time_of_day(p=1.0):
    return A.OneOf([
        # рассвет/закат: тёплый сдвиг + падение яркости
        A.Compose([A.RandomBrightnessContrast(brightness_limit=(-0.35, -0.05), contrast_limit=(-0.2, 0.1), p=1),
                   A.HueSaturationValue(hue_shift_limit=(-12, 4), sat_shift_limit=(5, 30), val_shift_limit=0, p=1)]),
        # полдень: пересвет, жёсткие тени
        A.Compose([A.RandomBrightnessContrast(brightness_limit=(0.05, 0.3), contrast_limit=(0.1, 0.35), p=1),
                   A.RandomShadow(shadow_roi=(0, 0.4, 1, 1), num_shadows_limit=(1, 3), p=0.7)]),
        # сумерки
        A.Compose([A.RandomGamma(gamma_limit=(130, 200), p=1),
                   A.RandomBrightnessContrast(brightness_limit=(-0.45, -0.2), contrast_limit=(-0.3, 0), p=1)]),
        # ночной режим камеры: ИК-подсветка (ч/б с зеленоватым отливом), шум, локальные
        # засветы от прожекторов. Калибровано так, чтобы техника оставалась различимой:
        # реальная ночная запись тёмная, но не чёрная — иначе аугментация учит модель
        # на пустом кадре.
        A.Compose([A.ToGray(p=1),
                   A.RandomGamma(gamma_limit=(105, 150), p=1),
                   A.RandomBrightnessContrast(brightness_limit=(-0.30, -0.12),
                                              contrast_limit=(-0.15, 0.05), p=1),
                   A.GaussNoise(std_range=(0.04, 0.10), p=1),
                   A.ImageCompression(quality_range=(35, 70), p=0.6),
                   A.RandomSunFlare(flare_roi=(0, 0, 1, 0.7), num_flare_circles_range=(1, 3),
                                    src_radius=90, p=0.6)]),
    ], p=p)


def weather(p=0.6):
    return A.OneOf([
        A.RandomRain(brightness_coefficient=0.85, drop_width=1, blur_value=3, p=1),
        A.RandomSnow(snow_point_range=(0.15, 0.4), brightness_coeff=2.0, p=1),
        A.RandomFog(fog_coef_range=(0.15, 0.45), alpha_coef=0.1, p=1),
        A.Spatter(mode="rain", p=1),          # капли на объективе
        A.RandomSunFlare(flare_roi=(0, 0, 1, 0.4), src_radius=180, p=1),
    ], p=p)


def season(p=0.5):
    return A.OneOf([
        # зима: снег на земле, низкий контраст, холодный баланс белого
        A.Compose([A.RandomSnow(snow_point_range=(0.25, 0.5), brightness_coeff=2.2, p=1),
                   A.RandomBrightnessContrast(brightness_limit=(0.05, 0.25), contrast_limit=(-0.3, -0.05), p=1),
                   A.HueSaturationValue(hue_shift_limit=(4, 14), sat_shift_limit=(-45, -15), val_shift_limit=0, p=1)]),
        # осень: охра, пожухшая зелень. Сдвиг тона держим узким — широкий диапазон
        # перекрашивает грунт в неестественный красный и учит модель на артефакте.
        A.HueSaturationValue(hue_shift_limit=(-6, -2), sat_shift_limit=(-20, 5), val_shift_limit=(-12, 2), p=1),
        # лето: сочная зелень при сохранении цвета грунта
        A.HueSaturationValue(hue_shift_limit=(2, 6), sat_shift_limit=(8, 25), val_shift_limit=(0, 10), p=1),
    ], p=p)


def camera(p=0.7):
    return A.OneOf([
        A.MotionBlur(blur_limit=(3, 11), p=1),        # смаз при повороте PTZ
        A.Defocus(radius=(2, 6), p=1),                 # расфокус
        A.ImageCompression(quality_range=(25, 65), p=1),  # артефакты видеопотока
        A.GaussNoise(std_range=(0.03, 0.12), p=1),
        A.Compose([A.OpticalDistortion(distort_limit=0.25, p=1)]),  # широкоугольный объектив
        A.Downscale(scale_range=(0.35, 0.7), p=1),     # низкий битрейт / дальняя камера
    ], p=p)


def geometry(p=1.0):
    # Масштаб — критичный фактор: медианная техника в кадрах ДГП ~3% ширины кадра.
    # Расширяем диапазон масштабов, чтобы модель училась и на «далёкой», и на «близкой» технике.
    return A.Compose([
        # BORDER_REFLECT_101, а не чёрная заливка: чёрные поля по краям — признак,
        # которого в реальном кадре нет, и модель быстро начинает на него опираться.
        A.Affine(scale=(0.5, 1.6), rotate=(-8, 8), shear=(-4, 4),
                 translate_percent=(-0.1, 0.1), fit_output=False,
                 border_mode=cv2.BORDER_REFLECT_101, p=0.9),
        A.Perspective(scale=(0.02, 0.08), p=0.3),      # другая высота/наклон установки камеры
        A.HorizontalFlip(p=0.5),
    ], p=p)


class PasteOccluders(A.ImageOnlyTransform):
    """Реалистичное перекрытие: вставляем вырезанные с площадок фрагменты
    (забор, мачта крана, бытовка, отвал грунта, тент, ветки) поверх кадра.

    Отличие от CoarseDropout — перекрывающий объект имеет текстуру площадки,
    поэтому модель учится не «чёрный прямоугольник = фон», а реальному
    сценарию «технику загородило».
    """

    def __init__(self, patches, n_range=(1, 3), scale=(0.08, 0.35), p=0.5):
        super().__init__(p=p)
        self.patches, self.n_range, self.scale = patches, n_range, scale

    def apply(self, img, **params):
        if not len(self.patches):
            return img
        out = img.copy()
        H, W = out.shape[:2]
        for _ in range(np.random.randint(*self.n_range)):
            patch = self.patches[np.random.randint(len(self.patches))]
            s = np.random.uniform(*self.scale)
            pw, ph = max(8, int(W * s)), max(8, int(H * s * np.random.uniform(0.4, 1.4)))
            pr = cv2.resize(patch, (pw, ph))
            x, y = np.random.randint(0, max(1, W - pw)), np.random.randint(0, max(1, H - ph))
            out[y:y + ph, x:x + pw] = pr
        return out


class FenceOcclusion(A.ImageOnlyTransform):
    """Забор / мачта крана / стойки опалубки: регулярные вертикальные полосы.

    На площадке техника чаще всего перекрывается именно вертикальными элементами —
    секциями ограждения, мачтами, колоннами. Прямоугольный dropout этот случай
    не воспроизводит.
    """

    def __init__(self, bar_width=(4, 16), gap=(28, 90), tilt=(-6, 6), p=0.5):
        super().__init__(p=p)
        self.bar_width, self.gap, self.tilt = bar_width, gap, tilt

    def apply(self, img, **params):
        out = img.copy()
        H, W = out.shape[:2]
        bw = np.random.randint(*self.bar_width)
        gap = np.random.randint(*self.gap)
        tilt = np.random.uniform(*self.tilt)
        # цвет берём из самого кадра — серый бетон/профлист, а не чёрный
        tone = int(np.clip(img.reshape(-1, 3).mean() * np.random.uniform(0.55, 1.15), 25, 220))
        colour = (tone, tone, int(tone * np.random.uniform(0.95, 1.08)))
        overlay = out.copy()
        for x in range(-int(abs(tilt) * H) - gap, W + gap, gap + bw):
            pts = np.array([[x, 0], [x + bw, 0],
                            [int(x + bw + tilt * H), H], [int(x + tilt * H), H]], dtype=np.int32)
            cv2.fillPoly(overlay, [pts], colour)
        alpha = np.random.uniform(0.75, 1.0)
        return cv2.addWeighted(overlay, alpha, out, 1 - alpha, 0)


class BlockOcclusion(A.ImageOnlyTransform):
    """Крупная заслонка: бытовка, отвал грунта, борт машины на переднем плане,
    тент. Немного, но большие — и залитые правдоподобным тоном, а не чёрным."""

    def __init__(self, n_range=(1, 3), size=(0.12, 0.42), p=0.5):
        super().__init__(p=p)
        self.n_range, self.size = n_range, size

    def apply(self, img, **params):
        out = img.copy()
        H, W = out.shape[:2]
        for _ in range(np.random.randint(*self.n_range)):
            bw = int(W * np.random.uniform(*self.size))
            bh = int(H * np.random.uniform(*self.size) * np.random.uniform(0.5, 1.3))
            x = np.random.randint(0, max(1, W - bw)); y = np.random.randint(0, max(1, H - bh))
            patch = out[y:y + bh, x:x + bw]
            base = patch.reshape(-1, 3).mean(0) * np.random.uniform(0.5, 1.3)
            noise = np.random.normal(0, 9, patch.shape)
            out[y:y + bh, x:x + bw] = np.clip(base + noise, 0, 255).astype(np.uint8)
        return out


def occlusion(patches=None, p=0.5):
    """Перекрытия площадки.

    Порядок предпочтения: вставка реальных фрагментов площадки -> вертикальные
    ограждения -> крупные однотонные заслонки. Мелкий «конфетти»-dropout
    сознательно не используем: он не соответствует ни одному реальному сценарию
    и при мелких объектах просто стирает цель целиком.
    """
    variants = [FenceOcclusion(p=1), BlockOcclusion(p=1)]
    if patches is not None and len(patches):
        variants.insert(0, PasteOccluders(patches, p=1))
        variants.insert(0, PasteOccluders(patches, p=1))  # вес x2 — самый реалистичный вариант
    return A.OneOf(variants, p=p)


def build(patches=None, strength="train"):
    """Собрать пайплайн.

    Группы не складываются все подряд: A.SomeOf выбирает ограниченное число.
    Иначе «ночь + туман + downscale + расфокус» дают практически чёрный кадр —
    такой сэмпл не несёт сигнала и только портит обучение. Геометрию применяем
    всегда (она безопасна и отвечает за главный фактор — масштаб объекта).

    strength='train'  — обучение (умеренно, 2 фотометрические группы из 5)
    strength='heavy'  — стресс-тест устойчивости (3 группы из 5)
    """
    n = 3 if strength == "heavy" else 2
    pool = [time_of_day(1.0), weather(1.0), season(1.0), camera(1.0), occlusion(patches, 1.0)]
    return A.Compose([geometry(1.0), A.SomeOf(pool, n=n, p=0.9)], bbox_params=BBOX)


GROUPS = {"time_of_day": time_of_day, "weather": weather, "season": season,
          "camera": camera, "geometry": geometry}
