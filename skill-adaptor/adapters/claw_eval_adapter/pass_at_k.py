"""Pass@k helpers for Claw-Eval (paper Table 1 reports Pass@3%).

Uses the standard unbiased Pass@k estimator when n trials and c successes
are known (same family as HumanEval / claw-eval compute_pass_at_k).
"""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased Pass@k: 1 - C(n-c, k) / C(n, k) for k <= n, else 1.0 if c > 0 else 0.0."""
    if n <= 0 or k <= 0:
        return 0.0
    if c < 0:
        c = 0
    if c > n:
        c = n
    if k > n:
        k = n
    if n - c < k:
        return 1.0

    def _comb(a: int, b: int) -> float:
        if b < 0 or b > a:
            return 0.0
        return float(math.comb(a, b))

    return 1.0 - _comb(n - c, k) / _comb(n, k)


def pass_at_k_from_trials(successes: Sequence[bool], k: int = 3) -> float:
    n = len(successes)
    c = sum(1 for s in successes if s)
    return pass_at_k(n, c, k)


def aggregate_pass_at_k(
    per_task_trials: Iterable[Sequence[bool]],
    k: int = 3,
) -> float:
    """Mean Pass@k across tasks (each task has its own n trials)."""
    scores: List[float] = []
    for trials in per_task_trials:
        scores.append(pass_at_k_from_trials(list(trials), k=k))
    if not scores:
        return 0.0
    return float(sum(scores) / len(scores))
