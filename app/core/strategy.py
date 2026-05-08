"""
Estrategia corrigida — permite TODOS os mercados de temperatura:
1. Mercados exatos (Warsaw 14°C, Shanghai 23°C) — PERMITIDOS
2. Mercados de faixa (Atlanta 76-77°F) — PERMITIDOS
3. Mercados extremos (or below / or above) — PERMITIDOS
4. Timing ate 7 dias antes da resolucao
5. Edge minimo configuravel (5% padrao)
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional
from .buckets import Bucket


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def horizon_sigma(hours: float) -> float:
    if hours <= 1:   return 0.5
    if hours <= 3:   return 0.8
    if hours <= 6:   return 1.0
    if hours <= 12:  return 1.4
    if hours <= 24:  return 1.8
    if hours <= 48:  return 2.5
    if hours <= 96:  return 3.0
    return 3.5


def is_extreme_market(bucket: Bucket) -> bool:
    return bucket.lo_c is None or bucket.hi_c is None


def prob_in_bucket(bucket: Bucket, mu_c: float, sigma_c: float) -> float:
    if sigma_c <= 0:
        sigma_c = 0.5
    p_lo = 0.0 if bucket.lo_c is None else _phi((bucket.lo_c - mu_c) / sigma_c)
    p_hi = 1.0 if bucket.hi_c is None else _phi((bucket.hi_c - mu_c) / sigma_c)
    return max(0.0, min(1.0, p_hi - p_lo))


@dataclass
class StrategyResult:
    side: str
    edge: float
    p_real: float
    p_market: float
    limit_price: float
    confidence: str
    reason: str


def evaluate(
    *,
    bucket: Bucket,
    mu_c: float,
    sigma_c: float,
    yes_ask: Optional[float],
    yes_bid: Optional[float],
    no_ask: Optional[float],
    no_bid: Optional[float],
    hours_to_resolve: float,
    min_edge: float = 0.05,
) -> Optional[StrategyResult]:
    if hours_to_resolve < 0.3:
        return None
    if hours_to_resolve > 168:
        return None

    # Confia no sigma do ensemble (ja incorpora horizonte + divergencia OWM/OMeo).
    # horizon_sigma vira piso de 50% pra evitar confianca excessiva quando
    # so uma fonte estiver disponivel.
    effective_sigma = max(sigma_c, horizon_sigma(hours_to_resolve) * 0.5)

    p_yes = prob_in_bucket(bucket, mu_c, effective_sigma)
    p_no  = 1.0 - p_yes

    candidates = []
    if yes_ask is not None and 0 < yes_ask < 0.98:
        edge = p_yes - yes_ask
        candidates.append(StrategyResult(
            side="YES", edge=edge, p_real=p_yes,
            p_market=yes_ask, limit_price=yes_ask,
            confidence="", reason="",
        ))
    if no_ask is not None and 0 < no_ask < 0.98:
        edge = p_no - no_ask
        candidates.append(StrategyResult(
            side="NO", edge=edge, p_real=p_no,
            p_market=no_ask, limit_price=no_ask,
            confidence="", reason="",
        ))

    if not candidates:
        return None

    best = max(candidates, key=lambda r: r.edge)
    if best.edge < min_edge:
        return None

    is_extreme = is_extreme_market(bucket)
    if best.edge >= 0.30 and is_extreme:
        confidence = "HIGH"
    elif best.edge >= 0.15:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    if bucket.lo_c is not None and bucket.hi_c is not None:
        width = bucket.hi_c - bucket.lo_c
        reason = f"faixa {bucket.lo_c:.1f}-{bucket.hi_c:.1f}C (width={width:.1f}C) previsao={mu_c:.1f}C"
    elif is_extreme:
        threshold = bucket.lo_c if bucket.hi_c is None else bucket.hi_c
        dist_c = abs(mu_c - threshold)
        reason = f"extremo: previsao {mu_c:.1f}C threshold {threshold:.1f}C dist={dist_c:.1f}C"
    else:
        reason = f"previsao {mu_c:.1f}C sigma={effective_sigma:.1f}C"

    best.confidence = confidence
    best.reason = reason
    return best
