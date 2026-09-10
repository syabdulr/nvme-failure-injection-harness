"""
QEMU-native injection: a real read failure from the block backend.

`env/run.sh` boots the VM with the namespace backed by a QEMU `blkdebug` node
configured to return EIO on reads of one sector. The read of that LBA then fails
with Media and Data Integrity / Unrecovered Read Error — the closest thing to a
NAND defect this emulator can produce.
"""
from __future__ import annotations

from scenarios.base import Scenario, run_nvme

# 4 KiB logical blocks -> LBA 256 == 512-byte sector 2048
TARGET_LBA = 256
TARGET_SECTOR = TARGET_LBA * 8


class MediaError(Scenario):
    def __init__(self) -> None:
        super().__init__(
            name="media_error",
            description="Read an LBA whose backing sector is wired to return EIO "
                        "(via QEMU blkdebug). Expected: Media and Data Integrity "
                        "/ Unrecovered Read Error.",
            needs_blkdebug=True,
            blkdebug_events=[{"event": "read_aio", "errno": 5,
                             "sector": TARGET_SECTOR, "once": False}],
            expected_sct=0x2,
            expected_sc=0x81,
        )

    def inject(self, ns: str, ctrl: str):
        args = ["read", ns, "--start-block", str(TARGET_LBA), "--block-count", "0",
                "--data-size", "4096", "--data", "/dev/null"]
        cp = run_nvme(args)
        return self._result(
            commands=[f"nvme {' '.join(args)}"],
            cp=cp,
            notes=f"LBA {TARGET_LBA} (sector {TARGET_SECTOR}) is wired to EIO in "
                  f"the blkdebug backend; other LBAs read fine.",
        )
