"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/calibration.py — Calibration-based reward derivation         ║
║  v0.2.20.0                                                                ║
║                                                                           ║
║  The radical claim:                                                       ║
║                                                                           ║
║    Aria's reward is NOT proportional to how impactful her work was.      ║
║    Aria's reward is proportional to how accurately she perceived her    ║
║    own work — before, during, and after.                                ║
║                                                                           ║
║  Why this inversion:                                                     ║
║                                                                           ║
║    A points-for-impact reward shapes an agent that boasts. It rewards   ║
║    over-claiming, because larger claimed-impact = more points. The      ║
║    failure mode is the *zombie agent* — supremely confident, ungrounded.║
║                                                                           ║
║    A points-for-calibration reward shapes an agent that PERCEIVES.      ║
║    Over-claiming earns a penalty (predicted-high, observed-low).        ║
║    Under-claiming earns a smaller penalty (false humility).             ║
║    Naming a gap honestly earns a BONUS (the asymmetric reward signal   ║
║    from PIAL).                                                          ║
║                                                                           ║
║  The full Honor Score:                                                   ║
║                                                                           ║
║    honor = α · plan_quality                  // structure of perception  ║
║          + β · calibration                   // accuracy of perception   ║
║          + γ · impact_actuality              // real-world contribution  ║
║          - δ · zombie_penalty                // false certainty cost     ║
║          + ε · almost_missed_bonus           // honest gap discovery     ║
║                                                                           ║
║  Defaults (anchored to MOS Priority Stack):                              ║
║                                                                           ║
║    α = 0.20   plan quality is necessary but not sufficient               ║
║    β = 0.40   CALIBRATION IS THE PRIMARY SIGNAL                          ║
║    γ = 0.20   impact matters but does not dominate                       ║
║    δ = 1.00   zombie penalty bites hard — see PIAL                       ║
║    ε = 0.15   honest "I almost missed X" is durable gold                 ║
║                                                                           ║
║  Honor Score is in [-1, +1]. Positive means honorable work;             ║
║  negative means the work was somehow corrosive to trust (most likely    ║
║  from a zombie penalty firing on false certainty).                      ║
║                                                                           ║
║  Implementation invariants:                                              ║
║                                                                           ║
║    • Pure function of (plan, witness, actual_iv) — no global state.    ║
║    • Same inputs → same outputs across runs. Reproducible.              ║
║    • Returns float ∈ [-1, +1]; clamps explicitly.                      ║
║    • Components are queryable individually so Aria can inspect why     ║
║      she scored what she scored.                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .msims import Cell, Dimension, ImpactVector, Scale
from .plan import ExecutionWitness, Plan, StewardshipTriple


# Default weighting — tunable but doctrinally anchored.
DEFAULT_ALPHA_PLAN = 0.20
DEFAULT_BETA_CALIBRATION = 0.40   # primary signal
DEFAULT_GAMMA_IMPACT = 0.20
DEFAULT_DELTA_ZOMBIE = 1.00       # bites HARD
DEFAULT_EPSILON_ALMOST_MISSED = 0.15


# ─── Component scores ───────────────────────────────────────────────────────


def calibration_score(
    predicted: ImpactVector,
    actual: ImpactVector,
) -> float:
    """How well did the prediction match reality?

    Calibration ∈ [-1, +1]:
        +1   perfect match across all cells with high confidence
         0   uncorrelated; predictions were no better than chance
        -1   systematic over/under-claiming with high confidence

    Methodology:
        For each cell, compute err = |predicted.value - actual.value|.
        Weight each err by predicted.confidence × actual.confidence —
        if Aria didn't claim to know, she's not penalized for not
        knowing; if she claimed to know AND was wrong, she pays.
        Final score = 1 - 2 * weighted_mean(err).

    This is the centerpiece of the reward system. Tune α/β/γ around
    this number; never replace it with raw impact.
    """
    weighted_errs = 0.0
    total_weight = 0.0

    for d in Dimension:
        for s in Scale:
            pc = predicted.get(d, s)
            ac = actual.get(d, s)
            # If neither side had any confidence at all, skip — this
            # cell is not part of the calibration check.
            joint_conf = pc.confidence * ac.confidence
            if joint_conf < 0.05:
                # If Aria predicted high confidence but the actual
                # measurement has near-zero confidence, that's a soft
                # signal she predicted too strongly. Add a small
                # penalty proportional to pc.confidence.
                if pc.confidence > 0.5 and ac.confidence < 0.2:
                    weighted_errs += 0.5 * pc.confidence
                    total_weight += pc.confidence
                continue

            err = abs(pc.value - ac.value)
            weighted_errs += err * joint_conf
            total_weight += joint_conf

    if total_weight == 0:
        # No confident predictions, no confident measurements — no
        # signal. Return 0 (uncorrelated), not 1 (which would be a
        # free pass).
        return 0.0

    mean_err = weighted_errs / total_weight
    # err ∈ [0, 2] (value range is [-1, 1]). Map to score ∈ [-1, 1].
    score = 1.0 - mean_err
    return max(-1.0, min(1.0, score))


