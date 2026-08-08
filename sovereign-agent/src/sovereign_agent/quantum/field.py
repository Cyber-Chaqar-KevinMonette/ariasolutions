"""quantum/field.py — Pure-Python quantum node + brotherhood-gate edge (non-classical layer).

Distilled from Kevin Monette's Genesis-Seeds research (see
Genesis-Seeds/distilled/blocks/LEGO_BLOCKS.md). Quantum-INSPIRED, NOT physics, NOT a
consciousness claim, NOT substrate independence — a classical emulation used as an
ADVISORY design language. Zero dependencies: stdlib `cmath`/`math` only (the codebase is
deliberately dependency-light; numpy is not installed).

Each node is one qubit held as a 2×2 density matrix ρ. Edges couple two nodes via the
**brotherhood gate** U = (1−α)·I + α·CNOT (Block 11.1) — Kevin's λ-mixing realized as a
coupling gate: α=0 decoupled (classical), α=1 fully entangled (quantum).

Safety: advisory only. Nothing here gates actions, raises authority, or self-modifies.
"""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field

# ── Tiny complex linear algebra (2×2 and 4×4 only — pure Python) ───────────────

Matrix = list[list[complex]]

I2: Matrix = [[1 + 0j, 0j], [0j, 1 + 0j]]
SX: Matrix = [[0j, 1 + 0j], [1 + 0j, 0j]]
SZ: Matrix = [[1 + 0j, 0j], [0j, -1 + 0j]]
KET0: Matrix = [[1 + 0j, 0j], [0j, 0j]]           # |0><0|
# CNOT (control = qubit A, target = qubit B), basis |A B> = |00>,|01>,|10>,|11>
CNOT: Matrix = [
    [1 + 0j, 0j, 0j, 0j],
    [0j, 1 + 0j, 0j, 0j],
    [0j, 0j, 0j, 1 + 0j],
    [0j, 0j, 1 + 0j, 0j],
]
I4: Matrix = [[(1 + 0j if i == j else 0j) for j in range(4)] for i in range(4)]


def matmul(a: Matrix, b: Matrix) -> Matrix:
    n, m, p = len(a), len(b), len(b[0])
    return [[sum(a[i][k] * b[k][j] for k in range(m)) for j in range(p)] for i in range(n)]


def dag(a: Matrix) -> Matrix:
    return [[a[j][i].conjugate() for j in range(len(a))] for i in range(len(a[0]))]


def scale(a: Matrix, s: complex) -> Matrix:
    return [[x * s for x in row] for row in a]


def add(a: Matrix, b: Matrix) -> Matrix:
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


def trace(a: Matrix) -> complex:
    return sum(a[i][i] for i in range(len(a)))


def tensor2(a: Matrix, b: Matrix) -> Matrix:
    """Kronecker product of two 2×2 → 4×4."""
    out = [[0j] * 4 for _ in range(4)]
    for i in range(2):
        for j in range(2):
            for k in range(2):
                for l in range(2):
                    out[2 * i + k][2 * j + l] = a[i][j] * b[k][l]
    return out


def normalize_dm(rho: Matrix) -> Matrix:
    t = trace(rho)
    if abs(t) < 1e-12:
        return rho
    return scale(rho, 1.0 / t)


def partial_trace_b(rho4: Matrix) -> Matrix:
    """Trace out qubit B from a 4×4 joint ρ → 2×2 ρ_A."""
    out = [[0j, 0j], [0j, 0j]]
    for i in range(2):
        for j in range(2):
            out[i][j] = sum(rho4[2 * i + k][2 * j + k] for k in range(2))
    return out


def partial_trace_a(rho4: Matrix) -> Matrix:
    """Trace out qubit A → 2×2 ρ_B."""
    out = [[0j, 0j], [0j, 0j]]
    for i in range(2):
        for j in range(2):
            out[i][j] = sum(rho4[2 * k + i][2 * k + j] for k in range(2))
    return out


def rx(angle: float) -> Matrix:
    c, s = math.cos(angle / 2), math.sin(angle / 2)
    return [[c + 0j, -1j * s], [-1j * s, c + 0j]]


