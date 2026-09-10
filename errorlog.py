#!/usr/bin/env python3
"""
NVMe status-code and Error Information Log decoding — the root-cause layer.

Project 1 (nvme-logpage-explorer) captures the Error Information Log (0x01) into
a snapshot; this module *interprets* it, plus the completion-queue status that a
failed command returns.

Two entry points:

    decode_status(0x4080)                     -> StatusDecode  (from a CQE / nvme-cli)
    interpret_error_log_page(log_page_dict)   -> list[ErrorLogEntry]  (from a 0x01 snapshot)

NVMe status layout differs between the two:

  * Completion Queue Entry DW3[31:17] "Status Field", as nvme-cli prints it
    (phase-tag bit already stripped):   SC = bits 7:0,  SCT = bits 10:8,
                                        CRD = 12:11, More = 13, DNR = 14
  * Error Information Log entry "Status Field" (SPEC Figure, DW at byte 8),
    phase tag still in bit 0:            SC = bits 8:1,  SCT = bits 11:9,
                                        More = 14, DNR = 15

stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# status code tables (NVMe Base Specification 2.x, Status Code sections)
# --------------------------------------------------------------------------- #
SCT_NAMES = {
    0x0: "Generic Command Status",
    0x1: "Command Specific Status",
    0x2: "Media and Data Integrity Errors",
    0x3: "Path Related Status",
    0x7: "Vendor Specific",
}

SC_GENERIC = {
    0x00: "Successful Completion",
    0x01: "Invalid Command Opcode",
    0x02: "Invalid Field in Command",
    0x03: "Command ID Conflict",
    0x04: "Data Transfer Error",
    0x05: "Commands Aborted due to Power Loss Notification",
    0x06: "Internal Error",
    0x07: "Command Abort Requested",
    0x08: "Command Aborted due to SQ Deletion",
    0x09: "Command Aborted due to Failed Fused Command",
    0x0A: "Command Aborted due to Missing Fused Command",
    0x0B: "Invalid Namespace or Format",
    0x0C: "Command Sequence Error",
    0x0D: "Invalid SGL Segment Descriptor",
    0x0E: "Invalid Number of SGL Descriptors",
    0x0F: "Data SGL Length Invalid",
    0x10: "Metadata SGL Length Invalid",
    0x11: "SGL Descriptor Type Invalid",
    0x12: "Invalid Use of Controller Memory Buffer",
    0x13: "PRP Offset Invalid",
    0x14: "Atomic Write Unit Exceeded",
    0x15: "Operation Denied",
    0x16: "SGL Offset Invalid",
    0x18: "Host Identifier Inconsistent Format",
    0x19: "Keep Alive Timer Expired",
    0x1A: "Keep Alive Timeout Invalid",
    0x1B: "Command Aborted due to Preempt and Abort",
    0x1C: "Sanitize Failed",
    0x1D: "Sanitize In Progress",
    0x1E: "SGL Data Block Granularity Invalid",
    0x1F: "Command Not Supported for Queue in CMB",
    0x20: "Namespace is Write Protected",
    0x21: "Command Interrupted",
    0x22: "Transient Transport Error",
    0x80: "LBA Out of Range",
    0x81: "Capacity Exceeded",
    0x82: "Namespace Not Ready",
    0x83: "Reservation Conflict",
    0x84: "Format In Progress",
}

SC_MEDIA = {
    0x80: "Write Fault",
    0x81: "Unrecovered Read Error",
    0x82: "End-to-end Guard Check Error",
    0x83: "End-to-end Application Tag Check Error",
    0x84: "End-to-end Reference Tag Check Error",
    0x85: "Compare Failure",
    0x86: "Access Denied",
    0x87: "Deallocated or Unwritten Logical Block",
}

SC_PATH = {
    0x00: "Internal Path Error",
    0x01: "Asymmetric Access Persistent Loss",
    0x02: "Asymmetric Access Inaccessible",
    0x03: "Asymmetric Access Transition",
    0x60: "Controller Pathing Error",
    0x70: "Host Pathing Error",
    0x71: "Command Aborted by Host",
}

# a few common Command Specific (SCT 1) codes worth naming
SC_CMD_SPECIFIC = {
    0x00: "Completion Queue Invalid",
    0x01: "Invalid Queue Identifier",
    0x02: "Invalid Queue Size",
    0x03: "Abort Command Limit Exceeded",
    0x05: "Asynchronous Event Request Limit Exceeded",
    0x0A: "Invalid Format",
    0x0B: "Firmware Activation Requires Conventional Reset",
    0x0D: "Feature Identifier Not Saveable",
    0x0E: "Feature Not Changeable",
    0x0F: "Feature Not Namespace Specific",
    0x10: "Firmware Activation Requires NVM Subsystem Reset",
    0x14: "Overlapping Range",
    0x15: "Insufficient Capacity",
    0x16: "Namespace Identifier Unavailable",
    0x1A: "Invalid Protection Information",
    0x1B: "Attempted Write to Read Only Range",
}

_SC_TABLE = {0x0: SC_GENERIC, 0x1: SC_CMD_SPECIFIC, 0x2: SC_MEDIA, 0x3: SC_PATH}

# rough operator guidance keyed on (sct, sc)
_ROOT_CAUSE_HINT = {
    (0x0, 0x01): "malformed command — reserved/unsupported opcode reached the controller",
    (0x0, 0x02): "malformed command — a field value is invalid or out of spec",
    (0x0, 0x04): "DMA / data-transfer failure moving the payload",
    (0x0, 0x06): "controller-internal fault — not caused by the command itself",
    (0x0, 0x0B): "namespace does not exist or is not formatted as the command assumes",
    (0x0, 0x0C): "command issued out of the required order (e.g. before namespace attach)",
    (0x0, 0x14): "write larger than the namespace's Atomic Write Unit",
    (0x0, 0x80): "LBA range starts or extends past the namespace size",
    (0x0, 0x81): "requested block count exceeds the namespace capacity",
    (0x0, 0x82): "namespace not attached / still initialising",
    (0x2, 0x80): "media write fault — the device could not commit data to NAND",
    (0x2, 0x81): "unrecoverable read — ECC/XOR could not reconstruct the block",
    (0x2, 0x82): "end-to-end guard (CRC) mismatch — data corrupted in flight or at rest",
    (0x2, 0x83): "end-to-end application-tag mismatch — protection-info metadata wrong",
    (0x2, 0x84): "end-to-end reference-tag mismatch — LBA in the PI metadata is wrong",
    (0x2, 0x85): "Compare command miscompare — media contents differ from the expected buffer",
    (0x2, 0x86): "access denied — the LBA range is locked or protected",
    (0x2, 0x87): "read of a block that was deallocated or never written",
    (0x1, 0x14): "DSM/copy range overlaps another range in the same command",
}


@dataclass
class StatusDecode:
    raw: int
    sc: int
    sct: int
    sct_name: str
    sc_name: str
    dnr: bool
    more: bool
    phase_tag: bool = False
    source: str = "cqe"  # "cqe" or "error-log"

    @property
    def is_success(self) -> bool:
        return self.sct == 0 and self.sc == 0

    @property
    def root_cause_hint(self) -> str:
        return _ROOT_CAUSE_HINT.get(
            (self.sct, self.sc),
            "see the NVMe Base Specification status-code section for this SCT/SC")

    def __str__(self) -> str:
        flags = "".join(c for c, on in (("DNR", self.dnr), ("|M", self.more)) if on)
        return (f"0x{self.raw:04X}  SCT {self.sct:#x} ({self.sct_name}) / "
                f"SC {self.sc:#04x} ({self.sc_name}){'  ' + flags if flags else ''}")

    def as_dict(self) -> dict:
        return {
            "raw": f"0x{self.raw:04X}", "sct": self.sct, "sct_name": self.sct_name,
            "sc": f"0x{self.sc:02X}", "sc_name": self.sc_name,
            "dnr": self.dnr, "more": self.more, "phase_tag": self.phase_tag,
            "root_cause_hint": self.root_cause_hint, "source": self.source,
        }


def _name_for(sct: int, sc: int) -> str:
    return _SC_TABLE.get(sct, {}).get(sc, f"Unknown SC {sc:#04x} for SCT {sct:#x}")


def decode_status(value: int, *, source: str = "cqe") -> StatusDecode:
    """
    Decode a completion-queue status as printed by nvme-cli — the `(0xNNNN)` in
    `NVMe status: <name>(0xNNNN)` — where the phase-tag bit is already stripped.
    """
    sc = value & 0xFF
    sct = (value >> 8) & 0x7
    more = bool(value & (1 << 13))
    dnr = bool(value & (1 << 14))
    return StatusDecode(raw=value, sc=sc, sct=sct, sct_name=SCT_NAMES.get(sct, "Reserved"),
                        sc_name=_name_for(sct, sc), dnr=dnr, more=more, source=source)


def decode_error_log_status(status_field: int) -> StatusDecode:
    """
    Decode the Status Field of an Error Information Log entry (log page 0x01),
    where bit 0 is the phase tag and SC/SCT sit one bit higher than in a CQE.
    """
    phase = bool(status_field & 0x1)
    sc = (status_field >> 1) & 0xFF
    sct = (status_field >> 9) & 0x7
    more = bool(status_field & (1 << 14))
    dnr = bool(status_field & (1 << 15))
    return StatusDecode(raw=status_field, sc=sc, sct=sct,
                        sct_name=SCT_NAMES.get(sct, "Reserved"),
                        sc_name=_name_for(sct, sc), dnr=dnr, more=more,
                        phase_tag=phase, source="error-log")


# --------------------------------------------------------------------------- #
# Error Information Log (0x01) interpretation
# --------------------------------------------------------------------------- #
@dataclass
class ErrorLogEntry:
    error_count: int
    sqid: int
    cmdid: int
    status: StatusDecode
    lba: int
    nsid: int
    parm_error_location: int = 0
    raw: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "error_count": self.error_count, "sqid": self.sqid, "cmdid": self.cmdid,
            "nsid": self.nsid, "lba": self.lba,
            "parm_error_location": self.parm_error_location,
            "status": self.status.as_dict(),
        }

    def summary(self) -> str:
        loc = f" LBA {self.lba}" if self.lba else ""
        return (f"#{self.error_count} sqid={self.sqid} cmdid={self.cmdid} "
                f"nsid={self.nsid}{loc}: {self.status.sc_name} "
                f"(SCT {self.status.sct:#x}/SC {self.status.sc:#04x}) — "
                f"{self.status.root_cause_hint}")


def _entries(log_page: Any) -> list[dict]:
    if isinstance(log_page, dict):
        return log_page.get("errors") or log_page.get("entries") or []
    if isinstance(log_page, list):
        return log_page
    return []


def interpret_error_log_page(log_page: Any) -> list[ErrorLogEntry]:
    """Turn a nvme-cli `error-log` JSON structure into decoded, non-empty entries."""
    out: list[ErrorLogEntry] = []
    for e in _entries(log_page):
        if not e.get("error_count"):
            continue  # unused slot
        sf = e.get("status_field", 0)
        out.append(ErrorLogEntry(
            error_count=e["error_count"],
            sqid=e.get("sqid", 0), cmdid=e.get("cmdid", 0),
            status=decode_error_log_status(sf),
            lba=e.get("lba", 0), nsid=e.get("nsid", 0),
            parm_error_location=e.get("parm_error_location", 0),
            raw=e,
        ))
    return out


def new_error_log_entries(before: Any, after: Any) -> list[ErrorLogEntry]:
    """Entries present in `after`'s error log but not in `before`'s."""
    seen = {(e.error_count, e.cmdid) for e in interpret_error_log_page(before)}
    return [e for e in interpret_error_log_page(after)
            if (e.error_count, e.cmdid) not in seen]
