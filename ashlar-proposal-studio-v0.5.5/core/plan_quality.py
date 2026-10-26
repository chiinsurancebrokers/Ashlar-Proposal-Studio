"""Which plan is best on merit, whatever it costs.

The family optimiser answers "what fits these needs for this budget". A broker also needs the other
answer: which plan is best on what it gives, however expensive. This module ranks plans on cover
quality alone. Price never enters the score.

Six dimensions, each 0 to 1, equal weight:

    limit       annual hospital limit, on a log scale from EUR 25,000 (0) to EUR 3,000,000 (1)
    deductible  participation per hospital stay or year, EUR 0 (1) to EUR 2,000 or more (0)
    waiting     total months of waiting across every condition the plan lists (0 months = 1, 300 or more = 0)
    area        where treatment is covered: Greece only, EU, abroad with its own limit, worldwide
    network     breadth of hospitals and direct settlement, a broker rating from 1 to 5
    exclusions  how few permanent exclusions, a broker rating from 1 to 5

Rules that keep it honest:
* Limit, deductible, waiting and area come from the offer or the policy wording. Network and exclusions
  are the broker's rating and are shown as such.
* A dimension counts only when every plan being compared has it. A missing figure never earns credit for
  one plan and nothing for another. The dimensions left out are named in the study.
* The score is a ranking aid. The policy wording prevails.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from core import waiting_periods

DIMENSIONS = ("limit", "deductible", "waiting", "area", "network", "exclusions")
LIMIT_FLOOR, LIMIT_TOP = 25_000, 3_000_000
DEDUCTIBLE_CAP = 2_000
WAITING_CAP_MONTHS = 300
AREA = {"greece": 0.33, "eu": 0.67, "abroad": 0.85, "world": 1.0}


@dataclass(frozen=True)
class PlanQuality:
    """Facts about one plan. ``None`` means the figure is not known."""

    limit: float | None = None                     # annual hospital limit in EUR
    deductible: float | None = None                # participation in EUR
    waiting_tables: tuple[str, ...] | None = None  # keys of core.waiting_periods tables
    area: str | None = None                        # a key of AREA
    network: int | None = None                     # broker rating 1 to 5
    exclusions: int | None = None                  # broker rating 1 to 5, 5 = fewest
    notes: Mapping[str, str] = field(default_factory=dict)  # dimension -> where the figure comes from


def months(period: str) -> float:
    """Months in an English waiting-period text such as 'After the first 30 days' or '24 (two) months'."""
    t = period.lower()
    if m := re.search(r"\((\d+)\)\s*months?", t) or re.search(r"(\d+)\s*months?", t):
        return float(m.group(1))
    if m := re.search(r"\((\d+)\)\s*(?:consecutive\s+)?insurance years?", t):
        return 12.0 * int(m.group(1))
    if "first insurance year" in t:
        return 12.0
    if m := re.search(r"(\d+)\s*days?", t):
        return round(int(m.group(1)) / 30)
    raise ValueError(f"Cannot read a waiting period from: {period!r}")


def waiting_months(keys: Iterable[str]) -> float:
    """Sum of the months of every condition in the plan's waiting tables."""
    return sum(months(row[2]) for key in keys for row in waiting_periods.TABLES[key]["rows"])


def scores(q: PlanQuality) -> dict[str, float | None]:
    out: dict[str, float | None] = {d: None for d in DIMENSIONS}
    if q.limit is not None:
        out["limit"] = min(1.0, max(0.0, math.log(max(q.limit, 1) / LIMIT_FLOOR) / math.log(LIMIT_TOP / LIMIT_FLOOR)))
    if q.deductible is not None:
        out["deductible"] = 1.0 - min(q.deductible, DEDUCTIBLE_CAP) / DEDUCTIBLE_CAP
    if q.waiting_tables is not None:
        out["waiting"] = 1.0 - min(waiting_months(q.waiting_tables), WAITING_CAP_MONTHS) / WAITING_CAP_MONTHS
    if q.area is not None:
        out["area"] = AREA[q.area]
    if q.network is not None:
        out["network"] = (q.network - 1) / 4
    if q.exclusions is not None:
        out["exclusions"] = (q.exclusions - 1) / 4
    return out


@dataclass(frozen=True)
class Merit:
    key: str
    score: float
    parts: Mapping[str, float | None]


def common_dimensions(plans: Mapping[str, PlanQuality]) -> tuple[str, ...]:
    all_scores = [scores(q) for q in plans.values()]
    return tuple(d for d in DIMENSIONS if all_scores and all(s[d] is not None for s in all_scores))


def rank(plans: Mapping[str, PlanQuality]) -> tuple[list[Merit], tuple[str, ...]]:
    """Plans best first, and the dimensions that were scored. Ties keep the order given."""
    dims = common_dimensions(plans)
    if not dims:
        return [], dims
    merits = []
    for key, q in plans.items():
        s = scores(q)
        merits.append(Merit(key, sum(s[d] for d in dims) / len(dims), s))
    return sorted(merits, key=lambda m: -m.score), dims


def combination_merit(plan_keys: Sequence[str], merits: Mapping[str, float]) -> float | None:
    """Mean merit of the plans in a combination, one vote per person. Plans without a rating are skipped."""
    vals = [merits[k] for k in plan_keys if k in merits]
    return sum(vals) / len(vals) if vals else None