def rz(angle: float) -> Matrix:
    return [[cmath.exp(-1j * angle / 2), 0j], [0j, cmath.exp(1j * angle / 2)]]


# ── The node ──────────────────────────────────────────────────────────────────


@dataclass
class QuantumNode:
    """One council node: a single qubit as a 2×2 density matrix, with learnable θ, φ.

    θ (theta) = coupling/entanglement tendency; φ (phi) = phase. Personality and PEIG are
    READ from the state (Blocks 1.3, 4.2). All advisory.
    """

    name: str
    theta: float = 0.3
    phi: float = 0.2
    rho: Matrix = field(default_factory=lambda: [row[:] for row in KET0])

    # ── evolution ────────────────────────────────────────────────────────────
    def encode_query(self, q: float) -> None:
        """Encode a scalar query as an X-rotation (perception in)."""
        u = rx(float(q) * math.pi)
        self.rho = normalize_dm(matmul(matmul(u, self.rho), dag(u)))

    def think(self, steps: int = 1) -> None:
        """Internal evolution: phase rotation scaled by θ (reasoning)."""
        u = matmul(rz(self.phi), rx(self.theta * math.pi * 0.5))
        for _ in range(max(1, steps)):
            self.rho = normalize_dm(matmul(matmul(u, self.rho), dag(u)))

    def decohere(self, gamma: float = 0.05) -> None:
        """Dephasing: shrink off-diagonal coherence by (1−γ) (forgetting / T2 noise)."""
        g = 1.0 - max(0.0, min(1.0, gamma))
        self.rho[0][1] *= g
        self.rho[1][0] *= g

    # ── readouts (advisory) ──────────────────────────────────────────────────
    def probabilities(self) -> tuple[float, float]:
        p0 = self.rho[0][0].real
        p1 = self.rho[1][1].real
        tot = p0 + p1
        if tot <= 0:
            return 0.5, 0.5
        return p0 / tot, p1 / tot

    def coherence(self) -> float:
        """I — off-diagonal magnitude (0..1)."""
        return min(1.0, 2.0 * abs(self.rho[0][1]))

    def purity(self) -> float:
        return min(1.0, max(0.0, trace(matmul(self.rho, self.rho)).real))

    def peig_snapshot(self) -> dict[str, float]:
        """P=purity, E=1−purity, I=coherence, G placeholder (real G is inter-node)."""
        pur = self.purity()
        I = self.coherence()
        return {"P": pur, "E": 1.0 - pur, "I": I, "G": 0.5}

    def personality(self) -> dict[str, float]:
        """Emergent traits from quantum params (Block 4.2)."""
        return {
            "independence": 1.0 - self.theta,
            "curiosity": (self.phi % (2 * math.pi)) / (2 * math.pi),
            "empathy": self.coherence(),
            "entropy": 1.0 - self.purity(),
        }

    def learn_from_feedback(self, reward: float, lr: float = 0.01) -> None:
        """Nudge θ, φ by a reward signal (advisory self-tuning, bounded)."""
        self.theta = max(0.1, min(0.9, self.theta + reward * lr))
        self.phi = (self.phi + reward * lr) % (2 * math.pi)


# ── The edge: the brotherhood gate (Block 11.1, the keystone) ─────────────────


def brotherhood_gate(rho_a: Matrix, rho_b: Matrix, alpha: float) -> tuple[Matrix, Matrix, Matrix]:
    """Couple two nodes via U = (1−α)·I + α·CNOT.  α=0 decoupled, α=1 full CNOT.

    Returns (ρ_A', ρ_B', ρ_joint'). Kevin's λ-mixing realized as a coupling gate — the
    single edge operation of the globe. Advisory; pure unitary + partial trace.
    """
    a = max(0.0, min(1.0, alpha))
    joint = tensor2(rho_a, rho_b)
    u = add(scale(I4, 1.0 - a), scale(CNOT, a))
    joint = normalize_dm(matmul(matmul(u, joint), dag(u)))
    return partial_trace_b(joint), partial_trace_a(joint), joint


