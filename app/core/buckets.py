"""Bucket-aware parser + edge for Polymarket weather markets.

Polymarket lists weather as bucket markets:
  - "Will the highest temperature in Austin be 71°F or below on May 8?"  -> (-inf, 71F]
  - "Will the highest temperature in Austin be 71°F or above on May 8?"  -> [71F, +inf)
  - "Will the highest temperature in Austin be 71°F on May 8?"            -> [71F, 72F)
  - "Will the highest temperature in Austin be between 74-75°F on May 8?" -> [74F, 76F)

We always reduce to a Bucket in °C with optional lo/hi (None = open tail).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


@dataclass
class Bucket:
    lo_c: Optional[float]   # inclusive, None = -inf
    hi_c: Optional[float]   # exclusive, None = +inf
    raw_unit: str = "C"
    raw_lo: Optional[float] = None
    raw_hi: Optional[float] = None

    def label(self) -> str:
        u = self.raw_unit
        if self.lo_c is None and self.raw_hi is not None:
            return f"≤{self.raw_hi}°{u}"
        if self.hi_c is None and self.raw_lo is not None:
            return f"≥{self.raw_lo}°{u}"
        if self.raw_lo is not None and self.raw_hi is not None and self.raw_lo == self.raw_hi:
            return f"={self.raw_lo}°{u}"
        if self.raw_lo is not None and self.raw_hi is not None:
            return f"{self.raw_lo}–{self.raw_hi}°{u}"
        return "?"


_CITY_RE = re.compile(r"\b(?:in|at)\s+([A-Z][a-zA-Z\.\-' ]{1,30}?)(?=\s+(?:be|reach|hit|exceed|above|below|or|on)\b|\?)", re.UNICODE)
_BETWEEN_RE = re.compile(r"between\s+(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*°?\s*([CFcf])", re.I)
_OR_BELOW_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*°?\s*([CFcf])\s*or\s*(?:below|less|lower)", re.I)
_OR_ABOVE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*°?\s*([CFcf])\s*or\s*(?:above|higher|more)", re.I)
_EXACT_RE = re.compile(r"\bbe\s+(-?\d+(?:\.\d+)?)\s*°?\s*([CFcf])\b", re.I)


def parse_question(question: str) -> tuple[Optional[str], Optional[Bucket]]:
    if not question:
        return None, None

    city = None
    m = _CITY_RE.search(question)
    if m:
        city = m.group(1).strip().rstrip("?.,'\" ")

    if (m := _BETWEEN_RE.search(question)):
        a, b, u = float(m.group(1)), float(m.group(2)), m.group(3).upper()
        lo_raw, hi_raw = (a, b) if a <= b else (b, a)
        lo_c = lo_raw if u == "C" else _f_to_c(lo_raw)
        # bucket high is exclusive, +1 unit (the next bucket starts there)
        hi_c = (hi_raw + 1) if u == "C" else _f_to_c(hi_raw + 1)
        return city, Bucket(lo_c=lo_c, hi_c=hi_c, raw_unit=u, raw_lo=lo_raw, raw_hi=hi_raw)

    if (m := _OR_BELOW_RE.search(question)):
        n, u = float(m.group(1)), m.group(2).upper()
        # "N°F or below" typically means highest will be at most N (inclusive of N bucket)
        hi_c = (n + 1) if u == "C" else _f_to_c(n + 1)
        return city, Bucket(lo_c=None, hi_c=hi_c, raw_unit=u, raw_hi=n)

    if (m := _OR_ABOVE_RE.search(question)):
        n, u = float(m.group(1)), m.group(2).upper()
        lo_c = n if u == "C" else _f_to_c(n)
        return city, Bucket(lo_c=lo_c, hi_c=None, raw_unit=u, raw_lo=n)

    if (m := _EXACT_RE.search(question)):
        n, u = float(m.group(1)), m.group(2).upper()
        lo_c = n if u == "C" else _f_to_c(n)
        hi_c = (n + 1) if u == "C" else _f_to_c(n + 1)
        return city, Bucket(lo_c=lo_c, hi_c=hi_c, raw_unit=u, raw_lo=n, raw_hi=n)

    return city, None


def prob_in_bucket(b: Bucket, mu_c: float, sigma_c: float) -> float:
    if sigma_c <= 0:
        sigma_c = 1.0
    if b.lo_c is None and b.hi_c is None:
        return 1.0
    p_lo = 0.0 if b.lo_c is None else _phi((b.lo_c - mu_c) / sigma_c)
    p_hi = 1.0 if b.hi_c is None else _phi((b.hi_c - mu_c) / sigma_c)
    return max(0.0, min(1.0, p_hi - p_lo))


@dataclass
class EdgeResult:
    side: str             # YES or NO
    edge: float
    p_real: float
    p_market: float
    limit_price: float


def compute_bucket_edge(
    *,
    bucket: Bucket,
    mu_c: float,
    sigma_c: float,
    yes_ask: Optional[float],
    yes_bid: Optional[float],
    no_ask: Optional[float],
    no_bid: Optional[float],
) -> Optional[EdgeResult]:
    p_yes = prob_in_bucket(bucket, mu_c, sigma_c)
    p_no = 1.0 - p_yes

    cands: list[EdgeResult] = []
    if yes_ask is not None and 0 < yes_ask < 1:
        cands.append(EdgeResult("YES", p_yes - yes_ask, p_yes, yes_ask, yes_ask))
    if no_ask is not None and 0 < no_ask < 1:
        cands.append(EdgeResult("NO", p_no - no_ask, p_no, no_ask, no_ask))
    if not cands:
        return None
    return max(cands, key=lambda r: r.edge)