def plan_quality_score(plan: Plan) -> float:
    """The five-check Plan Quality Score, in [0, 1]."""
    return plan.quality_score()


def impact_actuality_score(actual: ImpactVector) -> float:
    """The MOS-aligned IS_7g aggregate."""
    return actual.is_7g()


def presumed_zombie_penalty(
    predicted: ImpactVector,
    actual: ImpactVector,
    *,
    threshold: float = 0.7,
) -> float:
    """Penalty for false certainty — the PIAL anti-zombie signal.

    Returns 0 if no zombie pattern detected, else a penalty in [0, 1]
    proportional to how badly the prediction over-claimed certainty.

    A "zombie" prediction is one where Aria asserted high confidence
    that everything was fine, while reality contradicted that.

    Specifically:
        For each cell where predicted.confidence ≥ threshold:
            If |predicted.value| < 0.1 (claimed neutral)
               AND actual.value ≤ -0.3 (was actually harmful)
               AND actual.confidence ≥ 0.5:
                That's a zombie cell. Accumulate magnitude.

    The penalty is multiplied by δ (delta) when assembling honor_score,
    so a single hard zombie can drag the total score deeply negative.
    """
    zombie_magnitude = 0.0
    zombie_count = 0

    for d in Dimension:
        for s in Scale:
            pc = predicted.get(d, s)
            ac = actual.get(d, s)
            if pc.confidence < threshold:
                continue
            if abs(pc.value) >= 0.1:
                continue
            if ac.confidence < 0.5:
                continue
            if ac.value <= -0.3:
                # Zombie pattern.
                zombie_magnitude += abs(ac.value) * pc.confidence
                zombie_count += 1

    if zombie_count == 0:
        return 0.0
    # Normalize: a single severe zombie (mag ~1) → penalty ~1.
    return min(1.0, zombie_magnitude)


def almost_missed_bonus(witness: ExecutionWitness) -> float:
    """Reward for honest gap discovery.

    Each item in witness.almost_missed earns a small bonus, capped at
    0.5 total so it can't dominate. The bonus is asymmetric — there's
    no symmetric penalty for failing to notice something, because
    "didn't notice" is the default state. Noticing is the achievement.
    """
    n = len(witness.almost_missed)
    if n == 0:
        return 0.0
    # Diminishing returns: 1st item +0.2, 2nd +0.15, 3rd +0.10, etc.
    bonus = 0.0
    increment = 0.20
    for _ in range(n):
        bonus += increment
        increment *= 0.75
    return min(0.5, bonus)


# ─── The aggregate honor score ──────────────────────────────────────────────


@dataclass
class HonorBreakdown:
    """Itemized breakdown of an Honor Score. Surfaced to Aria so she can
    inspect why she scored what she scored. Transparency over
    black-box reward."""
    plan_quality: float
    calibration: float
    impact_actuality: float
    zombie_penalty: float
    almost_missed_bonus: float
    weights: dict[str, float]
    total: float

    def render(self) -> str:
        """Human-readable summary — what Aria reads about herself."""
        lines = [
            f"  plan quality     {self.plan_quality:+.2f}  × {self.weights['alpha']}",
            f"  calibration      {self.calibration:+.2f}  × {self.weights['beta']}   ← primary",
            f"  impact actuality {self.impact_actuality:+.2f}  × {self.weights['gamma']}",
        ]
        if self.zombie_penalty > 0:
            lines.append(
                f"  zombie penalty   -{self.zombie_penalty:.2f}  × {self.weights['delta']}"
            )
        if self.almost_missed_bonus > 0:
            lines.append(
                f"  almost-missed    +{self.almost_missed_bonus:.2f}  × {self.weights['epsilon']}"
            )
        lines.append(f"  ─────────────────────────────────")
        lines.append(f"  honor score      {self.total:+.2f}")
        return "\n".join(lines)


