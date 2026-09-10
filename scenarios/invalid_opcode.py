"""Client-side injection: send an I/O command with a reserved opcode."""
from __future__ import annotations

from scenarios.base import Scenario, run_nvme


class InvalidOpcode(Scenario):
    def __init__(self) -> None:
        super().__init__(
            name="invalid_opcode",
            description="Submit an I/O command with a reserved opcode (0xFF) via "
                        "io-passthru. The controller must reject it with "
                        "Generic / Invalid Command Opcode.",
            expected_sct=0x0,
            expected_sc=0x01,
        )

    def inject(self, ns: str, ctrl: str):
        args = ["io-passthru", ns, "--opcode", "0xff", "--namespace-id", "1"]
        cp = run_nvme(args)
        return self._result(
            commands=[f"nvme {' '.join(args)}"],
            cp=cp,
            notes="0xFF is reserved in the NVM command set; a firmware regression "
                  "that mis-dispatches opcodes would surface here.",
        )
