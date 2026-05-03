"""
Analytics: KPIs, gap analysis, streak detection, generation breakdown.
All functions accept entries as Dict[int, PokemonEntry] (duck-typed).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

GENERATIONS: Dict[str, Tuple[int, int]] = {
    "Gen 1 · Kanto":  (1,    151),
    "Gen 2 · Johto":  (152,  251),
    "Gen 3 · Hoenn":  (252,  386),
    "Gen 4 · Sinnoh": (387,  493),
    "Gen 5 · Unova":  (494,  649),
    "Gen 6 · Kalos":  (650,  721),
    "Gen 7 · Alola":  (722,  809),
    "Gen 8 · Galar":  (810,  905),
    "Gen 9 · Paldea": (906, 1025),
}


@dataclass
class Gap:
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start + 1

    @property
    def label(self) -> str:
        return f"#{self.start}" if self.start == self.end else f"#{self.start}–#{self.end}"


def _is_collected(num: int, entries: dict) -> bool:
    entry = entries.get(num)
    return bool(entry and entry.collected)


def find_gaps(entries: dict, total: int) -> List[Gap]:
    """All contiguous missing ranges within 1..total."""
    gaps: List[Gap] = []
    gap_start: Optional[int] = None

    for num in range(1, total + 1):
        if not _is_collected(num, entries):
            if gap_start is None:
                gap_start = num
        else:
            if gap_start is not None:
                gaps.append(Gap(gap_start, num - 1))
                gap_start = None

    if gap_start is not None:
        gaps.append(Gap(gap_start, total))

    return gaps


def find_longest_streak(entries: dict, total: int) -> Tuple[int, int, int]:
    """Return (start, end, length) of the longest consecutive collected run."""
    best: Tuple[int, int, int] = (0, 0, 0)
    streak_start: Optional[int] = None
    streak_len = 0

    for num in range(1, total + 1):
        if _is_collected(num, entries):
            if streak_start is None:
                streak_start = num
            streak_len += 1
            if streak_len > best[2]:
                best = (streak_start, num, streak_len)
        else:
            streak_start = None
            streak_len = 0

    return best


def compute_kpis(entries: dict, api_total: int, count_untracked: bool = True) -> dict:
    effective_total = api_total if count_untracked else max(entries.keys(), default=0)
    collected = sum(1 for n in range(1, effective_total + 1) if _is_collected(n, entries))
    missing = effective_total - collected
    pct = (collected / effective_total * 100) if effective_total > 0 else 0.0

    gaps = find_gaps(entries, effective_total)
    largest_gap = max(gaps, key=lambda g: g.size, default=None)
    streak = find_longest_streak(entries, effective_total)

    return {
        "api_total": api_total,
        "effective_total": effective_total,
        "collected": collected,
        "missing": missing,
        "pct_complete": pct,
        "largest_gap": largest_gap,
        "longest_streak": streak,
        "gaps": gaps,
    }


def get_generation_stats(entries: dict) -> Dict[str, dict]:
    stats: Dict[str, dict] = {}
    for gen_name, (start, end) in GENERATIONS.items():
        total = end - start + 1
        collected = sum(1 for n in range(start, end + 1) if _is_collected(n, entries))
        stats[gen_name] = {
            "range": (start, end),
            "total": total,
            "collected": collected,
            "missing": total - collected,
            "pct": (collected / total * 100) if total > 0 else 0.0,
        }
    return stats