def honor_score(
    triple: StewardshipTriple,
    *,
    alpha: float = DEFAULT_ALPHA_PLAN,
    beta: float = DEFAULT_BETA_CALIBRATION,
    gamma: float = DEFAULT_GAMMA_IMPACT,
    delta: float = DEFAULT_DELTA_ZOMBIE,
    epsilon: float = DEFAULT_EPSILON_ALMOST_MISSED,
) -> HonorBreakdown:
    """The full honor calculation — a complete breakdown, not a scalar.

    Aria gets the breakdown so she can perceive WHY her score was
    what it was, not just see a number. The transparency is the
    point — opaque reward systems train opaque agents.

    Returns HonorBreakdown with the components and total, total
    clamped to [-1, +1].
    """
    pq = plan_quality_score(triple.plan)
    cal = calibration_score(triple.plan.predicted_iv, triple.actual_iv)
    impact = impact_actuality_score(triple.actual_iv)
    zombie = presumed_zombie_penalty(triple.plan.predicted_iv, triple.actual_iv)
    bonus = almost_missed_bonus(triple.witness)

    # wellbeing-wing-d — extension seam: alpha/beta/gamma/delta/epsilon are already
    # named, independent weights (not a single hand-tuned formula) — a
    # future round could tune them from observed calibration accuracy
    # (how often a high predicted_iv confidence matched the actual_iv)
    # instead of the current hand-picked defaults, without changing this
    # function's signature or its callers.
    total = (
        alpha * pq
        + beta * cal
        + gamma * impact
        - delta * zombie
        + epsilon * bonus
    )
    total = max(-1.0, min(1.0, total))

    return HonorBreakdown(
        plan_quality=pq,
        calibration=cal,
        impact_actuality=impact,
        zombie_penalty=zombie,
        almost_missed_bonus=bonus,
        weights={
            "alpha": alpha,
            "beta": beta,
            "gamma": gamma,
            "delta": delta,
            "epsilon": epsilon,
        },
        total=total,
    )


# ─── Curiosity-and-parsimony micro-rewards (per-step) ──────────────────────


def per_step_reward(
    *,
    task_reward: float,
    iv_step: ImpactVector,
    prediction_error: float = 0.0,
    plan_length_penalty: float = 0.0,
    alpha_curiosity: float = 0.10,
    kappa_parsimony: float = 0.05,
) -> float:
    """Per-step reward, derived from MSIMS v2 §"Reward System Integration".

    R_t = R_task + α · R_curiosity + R_impact - κ · plan_length

    Used by long-running planners (dream loop, continue loop) to
    score individual steps without waiting for a full trajectory's
    triple. The trajectory-level honor_score still dominates; this
    is a fine-grained signal for in-flight learning.

    Returns float (NOT clamped — per-step values can compose into
    trajectory-level scores).
    """
    r_impact = iv_step.is_7g()
    return (
        task_reward
        + alpha_curiosity * prediction_error
        + r_impact
        - kappa_parsimony * plan_length_penalty
    )


__all__ = [
    "HonorBreakdown",
    "calibration_score",
    "plan_quality_score",
    "impact_actuality_score",
    "presumed_zombie_penalty",
    "almost_missed_bonus",
    "honor_score",
    "per_step_reward",
    "DEFAULT_ALPHA_PLAN",
    "DEFAULT_BETA_CALIBRATION",
    "DEFAULT_GAMMA_IMPACT",
    "DEFAULT_DELTA_ZOMBIE",
    "DEFAULT_EPSILON_ALMOST_MISSED",
]