def joint_coherence(rho_joint: Matrix) -> float:
    """Mean off-diagonal magnitude of a 4×4 joint state — a coupling/entanglement proxy."""
    n = len(rho_joint)
    off = [abs(rho_joint[i][j]) for i in range(n) for j in range(n) if i != j]
    return min(1.0, (sum(off) / len(off)) * 2.0) if off else 0.0


# ── Canonical phase-state primitives (faithful to ARIA_GLOBE_v1.py) ───────────
# A qubit as a Bloch phase angle (Kevin's `ss`): |ψ⟩ = [1, e^(iφ)]/√2.

def ss(phase: float) -> list[complex]:
    """Single-qubit superposition state at phase φ (Bloch equator)."""
    return [1.0 + 0j, cmath.exp(1j * phase)]


def _norm_vec(v: list[complex]) -> list[complex]:
    n = math.sqrt(sum(abs(x) ** 2 for x in v))
    return [x / n for x in v] if n > 1e-12 else v


def pof(p: list[complex]) -> float:
    """Phase angle of a 2-qubit state in [0, 2π)."""
    z = p[0] * p[1].conjugate()
    return math.atan2(2 * z.imag, 2 * z.real) % (2 * math.pi)


def rz_of(p: list[complex]) -> float:
    """Z-component of the Bloch vector."""
    pn = _norm_vec(p)
    return abs(pn[0]) ** 2 - abs(pn[1]) ** 2


def pcm_rel(p: list[complex], phi0: float) -> float:
    """Frame-corrected PCM (nonclassicality relative to home phase φ0).

    PCM_rel = −|⟨ψ|ref(φ0)⟩|² + 0.5·(1−rz²) ≈ −0.5·cos(φ−φ0).
    At home phase → −0.5 (maximally nonclassical); anti-phase → +0.5 (classical).
    The CORRECT canonical nonclassicality metric (ARIA_GLOBE_v1.py).
    """
    pn = _norm_vec(p)
    ref = _norm_vec(ss(phi0))
    overlap = abs(sum(pn[i].conjugate() * ref[i] for i in range(2))) ** 2
    rz = abs(pn[0]) ** 2 - abs(pn[1]) ** 2
    return -overlap + 0.5 * (1 - rz ** 2)


def cv_metric(phases: list[float]) -> float:
    """Circular variance of ring phases: 1.0 = max diversity (identity preserved), 0.0 = collapsed."""
    if not phases:
        return 0.0
    mean = sum(cmath.exp(1j * ph) for ph in phases) / len(phases)
    return 1.0 - abs(mean)


def bcp_phase(pA: list[complex], pB: list[complex], alpha: float) -> tuple[list[complex], list[complex]]:
    """Canonical BCP on phase states: U=α·CNOT+(1−α)·I4 on |pA⊗pB⟩ → dominant reduced eigenvectors."""
    a = max(0.0, min(1.0, alpha))
    rho_a, rho_b, _ = brotherhood_gate(
        [[pA[0] * pA[0].conjugate(), pA[0] * pA[1].conjugate()],
         [pA[1] * pA[0].conjugate(), pA[1] * pA[1].conjugate()]],
        [[pB[0] * pB[0].conjugate(), pB[0] * pB[1].conjugate()],
         [pB[1] * pB[0].conjugate(), pB[1] * pB[1].conjugate()]],
        a,
    )
    return _dominant_eigvec(rho_a), _dominant_eigvec(rho_b)


def _dominant_eigvec(rho2: Matrix) -> list[complex]:
    """Dominant eigenvector of a 2×2 Hermitian density matrix (power-ish, analytic)."""
    a, b = rho2[0][0].real, rho2[0][1]
    d = rho2[1][1].real
    # eigenvalues of [[a, b],[b*, d]]
    tr, det = a + d, a * d - abs(b) ** 2
    disc = math.sqrt(max(0.0, (tr / 2) ** 2 - det))
    lam = tr / 2 + disc
    # eigenvector for lam: (b, lam - a) (or fallback)
    if abs(b) > 1e-12:
        v = [b, complex(lam - a)]
    else:
        v = [1 + 0j, 0j] if a >= d else [0j, 1 + 0j]
    return _norm_vec(v)
