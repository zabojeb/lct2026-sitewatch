"""Наблюдаемая техника → распределение вероятностей по этапам работ.

Почему не просто Jaccard
------------------------
В матрице этапов перечисления означают ВОЗМОЖНОЕ присутствие: «экскаватор ИЛИ
бульдозер ИЛИ каток», а не весь комплект разом (см. «Границы использования» в md).
Jaccard считает каждую неувиденную разрешённую машину уликой против этапа: этап
с пятью альтернативами при одном увиденном экскаваторе получает 1/5, а этап
«только экскаватор» — 1/1. Поэтому Jaccard системно выбирает этапы с узким
набором техники, а не те, что лучше объясняют увиденное.

Основной метод — байесовский, с «принципом размера» (size principle):
    P(ключ | этап) = α·[ключ ∈ work]/|work|  +  β·[ключ ∈ delivery]/|delivery|
                   + γ·фон(ключ)
Увиденная техника должна объясняться этапом (иначе остаётся только малый фоновый
член γ). Среди этапов, объясняющих всё увиденное, выигрывает более конкретный —
и тем сильнее, чем больше разной техники увидено. Неувиденная разрешённая
машина уликой не считается: отсутствие одной из альтернатив — не нарушение.

Доставка (β < α) даёт слабую улику: самосвал подтверждает работу хуже, чем
экскаватор, — как и сказано в md. Фон (γ) нужен, потому что на площадке бывает
техника, не относящаяся к текущему этапу: без него одна посторонняя машина
обнуляла бы вероятность правильного этапа.

Выход — апостериорное распределение с учётом априорного (например, из
календарного плана), свёрнутое до групп неразличимых этапов и до сводных строк.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from matrix import Stage, StageMatrix


# Визуально похожая техника: детектор устойчиво путает её между собой.
# Это стартовое допущение; в работе его заменяет матрица ошибок конкретного
# детектора, снятая на его валидационной выборке (confusion_from_counts).
LOOKALIKE = [("C", "M"), ("D", "Q"), ("L", "S"), ("B", "L"), ("X", "P"),
             ("T", "C"), ("V", "PD"), ("Z", "Q"), ("G", "B"), ("R", "B")]


def lookalike_confusion(keys, pairs=LOOKALIKE, eps: float = 0.25) -> dict:
    """C[истинный][увиденный]: с вероятностью eps машина называется одним из
    своих «двойников», иначе — правильно."""
    mates = {k: set() for k in keys}
    for a, b in pairs:
        if a in mates and b in mates:
            mates[a].add(b); mates[b].add(a)
    C = {}
    for k in keys:
        if mates[k]:
            C[k] = {k: 1 - eps, **{m: eps / len(mates[k]) for m in mates[k]}}
        else:
            C[k] = {k: 1.0}
    return C


def confusion_from_counts(counts: dict[tuple[str, str], int], keys, smooth: float = 1.0) -> dict:
    """Матрица ошибок из пар (истинный ключ, предсказанный ключ) валидации детектора."""
    C = {}
    for t in keys:
        row = {o: counts.get((t, o), 0) + (smooth if o == t else 0) for o in keys}
        z = sum(row.values())
        C[t] = {o: v / z for o, v in row.items() if v > 0}
    return C


@dataclass
class Scored:
    stage: Stage
    score: float          # метрика метода (логарифм правдоподобия, Jaccard и т.п.)
    posterior: float      # вероятность с учётом априорного распределения


class StageScorer:
    METHODS = ("bayes", "jaccard", "jaccard_work", "wjaccard")

    def __init__(self, M: StageMatrix, method: str = "bayes",
                 alpha: float = 0.75, beta: float = 0.15, gamma: float = 0.10,
                 tau: float = 0.5, delivery_weight: float = 0.3,
                 confusion: dict | None = None):
        assert method in self.METHODS, method
        self.M, self.method = M, method
        # Матрица ошибок детектора C[истинный][увиденный]. Без неё увиденная
        # «сваебойная машина» считается чистой уликой против этапа с буровой, хотя
        # детектор эти машины путает. С ней: P(увидели k | этап) =
        # Σ_k' C[k'][k]·P(k' | этап) — маргинализация по истинной технике.
        self.confusion = confusion
        self._into = None
        if confusion:
            self._into = {}
            for t, row in confusion.items():
                for o, v in row.items():
                    self._into.setdefault(o, []).append((t, v))
        self.alpha, self.beta, self.gamma = alpha, beta, gamma
        self.tau = tau                        # порог soft-присутствия для «жёстких» методов
        self.dw = delivery_weight             # вес доставки в взвешенном Jaccard
        self.cands = M.leaves
        n = len(self.cands)
        # «Редкость» ключа: в скольких этапах он допустим. Автокран разрешён в 129
        # этапах и почти ничего не говорит; буровая — в 9 и говорит много.
        df = defaultdict(int)
        for s in self.cands:
            for k in s.work | s.delivery:
                df[k] += 1
        self.idf = {k: math.log((n + 1) / (df.get(k, 0) + 1)) + 1.0 for k in M.keys}
        # Фон: распространённая техника чаще оказывается на площадке «просто так».
        tot = sum(df.get(k, 0) + 1 for k in M.keys)
        self.bg = {k: (df.get(k, 0) + 1) / tot for k in M.keys}

    # --- правдоподобие одного этапа ---------------------------------------
    def _p_key(self, s: Stage, k: str) -> float:
        a, b, g = self.alpha, self.beta, self.gamma
        # у этапа может не быть одной из частей — перераспределяем её массу
        if not s.work:
            b, a = a + b, 0.0
        if not s.delivery:
            a, b = a + b, 0.0
        p = g * self.bg[k]
        if k in s.work:
            p += a / len(s.work)
        if k in s.delivery:
            p += b / len(s.delivery)
        return p

    def _p_obs(self, s: Stage, k: str) -> float:
        if not self._into:
            return self._p_key(s, k)
        return sum(v * self._p_key(s, t) for t, v in self._into.get(k, [(k, 1.0)]))

    def _score(self, s: Stage, obs: dict[str, float]) -> float:
        if self.method == "bayes":
            return sum(o * math.log(self._p_obs(s, k)) for k, o in obs.items())
        O = {k for k, o in obs.items() if o >= self.tau}
        if self.method == "jaccard":
            S = s.work | s.delivery
            return len(O & S) / len(O | S) if O | S else 0.0
        if self.method == "jaccard_work":
            S = s.work
            return len(O & S) / len(O | S) if O | S else 0.0
        # взвешенный Jaccard (Ружичка): веса — idf, доставка с пониженным весом
        sw = {k: self.idf[k] for k in s.work}
        for k in s.delivery:
            sw.setdefault(k, self.idf[k] * self.dw)
        ow = {k: self.idf[k] * o for k, o in obs.items()}
        keys = set(sw) | set(ow)
        num = sum(min(sw.get(k, 0), ow.get(k, 0)) for k in keys)
        den = sum(max(sw.get(k, 0), ow.get(k, 0)) for k in keys)
        return num / den if den else 0.0

    # --- ранжирование -------------------------------------------------------
    def group_prior(self) -> dict[int, float]:
        """Равная вероятность каждой РАЗЛИЧИМОЙ группе, а не каждой строке XLSX.

        Перечень детализирован неравномерно: «вынос сетей» расписан на десяток
        одинаковых по технике подстрок (теплосеть, вода, газ…), а сваи — на три.
        Если дать равный вес строкам, группа выигрывает числом строк, то есть
        артефактом документа, а не частотой работ. Без плана нейтральнее считать
        равновероятными различимые гипотезы.
        """
        size = defaultdict(int)
        for s in self.cands:
            size[s.signature] += 1
        g = len(size)
        return {s.row: 1.0 / (g * size[s.signature]) for s in self.cands}

    def rank(self, obs: dict[str, float], prior: dict[int, float] | None = None,
             temperature: float = 1.0) -> list[Scored]:
        """obs: ключ → степень уверенности в присутствии (0..1), уже слитая по камерам.
        prior: строка XLSX → априорный вес (например, из календарного плана);
        без него — равномерно по различимым группам, см. group_prior()."""
        obs = {k: o for k, o in obs.items() if o > 0 and k in self.M.keys}
        prior = prior or self.group_prior()
        raw = [(s, self._score(s, obs)) for s in self.cands]
        if self.method == "bayes":
            logits = [sc / temperature for _, sc in raw]
        else:
            # похожести переводим в «логиты», чтобы вероятности были сравнимы
            logits = [sc * 20.0 / temperature for _, sc in raw]
        if prior:
            logits = [lg + math.log(max(prior.get(s.row, 1e-6), 1e-12))
                      for (s, _), lg in zip(raw, logits)]
        mx = max(logits)
        w = [math.exp(lg - mx) for lg in logits]
        z = sum(w)
        out = [Scored(s, sc, wi / z) for (s, sc), wi in zip(raw, w)]
        return sorted(out, key=lambda r: (-r.posterior, r.stage.row))

    # --- свёртки ------------------------------------------------------------
    def groups(self, ranked: list[Scored]):
        """Этапы с одинаковым набором техники по технике неразличимы: сворачиваем
        их в группу и складываем вероятности. Выбор внутри группы — дело плана."""
        g = defaultdict(lambda: [0.0, []])
        for r in ranked:
            g[r.stage.signature][0] += r.posterior
            g[r.stage.signature][1].append(r.stage)
        return sorted(((p, members) for p, members in g.values()), key=lambda t: -t[0])

    def rollup(self, ranked: list[Scored]) -> list[tuple[Stage, float]]:
        """Вероятность сводной строки XLSX = сумма вероятностей её листовых детей."""
        post = {r.stage.row: r.posterior for r in ranked}
        res = []
        for s in self.M.stages.values():
            if s.is_summary:
                res.append((s, sum(post.get(c, 0.0) for c in s.children)))
        return sorted(res, key=lambda t: -t[1])

    def explain(self, s: Stage, obs: dict[str, float]) -> dict:
        """Почему этап получил свой балл — чтобы предупреждение было обоснованным."""
        seen = {k for k, o in obs.items() if o > 0}
        return {"работа": sorted(seen & s.work),
                "только доставка": sorted((seen & s.delivery) - s.work),
                "не объясняется этапом": sorted(seen - s.work - s.delivery),
                "допустимо, но не видно": sorted(s.work - seen)}


def plan_check(scorer: "StageScorer", obs: dict[str, float], planned_rows: list[int],
               threshold: float = 3.5) -> dict:
    """Согласуется ли увиденная техника с плановым этапом.

    Решаем ТОЛЬКО по уликам — по отношению правдоподобий:
        LR = log P(улики | лучший этап) − log P(улики | плановый этап).
    Апостериорную вероятность для этого брать нельзя: в неё план уже заложен
    как априорное, и проверка превращается в круг — сильный план «подтверждает»
    сам себя при любых уликах.

    threshold — во сколько раз (в логарифме) другой этап должен объяснять
    увиденное лучше планового, чтобы поднять тревогу. 3.5 ≈ в 33 раза: на
    синтетике это ≈5 % ложных тревог при ~70 % пойманных отклонений (AUC 0.91).
    """
    assert scorer.method == "bayes"
    obs = {k: o for k, o in obs.items() if o > 0 and k in scorer.M.keys}
    planned = [scorer.M.stages[r] for r in planned_rows if r in scorer.M.stages]
    planned = [s for s in planned if s.observable and not s.is_summary]
    if not obs:
        return {"verdict": "нет данных", "lr": 0.0}
    if not planned:
        return {"verdict": "плановый этап не наблюдаем по камерам", "lr": 0.0}
    ll_plan = max(scorer._score(s, obs) for s in planned)
    best = max(scorer.cands, key=lambda s: scorer._score(s, obs))
    lr = scorer._score(best, obs) - ll_plan
    worst = max(planned, key=lambda s: scorer._score(s, obs))
    ex = scorer.explain(worst, obs)
    return {"verdict": "расходится с планом" if lr > threshold else "согласуется с планом",
            "lr": round(lr, 2),
            "лучше объясняет": best,
            "техника вне планового этапа": ex["не объясняется этапом"],
            "плановая работа подтверждена техникой": ex["работа"]}


def plan_prior(M: StageMatrix, planned_rows: list[int], weight: float = 0.8,
               neighbourhood: int = 3) -> dict[int, float]:
    """Априорное распределение из календарного плана.

    Основная масса — плановым этапам; небольшая — соседним строкам XLSX (в перечне
    они идут примерно в технологическом порядке, и соседний этап — самое вероятное
    отклонение); остаток — равномерно. Нулевой вероятности не даём никому: иначе
    фактическое отклонение от плана невозможно было бы обнаружить.
    """
    cands = [s.row for s in M.leaves]
    p = {r: (1 - weight) * 0.5 / len(cands) for r in cands}
    near = {r + d for r in planned_rows for d in range(-neighbourhood, neighbourhood + 1)} & set(cands)
    for r in near:
        p[r] += (1 - weight) * 0.5 / max(len(near), 1)
    for r in planned_rows:
        if r in p:
            p[r] += weight / len(planned_rows)
    z = sum(p.values())
    return {r: v / z for r, v in p.items()}
