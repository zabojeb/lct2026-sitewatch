#!/usr/bin/env python3
"""Explainable mapping from a construction-stage title to camera-visible equipment.

The mapper is intentionally deterministic. It does not pretend that an unknown
title is a known technology: low-evidence titles receive ``needs_review``.
Profiles are based on the leading machines listed in official GESN/FSNB resource
tables; ``required`` means required over an observation window, not in every frame.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable


EQUIPMENT_CLASSES = [
    "самосвал",
    "экскаватор",
    "каток",
    "кран-манипулятор",
    "бетоносмеситель",
    "бульдозер",
    "грузовик",
    "автокран",
    "башенный кран",
    "буровая",
    "бетононасос",
    "погрузчик",
    "автогрейдер",
    "асфальтоукладчик",
]


OFFICIAL_SOURCES = {
    "fsnb2022": {
        "title": "ФСНБ-2022: государственные элементные сметные нормы",
        "authority": "Минстрой России",
        "url": "https://minstroyrf.gov.ru/trades/tree_download.php?ID=0&folder=fsnb2022",
    },
    "gesn06": {
        "title": "ГЭСН 06. Бетонные и железобетонные конструкции монолитные",
        "authority": "Минстрой России",
        "url": "https://minstroyrf.gov.ru/docs/137985/",
    },
    "gesn07": {
        "title": "ГЭСН 07. Бетонные и железобетонные конструкции сборные",
        "authority": "Минстрой России",
        "url": "https://minstroyrf.gov.ru/trades/dwd-state-gesn.php?ID=6",
    },
    "gesn27": {
        "title": "ГЭСН 27. Автомобильные дороги",
        "authority": "Минстрой России",
        "url": "https://minstroyrf.gov.ru/trades/dwd-gesn-2020.php?ID=26",
    },
    "tsn_moscow": {
        "title": "Перечень сборников ТСН-2001 для Москвы, приказ МКЭ-ОД/23-89",
        "authority": "Москомэкспертиза / Правительство Москвы",
        "url": "https://www.mos.ru/upload/documents/files/5683/MKE-OD-23-89sprilojeniem.pdf",
    },
}


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    required: tuple[str, ...] = ()
    required_any: tuple[tuple[str, ...], ...] = ()
    optional: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    gesn_tables: tuple[str, ...] = ()
    note: str = ""
    observation_window_minutes: int = 30


def profile(
    id: str,
    name: str,
    *,
    required: Iterable[str] = (),
    required_any: Iterable[Iterable[str]] = (),
    optional: Iterable[str] = (),
    source_refs: Iterable[str] = (),
    gesn_tables: Iterable[str] = (),
    note: str = "",
    observation_window_minutes: int = 30,
) -> Profile:
    return Profile(
        id=id,
        name=name,
        required=tuple(required),
        required_any=tuple(tuple(group) for group in required_any),
        optional=tuple(optional),
        source_refs=tuple(source_refs),
        gesn_tables=tuple(gesn_tables),
        note=note,
        observation_window_minutes=observation_window_minutes,
    )


PROFILES = {
    p.id: p
    for p in [
        profile(
            "no_camera_equipment",
            "Работа без контролируемой тяжёлой техники",
            source_refs=("fsnb2022",),
            note="Отделка, внутренние сети, IT, закупка и ручные операции не дают надёжного сигнала по внешней камере.",
        ),
        profile(
            "site_setup",
            "Обустройство строительной площадки",
            optional=("грузовик", "кран-манипулятор", "автокран", "экскаватор", "погрузчик"),
            source_refs=("fsnb2022", "tsn_moscow"),
            note="Техника появляется эпизодически; отсутствие не является отклонением.",
        ),
        profile(
            "demolition",
            "Снос и механизированный демонтаж",
            required_any=(("экскаватор", "бульдозер", "погрузчик"),),
            optional=("самосвал", "грузовик", "автокран"),
            source_refs=("fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 46; ГЭСНр 53",),
            note="Нужна хотя бы одна ведущая демонтажная машина; вывоз может происходить не непрерывно.",
        ),
        profile(
            "debris_loading",
            "Погрузка грунта или строительного мусора",
            required_any=(("погрузчик", "экскаватор"),),
            optional=("самосвал", "грузовик"),
            source_refs=("fsnb2022",),
            gesn_tables=("ГЭСН 01; ГЭСНр 61",),
            note="Погрузчик добавлен как отдельный визуальный класс по ресурсным таблицам ГЭСН.",
        ),
        profile(
            "earth_excavation",
            "Разработка грунта и котлован",
            required=("экскаватор",),
            required_any=(("самосвал", "погрузчик"),),
            optional=("бульдозер", "автогрейдер", "грузовик"),
            source_refs=("fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 01-01-011 и подраздел 1.2",),
            note="Экскаватор разрабатывает грунт; самосвал либо погрузчик обеспечивает поток грунта/вывоз.",
        ),
        profile(
            "earth_grading",
            "Планировка, насыпь и обратная засыпка",
            required_any=(("бульдозер", "автогрейдер", "экскаватор"),),
            optional=("самосвал", "погрузчик", "каток"),
            source_refs=("fsnb2022",),
            gesn_tables=("ГЭСН 01-01-116; 01-01-117",),
            note="Технология допускает разные ведущие планировочные машины.",
        ),
        profile(
            "soil_compaction",
            "Уплотнение грунта",
            required=("каток",),
            optional=("бульдозер", "автогрейдер", "самосвал"),
            source_refs=("fsnb2022",),
            gesn_tables=("ГЭСН 01-02-001",),
            note="Каток является ведущей камерно-наблюдаемой машиной для механизированного уплотнения.",
        ),
        profile(
            "network_trench",
            "Наружные сети и траншейные работы",
            required=("экскаватор",),
            optional=("самосвал", "погрузчик", "грузовик", "автокран", "кран-манипулятор"),
            source_refs=("fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 01; 22; 23; 24; 33; 34",),
            note="Контроль применяется к наружной трассе/траншее; внутренние сети вынесены в отдельный профиль.",
        ),
        profile(
            "bored_piles",
            "Буронабивные сваи, скважины и закрепление грунтов",
            required=("буровая",),
            optional=("автокран", "башенный кран", "экскаватор", "бетоносмеситель", "бетононасос", "грузовик"),
            source_refs=("fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 05-01-028; 05-01-029",),
            note="Буровая установка — ведущая и визуально различимая машина.",
            observation_window_minutes=60,
        ),
        profile(
            "piles_generic",
            "Свайные работы без указания технологии",
            required_any=(("буровая", "автокран"),),
            optional=("экскаватор", "бетоносмеситель", "бетононасос", "грузовик"),
            source_refs=("fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 05",),
            note="Название не различает буронабивные и погружаемые сваи; используется альтернативная группа.",
            observation_window_minutes=60,
        ),
        profile(
            "concrete",
            "Монолитные бетонные и железобетонные работы",
            required_any=(("бетононасос", "бетоносмеситель", "башенный кран", "автокран"),),
            optional=("грузовик",),
            source_refs=("gesn06", "fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 06-01-003; 06-22-004",),
            note="Подача смеси выполняется насосом или краном; автобетоносмеситель учитывается как наблюдаемая доставка.",
            observation_window_minutes=60,
        ),
        profile(
            "rebar",
            "Армирование и арматурные каркасы",
            optional=("башенный кран", "автокран", "кран-манипулятор", "грузовик"),
            source_refs=("gesn06", "fsnb2022"),
            gesn_tables=("ГЭСН 06",),
            note="Подъём арматуры эпизодичен, поэтому жёсткий контроль по камере не вводится.",
        ),
        profile(
            "structure_lift",
            "Монтаж сборных, металлических и крупногабаритных конструкций",
            required_any=(("башенный кран", "автокран", "кран-манипулятор"),),
            optional=("грузовик",),
            source_refs=("gesn07", "fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 07-05-004; ГЭСН 09",),
            note="Нужна хотя бы одна грузоподъёмная машина в пределах окна наблюдения.",
            observation_window_minutes=60,
        ),
        profile(
            "road_base",
            "Дорожное основание и подготовительные слои",
            required_any=(("каток", "автогрейдер", "бульдозер"),),
            optional=("самосвал", "погрузчик", "экскаватор", "грузовик", "автокран"),
            source_refs=("gesn27", "fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 27-03-002; 27-03-003",),
            note="Автогрейдер добавлен как отдельный класс для планировки дорожных оснований.",
        ),
        profile(
            "asphalt_paving",
            "Асфальтобетонное покрытие",
            required_any=(("асфальтоукладчик", "каток"),),
            optional=("самосвал", "погрузчик", "автогрейдер", "грузовик"),
            source_refs=("gesn27", "fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 27-06-039",),
            note="Асфальтоукладчик добавлен как самостоятельный визуальный класс; каток покрывает стадию уплотнения.",
        ),
        profile(
            "manual_paving",
            "Плиточное, бортовое и малое покрытие",
            optional=("погрузчик", "грузовик", "кран-манипулятор", "каток"),
            source_refs=("gesn27", "tsn_moscow"),
            gesn_tables=("ГЭСН 27",),
            note="Работа часто выполняется малыми механизмами и вручную; тяжёлая техника не обязательна.",
        ),
        profile(
            "facade_roof_masonry",
            "Фасад, кровля и наружная кладка",
            optional=("башенный кран", "автокран", "кран-манипулятор", "грузовик"),
            source_refs=("fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 08; 12; 15; 26",),
            note="Подача материалов видима эпизодически; отсутствие крана не считается нарушением.",
        ),
        profile(
            "landscaping",
            "Озеленение и благоустройство",
            optional=("грузовик", "самосвал", "экскаватор", "погрузчик", "бульдозер", "каток"),
            source_refs=("fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 47",),
            note="Состав машин зависит от размера посадочного материала и технологии.",
        ),
        profile(
            "delivery_install",
            "Доставка и эпизодический монтаж",
            optional=("грузовик", "кран-манипулятор", "автокран"),
            source_refs=("fsnb2022",),
            note="Используется для оборудования, ограждений, освещения и прочих поставочных операций.",
        ),
        profile(
            "tunnel",
            "Тоннельные работы / ТПМК",
            optional=("автокран", "башенный кран", "экскаватор", "самосвал", "грузовик", "бетононасос"),
            source_refs=("fsnb2022", "tsn_moscow"),
            gesn_tables=("ГЭСН 29",),
            note="ТПМК отсутствует в перечне визуальных классов; контроль ведётся только по вспомогательной технике.",
        ),
        profile(
            "mixed_underground",
            "Укрупнённая подземная фаза",
            optional=("экскаватор", "самосвал", "буровая", "автокран", "башенный кран", "бетоносмеситель", "бетононасос", "бульдозер", "погрузчик", "грузовик"),
            source_refs=("fsnb2022",),
            note="Заголовок объединяет разные технологии; обязательный комплект назначается дочерним строкам.",
        ),
        profile(
            "mixed_aboveground",
            "Укрупнённая надземная фаза",
            optional=("башенный кран", "автокран", "кран-манипулятор", "бетоносмеситель", "бетононасос", "грузовик"),
            source_refs=("fsnb2022",),
            note="Заголовок объединяет разные технологии; обязательный комплект назначается дочерним строкам.",
        ),
        profile(
            "mixed_construction",
            "Укрупнённый заголовок СМР",
            optional=tuple(EQUIPMENT_CLASSES),
            source_refs=("fsnb2022",),
            note="Корневой заголовок не используется для проверки отсутствия техники.",
        ),
        profile(
            "mixed_utilities",
            "Укрупнённый заголовок инженерных систем",
            optional=("экскаватор", "самосвал", "погрузчик", "грузовик", "автокран", "кран-манипулятор"),
            source_refs=("fsnb2022", "tsn_moscow"),
            note="Наружные и внутренние сети разделяются на дочерних строках.",
        ),
        profile(
            "needs_review",
            "Неизвестный этап — требуется проверка",
            note="Недостаточно признаков для автоматического назначения техники.",
        ),
    ]
}


@dataclass(frozen=True)
class Rule:
    id: str
    profile_id: str
    pattern: str
    priority: int
    reason: str
    negative_pattern: str = ""


# Specific rules have higher priority. Word boundaries prevent collisions such
# as "кладка" inside "прокладка".
RULES = [
    Rule("tunnel", "tunnel", r"\bтпмк\b|проходк\w*\s+тоннел|тоннелепроход", 100, "тоннельная технология"),
    Rule("bored-piles", "bored_piles", r"буронабив|буроинъекц|буросекущ|\bбурени\w*\b|скважин\w*\s+интервал|закреплени\w*\s+грунт|струйн\w*\s+цементац", 98, "бурение/закрепление грунтов"),
    Rule("piles-generic", "piles_generic", r"свайн\w*\s+фундамент|устройств\w*\s+сва(й|и)|шпунтов\w*\s+огражден|\bшпунт\b|\bсваи\b|ограждающ\w*\s+конструкц\w*\s*\(свг|обвязочн\w*\s+балк|распорн\w*\s+систем", 90, "свайные и ограждающие работы без точного способа"),
    Rule("asphalt", "asphalt_paving", r"асфальтобетон|асфальтирован|нижн\w*\s+сло\w*\s+покрыт|верхн\w*\s+сло\w*\s+покрыт|покрыти\w*\s+дорожн\w*\s+одежд", 96, "асфальтобетонное покрытие"),
    Rule("soil-compaction", "soil_compaction", r"уплотнени\w*\s+грунт", 95, "уплотнение грунта"),
    Rule("road-base", "road_base", r"дорожн\w*\s+одежд|щебеночн\w*\s+основан|песчан\w*\s+(подготов|основан)|сло\w*\s+основан\w*\s+дорож|жестк\w*\s+основан|планировк\w*\s+(нижн|верхн)\w*\s+сло|уплотнени\w*\s+(нижн|верхн)\w*\s+сло", 92, "основание дорожной одежды"),
    Rule("manual-paving", "manual_paving", r"тротуарн\w*\s+плит|бортов\w*\s+кам|резинов\w*\s+крош|пешеходн\w*\s+зон|проезд\w*\s+и\s+тротуар|водоотводн\w*\s+лотк", 88, "малое дорожное покрытие/элементы"),
    Rule("debris-loading", "debris_loading", r"погрузк\w*\s+(строительн\w*\s+)?мусор|погрузк\w*\s+грунт", 97, "явная погрузочная операция"),
    Rule("demolition", "demolition", r"\bснос\b|демонтаж\w*\s+(ж/?б|железобетон|здани|сооруж|перекрыт)", 94, "механизированный демонтаж"),
    Rule("excavation", "earth_excavation", r"котлован|разработк\w*\s+грунт|выемк\w*\s+грунт|землян\w*\s+работ", 91, "разработка грунта/котлован"),
    Rule("earth-grading", "earth_grading", r"обратн\w*\s+засып|планировк\w*\s+грунт|вертикальн\w*\s+планиров|устройств\w*\s+насып|устройств\w*\s+выемк|насыпь\s*/?\s*призм", 89, "планировка или перемещение грунта"),
    Rule("network-explicit", "network_trench", r"вынос\w*.*\bсет|наружн\w*\s+сет|трубн\w*\s+канализац|прокладк\w*\s+труб|устройств\w*\s+колодц|пристенн\w*\s+дренаж|разработк\w*\s+грунт\w*\s+с\s+креплен", 93, "наружная сеть/траншея"),
    Rule("masonry-specific", "facade_roof_masonry", r"стен\w*\s+из\s+ячеист|стен\w*.*\bкирпич|перегород\w*.*\b(кирпич|газобетон|гкл|гвлв)", 90, "стены/перегородки из штучных материалов"),
    Rule("concrete", "concrete", r"монолит|бетонир|бетонн\w*\s+(подготов|покрыт)|фундаментн\w*\s+плит|устройств\w*\s+фундамент|ж/?б\s+(конструкц|контсрукц)|железобетонн\w*\s+конструкц|стен,?\s+колонн\w*\s+и\s+пилон|сталебетон|путев\w*\s+бетон|плит\w*\s+(перекрыт|проезж)|подпорн\w*\s+(стен|\/)|мостов\w*\s+полотн|дизель-генераторн\w*.*фундамент", 87, "бетонные/железобетонные конструкции"),
    Rule("rebar", "rebar", r"\bармокаркас\b|армировани\w*\s+пролет|арматурн\w*\s+каркас", 86, "армирование без явного бетонирования"),
    Rule("structure-lift", "structure_lift", r"металлоконструкц|каркас\w*\s+здани|конструкц\w*\s+пролетн|сборн\w*\s+(ж/?б|железобетон)|сэндвич[- ]панел|профилированн\w*\s+лист|\bпрофнастил\b|конструкц\w*\s+кровл|\bопоры\b|установк\w*\s+опор|\bпролеты\b|рельсо-шпальн|верхн\w*\s+строени\w*\s+пут", 84, "монтаж крупногабаритных конструкций"),
    Rule("facade-roof-masonry", "facade_roof_masonry", r"\bфасад|\bкровл|козырьк|витраж|керамогранит|теплоизоляц|утеплител|облицовк|(?<!про)кладк\w*|\bкирпич|наружн\w*\s+стен|газобетон|\bгкл\b|\bгвлв\b|ламел|фасадн\w*\s+кассет|\bцокол|парапет|пароизоляц|водосток|аэратор|разуклонк|откос\w*\s+и\s+слив", 70, "фасад/кровля/кладка"),
    Rule("landscaping", "landscaping", r"озелен|\bгазон|цветник|посадк\w*\s+(дерев|кустар|зелен)|вырубк\w*\s+зелен|пересадк\w*\s+зелен|\bмаф", 68, "озеленение"),
    Rule("site-setup", "site_setup", r"обустройств\w*\s+строительн\w*\s+площад|огражден\w*\s+строительн\w*\s+площад|временн\w*\s+внутриплощадочн|хозяйственно-бытов\w*\s+город", 66, "обустройство стройплощадки"),
    Rule("delivery-install", "delivery_install", r"установк\w*\s+(барьерн|перильн|пешеходн|дорожн\w*\s+знак|светофор|шумо|ворот|огражден)|дорожн\w*\s+огражден|наружн\w*\s+освещен|архитектурно-художественн\w*\s+подсвет|монтаж\w*\s+(вертикальн\w*\s+транспорт|эскалатор|оборудован)|поставк\w*\s+оборудован|заказ\w*\s+оборудован", 60, "доставка или эпизодический монтаж"),
]


EXACT_HEADINGS = {
    "подготовка территории": "site_setup",
    "выполнение строительно-монтажных работ": "mixed_construction",
    "устройство подземной части": "mixed_underground",
    "устройство надземной части": "mixed_aboveground",
    "устройство инженерных систем": "mixed_utilities",
    "отделочные работы": "no_camera_equipment",
    "благоустройство территории": "landscaping",
    "устройство наружных сетей": "network_trench",
    "устройство внутренних сетей": "no_camera_equipment",
    "устройство основания": "road_base",
    "мостовое полотно": "concrete",
    "устройство временных инженерных сетей": "site_setup",
    "оснащение стройплощадки оборудованием по 299-пп": "site_setup",
    "установка бокового барьерного ограждения с внешней стороны пролетного строения": "delivery_install",
    "стены и перегородки": "facade_roof_masonry",
    "дорожные знаки": "delivery_install",
    "пешеходное ограждение": "delivery_install",
    "светофорные объекты": "delivery_install",
    "шумо/грязезащитные экраны": "delivery_install",
    "средства организации дорожного движения": "delivery_install",
    "обустройство": "delivery_install",
    "трансбарьер": "delivery_install",
    "трибуны актового зала": "delivery_install",
    "ограждения": "delivery_install",
    "решетки": "delivery_install",
    "пожарные лестницы": "delivery_install",
    "утепление": "facade_roof_masonry",
    "устройство эксплуатируемой дорожки": "facade_roof_masonry",
    "устройство шумозащитного экрана": "delivery_install",
    "подшивка нависающих частей здания алюминиевой рейкой": "facade_roof_masonry",
    "ограждения из нержавеющей стали": "delivery_install",
}


INTERNAL_CONTEXT = re.compile(r"внутренн|отделочн|пассажирск\w*\s+зон|техническ\w*\s+помещ", re.I)
OUTER_CONTEXT = re.compile(r"наружн|вынос|благоустрой|подготовк\w*\s+территор", re.I)
NETWORK_SHORT = re.compile(
    r"^(теплосеть|водоснабжение|х/?б\s+канализация|ливневая\s+канализация|"
    r"электроснабжение|слаботочные\s+сети|сети\s+связи|сети\s+водоснабжения|"
    r"сети\s+канализации|прокладка\s+кабеля|электрика|сантехника)$",
    re.I,
)
NO_CAMERA = re.compile(
    r"отселен|проверк\w*\s+посадк|геодезическ\w*\s+знак|\bподд\b|видеокамер|"
    r"\bскуд\b|face\s*id|датчик\w*\s+шум|\bецхд\b|интеграц|тестирован|закупк|"
    r"оконн|подоконник|двер|внутренн\w*\s+перегород|сантехническ\w*\s+перегород|\bлюк|отделк|потолк|\bполов\b|"
    r"окраск|огнезащит|гидроизол|гидрозол|инъектир|мебел|компьютер|жалюзи|"
    r"немонтируем|инвентарь|расходн\w*\s+материал|медицинск\w*\s+инструмент|"
    r"дератизац|сигнализац|радиофикац|электрочасо|телефонизац|домофон|"
    r"автоматизац|пожаротушен|вентиляц|кондиционир|систем\w*\s+отоплен|теплов\w*\s+пункт|электрооборудован|охранн\w*\s+телевиден|противопожарн\w*\s+мероприят|\bапс\b|\bсоуэ\b|\bаппз\b|\bоди\b|\bсвмгн\b|"
    r"периметр\w*\s+безопасност|хозяйственн\w*\s+инвентар|дорожн\w*\s+разметк",
    re.I,
)


def normalize(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = value.replace("–", "-").replace("—", "-")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .;:")


def allowed_equipment(p: Profile) -> list[str]:
    values = set(p.required) | set(p.optional)
    for group in p.required_any:
        values.update(group)
    return sorted(values, key=lambda x: EQUIPMENT_CLASSES.index(x))


def _result(profile_id: str, rule_id: str, reason: str, confidence: str, *, review: bool = False) -> dict:
    p = PROFILES[profile_id]
    return {
        "profile_id": p.id,
        "profile_name": p.name,
        "match_status": "needs_review" if review else "matched",
        "confidence": confidence,
        "rule_id": rule_id,
        "reason": reason,
        "required": list(p.required),
        "required_any": [list(group) for group in p.required_any],
        "optional": list(p.optional),
        "allowed": allowed_equipment(p),
        "camera_control": bool(p.required or p.required_any),
        "observation_window_minutes": p.observation_window_minutes,
        "source_refs": list(p.source_refs),
        "gesn_tables": list(p.gesn_tables),
        "note": p.note,
    }


def map_stage(name: str, *, l1: str = "", l2: str = "") -> dict:
    """Map one title. Context is used only to disambiguate short/generic names."""
    title = normalize(name)
    context = normalize(" ".join(x for x in (l1, l2) if x))

    if not title:
        return _result("needs_review", "empty-title", "пустое название", "none", review=True)

    if title in EXACT_HEADINGS:
        return _result(EXACT_HEADINGS[title], f"exact:{title}", "точное название укрупнённого этапа", "high")

    if NETWORK_SHORT.fullmatch(title):
        if INTERNAL_CONTEXT.search(context) and not OUTER_CONTEXT.search(context):
            return _result("no_camera_equipment", "context:internal-network", "короткое имя в разделе внутренних сетей", "high")
        if OUTER_CONTEXT.search(context):
            return _result("network_trench", "context:outer-network", "короткое имя в разделе наружных сетей/благоустройства", "high")
        return _result("network_trench", "title:network-short", "короткое название инженерной сети", "medium")

    if NO_CAMERA.search(title):
        return _result("no_camera_equipment", "title:no-camera", "этап не даёт устойчивого сигнала тяжёлой техники по внешней камере", "high")

    matches = [r for r in RULES if re.search(r.pattern, title, re.I) and not (r.negative_pattern and re.search(r.negative_pattern, title, re.I))]
    if matches:
        matches.sort(key=lambda r: r.priority, reverse=True)
        winner = matches[0]
        confidence = "high" if winner.priority >= 84 else "medium"
        reason = winner.reason
        if len(matches) > 1:
            reason += "; также найдены признаки: " + ", ".join(r.id for r in matches[1:3])
        return _result(winner.profile_id, winner.id, reason, confidence)

    if "отделочные работы" in context:
        return _result("no_camera_equipment", "section:finishing", "общая строка раздела отделочных работ", "medium")
    if "благоустройство территории" in context:
        return _result("landscaping", "section:landscaping", "общая строка раздела благоустройства", "medium")
    if "устройство инженерных систем" in context:
        if INTERNAL_CONTEXT.search(title + " " + context):
            return _result("no_camera_equipment", "section:internal-utilities", "общая строка внутренних инженерных систем", "medium")
        return _result("mixed_utilities", "section:utilities", "общая строка инженерных систем без указания технологии", "low")
    if "подготовка территории" in context:
        return _result("site_setup", "section:site-preparation", "общая строка подготовки территории", "low")
    if "устройство надземной части" in context:
        return _result("delivery_install", "section:aboveground", "общая строка надземной части без ведущей технологии", "low")

    return _result("needs_review", "unmatched", "нет достаточных признаков для безопасного назначения", "none", review=True)


def profile_records() -> list[dict]:
    records = []
    for p in PROFILES.values():
        rec = asdict(p)
        rec["required"] = list(p.required)
        rec["required_any"] = [list(group) for group in p.required_any]
        rec["optional"] = list(p.optional)
        rec["allowed"] = allowed_equipment(p)
        records.append(rec)
    return records


def validate_profiles() -> None:
    known = set(EQUIPMENT_CLASSES)
    for p in PROFILES.values():
        values = set(p.required) | set(p.optional)
        for group in p.required_any:
            values.update(group)
        unknown = values - known
        if unknown:
            raise ValueError(f"{p.id}: unknown equipment classes: {sorted(unknown)}")
        if set(p.required) & set(p.optional):
            raise ValueError(f"{p.id}: equipment cannot be both required and optional")
        for group in p.required_any:
            if set(group) & set(p.optional):
                raise ValueError(f"{p.id}: required_any overlaps optional")


validate_profiles()
