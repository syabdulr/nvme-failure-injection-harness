"""
QEMU-native injection on the SMART path (not the command path).

`env/run.sh` boots the VM with `-device nvme,...,smart_critical_warning=0x04`,
which sets bit 2 (NVM subsystem reliability degraded) in the SMART/Health log's
Critical Warning field. No command fails — detection is entirely via the health
log, exercised by `explore.evaluate()` in the harness.
"""
from __future__ import annotations

from scenarios.base import Scenario, run_nvme

CRIT_WARNING_VALUE = 0x04  # bit 2: NVM subsystem reliability degraded


class SmartWarning(Scenario):
    def __init__(self) -> None:
        super().__init__(
            name="smart_warning",
            description="Bring the device up with SMART Critical Warning bit 2 "
                        "set. No command fails; the regression is only visible "
                        "in the health log and must be caught there.",
            device_props={"smart_critical_warning": hex(CRIT_WARNING_VALUE)},
            expected_sct=None,   # nothing fails
            expected_sc=None,
        )

    def inject(self, ns: str, ctrl: str):
        # nothing to issue — the fault is standing. Record the health-log state.
        cp = run_nvme(["smart-log", ctrl, "-o", "json"])
        return self._result(
            commands=["(no failing command — SMART Critical Warning preset at boot)",
                      f"nvme smart-log {ctrl}"],
            cp=cp,
            notes="Detection path is explore.evaluate() flagging critical_warning, "
                  "not a completion-queue status.",
        )

    def matches_expectation(self, r) -> bool:
        return '"critical_warning"' in (r.stderr or "") and \
               '"critical_warning":0' not in (r.stderr or "").replace(" ", "")
