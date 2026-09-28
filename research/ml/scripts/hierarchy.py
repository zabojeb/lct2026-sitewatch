"""Иерархия классов: группа техники + мягкая деградация при путанице.

Проблема. Автокран, гусеничный кран и кран-манипулятор на 35 px различаются
плохо — это три вида стрелы, а стрела в кадре шириной 35 px занимает считанные
пиксели. Жёсткий top-1 здесь даёт уверенно неверный класс.

Решение. Детектор остаётся 16-классовым (менять архитектуру не нужно), но поверх
softmax добавляется правило: если уверенность в конкретном классе низкая, а сумма
по его группе высокая — отдаём группу, а не класс.

Почему это работает именно на нашей задаче: правила в `stage_rules.yaml` в
половине случаев и так оперируют группой. Этапу 12.3.4 «фундамент» нужно
«средство подачи бетона» — автокран это, гусеничный или башенный, неважно.
Значит потеря точного класса не ломает сопоставление, а «уверенно неверный
класс» — ломает.
"""
from __future__ import annotations

GROUPS: dict[str, list[str]] = {
    "земляная":   ["excavator", "bulldozer", "wheel_loader", "backhoe_loader", "grader"],
    "подъёмная":  ["tower_crane", "mobile_crane", "crawler_crane", "knuckle_crane"],
    "бетонная":   ["concrete_mixer", "concrete_pump"],
    "транспорт":  ["dump_truck", "truck"],
    "дорожная":   ["roller", "grader"],
    "буровая":    ["pile_rig"],
}
CLASS_TO_GROUPS: dict[str, list[str]] = {}
for g, members in GROUPS.items():
    for c in members:
        CLASS_TO_GROUPS.setdefault(c, []).append(g)


def resolve(class_probs: dict[str, float], cls_thr: float = 0.45,
            group_thr: float = 0.60) -> tuple[str, str, float]:
    """Свести распределение по классам к ответу нужной степени конкретности.

    Возвращает (уровень, метка, уверенность), где уровень — 'class' | 'group' | 'unknown'.

    >>> resolve({"mobile_crane": 0.30, "crawler_crane": 0.28, "tower_crane": 0.22})
    ('group', 'подъёмная', 0.8)
    >>> resolve({"excavator": 0.81, "bulldozer": 0.05})
    ('class', 'excavator', 0.81)
    """
    if not class_probs:
        return "unknown", "", 0.0

    top_cls, top_p = max(class_probs.items(), key=lambda kv: kv[1])
    if top_p >= cls_thr:
        return "class", top_cls, round(top_p, 3)

    # класс не набрал — пробуем группу
    group_p = {g: sum(p for c, p in class_probs.items() if g in CLASS_TO_GROUPS.get(c, []))
               for g in GROUPS}
    top_g, gp = max(group_p.items(), key=lambda kv: kv[1])
    if gp >= group_thr:
        return "group", top_g, round(gp, 3)
    return "unknown", "", round(top_p, 3)


def satisfies(observed: list[tuple[str, str]], requirement: str) -> bool:
    """Покрывает ли наблюдение требование правила (класс ИЛИ группа).

    `observed` — список (уровень, метка) из resolve(); `requirement` — имя класса
    из stage_rules.yaml. Наблюдение уровня 'group' засчитывается, если требуемый
    класс входит в эту группу: «видим подъёмную технику» удовлетворяет требованию
    «нужен автокран» с оговоркой, которую интерфейс показывает пользователю.
    """
    for level, label in observed:
        if level == "class" and label == requirement:
            return True
        if level == "group" and requirement in GROUPS.get(label, []):
            return True
    return False
