"""
Client-side injection: a Compare command whose expected data does not match
what is on the media.

Writes a known pattern to an LBA, then issues NVMe Compare with a different
pattern. A conforming controller reports Media and Data Integrity Errors /
Compare Failure — the same SCT the drive would use for a genuine miscompare
caused by silent corruption.
"""
from __future__ import annotations

import os
import tempfile

from scenarios.base import Scenario, run_nvme

LBA = 10
_A = b"\xAA" * 4096
_B = b"\x55" * 4096


class CompareMismatch(Scenario):
    def __init__(self) -> None:
        super().__init__(
            name="compare_mismatch",
            description="Write pattern A to an LBA, then NVMe Compare it against "
                        "pattern B. Expected: Media and Data Integrity / "
                        "Compare Failure.",
            expected_sct=0x2,
            expected_sc=0x85,
        )

    def inject(self, ns: str, ctrl: str):
        d = tempfile.mkdtemp()
        pa, pb = os.path.join(d, "a"), os.path.join(d, "b")
        open(pa, "wb").write(_A)
        open(pb, "wb").write(_B)

        w = ["write", ns, "--start-block", str(LBA), "--block-count", "0",
             "--data-size", "4096", "--data", pa]
        c = ["compare", ns, "--start-block", str(LBA), "--block-count", "0",
             "--data-size", "4096", "--data", pb]

        wr = run_nvme(w)
        cp = run_nvme(c)
        return self._result(
            commands=[f"nvme {' '.join(w)}  (rc={wr.returncode})",
                      f"nvme {' '.join(c)}"],
            cp=cp,
            notes="the write lands cleanly; only the Compare against the wrong "
                  "expected data fails, which is how a drive signals a miscompare.",
        )
