from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


def _phi(z: float) -> float:
    """Standard normal CDF without scipy (Abramowitz & Stegun)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def prob_temp_at_least(threshold_c: float, mu_c: float, sigma_c: float) -> float:
    """P(T >= threshold) given Normal(mu, sigma) forecast."""
    if sigma_c <= 0:
        return 1.0 if mu_c >= threshold_c else 0.0
    z = (threshold_c - mu_c) / sigma_c
    return 1.0 - _phi(z)


def prob_temp_at_most(threshold_c: float, mu_c: float, sigma_c: float) -> float:
    return 1.0 - prob_temp_at_least(threshold_c, mu_c, sigma_c)


@dataclass
class EdgeResult:
    side: str  # YES or NO
    edge: float
    p_real: float
    p_market: float
    limit_price: float


def compute_edge(
    *,
    direction: str,           # 'gte' or 'lte'
    threshold_c: float,
    mu_c: float,
    sigma_c: float,
    yes_ask: Optional[float],
    yes_bid: Optional[float],
    no_ask: Optional[float],
    no_bid: Optional[float],
) -> Optional[EdgeResult]:
    """Pick the best side to take and return the edge (p_real - p_market).

    Returns None if no side is tradeable (missing quotes).
    """
    if direction == "gte":
        p_yes = prob_temp_at_least(threshold_c, mu_c, sigma_c)
    else:
        p_yes = prob_temp_at_most(threshold_c, mu_c, sigma_c)
    p_no = 1.0 - p_yes

    candidates: list[EdgeResult] = []
    if yes_ask is not None and 0 < yes_ask < 1:
        candidates.append(EdgeResult("YES", p_yes - yes_ask, p_yes, yes_ask, yes_ask))
    if no_ask is not None and 0 < no_ask < 1:
        candidates.append(EdgeResult("NO", p_no - no_ask, p_no, no_ask, no_ask))

    if not candidates:
        return None
    best = max(candidates, key=lambda r: r.edge)
    return best
