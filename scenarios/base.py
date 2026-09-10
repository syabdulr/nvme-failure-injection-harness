"""Scenario framework: a fault to inject and the status it should produce."""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field

from errorlog import StatusDecode, decode_status

_STATUS_RE = re.compile(r"\((0x[0-9A-Fa-f]+)\)")


def _nvme() -> str:
    path = shutil.which("nvme")
    if not path:
        raise RuntimeError("nvme-cli not on PATH")
    return path


def run_nvme(args: list[str]) -> subprocess.CompletedProcess:
    """Run `nvme <args>`, capturing everything. Never raises on non-zero exit."""
    return subprocess.run([_nvme(), *args], capture_output=True, text=True)


def status_from_stderr(text: str) -> StatusDecode | None:
    """Pull the `(0xNNNN)` NVMe status nvme-cli prints on a failed command."""
    m = _STATUS_RE.search(text or "")
    if not m:
        return None
    return decode_status(int(m.group(1), 16))


_DMESG_RE = re.compile(
    r"nvme.*\b(I/O Error|I/O Cmd|medium error|media error|controller is down|"
    r"timeout|aborting|reset)\b", re.I)


def dmesg_tail(lines: int = 6) -> list[str]:
    """Recent kernel-log lines that look like an NVMe error (not boot noise)."""
    try:
        out = subprocess.run(["dmesg"], capture_output=True, text=True).stdout
    except Exception:
        return []
    hits = [ln.strip() for ln in out.splitlines() if _DMESG_RE.search(ln)]
    return hits[-lines:]


@dataclass
class InjectionResult:
    scenario: str
    commands: list[str]
    status: StatusDecode | None
    returncode: int
    stderr: str
    dmesg: list[str] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "commands": self.commands,
            "returncode": self.returncode,
            "status": self.status.as_dict() if self.status else None,
            "stderr": self.stderr.strip(),
            "dmesg": self.dmesg,
            "notes": self.notes,
        }


@dataclass
class Scenario:
    name: str
    description: str
    # host-side launch requirements (read by env/run.sh before booting the VM):
    needs_blkdebug: bool = False
    blkdebug_events: list[dict] = field(default_factory=list)
    device_props: dict = field(default_factory=dict)
    # what a correct controller should report:
    expected_sct: int | None = None
    expected_sc: int | None = None

    def inject(self, ns: str, ctrl: str) -> InjectionResult:  # pragma: no cover
        raise NotImplementedError

    # helper for subclasses
    def _result(self, commands, cp, notes="") -> InjectionResult:
        return InjectionResult(
            scenario=self.name,
            commands=commands,
            status=status_from_stderr(cp.stderr + cp.stdout),
            returncode=cp.returncode,
            stderr=(cp.stderr or cp.stdout),
            dmesg=dmesg_tail(),
            notes=notes,
        )

    def matches_expectation(self, r: InjectionResult) -> bool:
        if self.expected_sc is None:
            return r.returncode != 0
        if not r.status:
            return False
        ok = r.status.sc == self.expected_sc
        if self.expected_sct is not None:
            ok = ok and r.status.sct == self.expected_sct
        return ok
