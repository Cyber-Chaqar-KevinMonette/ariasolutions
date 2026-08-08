"""universal_scanner — the Universal Scanner Kernel: one composable pre-flight gate
that every risky operation can pass through before domain-specific checks apply.
Composes existing sentinels/scanners; does not replace or duplicate any of them.
Staged; applied via apply_universal_scanner.sh."""
from __future__ import annotations

from sovereign_agent.universal_scanner.kernel import (
    KernelVerdict,
    OperationDescriptor,
    Verdict,
    kernel_check,
    run,
)

__all__ = ["OperationDescriptor", "KernelVerdict", "Verdict", "kernel_check", "run"]
