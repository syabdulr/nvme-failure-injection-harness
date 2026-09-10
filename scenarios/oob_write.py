"""Client-side injection: write starting past the end of the namespace."""
from __future__ import annotations

from scenarios.base import Scenario, run_nvme


class OobWrite(Scenario):
    def __init__(self) -> None:
        super().__init__(
            name="oob_write",
            description="Issue a write whose starting LBA is past the namespace "
                        "size. A conforming controller rejects it with "
                        "Generic / LBA Out of Range.",
            expected_sct=0x0,
            expected_sc=0x80,
        )

    def inject(self, ns: str, ctrl: str):
        # namespace has `nsze` blocks (0 .. nsze-1); aim well past it.
        start = 1 << 40
        args = ["write", ns, "--start-block", str(start), "--block-count", "0",
                "--data-size", "4096", "--data", "/dev/zero"]
        cp = run_nvme(args)
        return self._result(
            commands=[f"nvme {' '.join(args)}"],
            cp=cp,
            notes=f"start LBA {start} is far beyond nsze; the transfer never "
                  f"reaches the backing store.",
        )
