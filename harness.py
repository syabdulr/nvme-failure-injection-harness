#!/usr/bin/env python3
"""
NVMe failure-injection regression harness.

For each scenario, run the full loop inside the emulated-device VM:

    baseline snapshot  ->  inject fault  ->  post snapshot
        -> diff log pages
        -> decode the NVMe status the failing command returned
        -> diff the Error Information Log (0x01)
        -> run explore's threshold rules on both snapshots
        -> write a root-cause report (JSON + Markdown)

Log-page capture, snapshot diffing and the threshold rules are imported from
Project 1 (`nvme-logpage-explorer`) — not reimplemented. The new logic here is
the injection mechanisms (scenarios/) and the status / error-log interpretation
(errorlog.py).

    harness.py run [scenario ...]     # default: the client-side scenarios
    harness.py list
    harness.py decode 0x4080
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Project 1, as a library. Prefer an installed copy; fall back to a sibling checkout.
try:
    import explore
except ImportError:  # pragma: no cover - dev convenience
    sibling = HERE.parent / "nvme-logpage-explorer"
    if sibling.is_dir():
        sys.path.insert(0, str(sibling))
    import explore

import errorlog
import scenarios

OUT = HERE / "output"


# --------------------------------------------------------------------------- #
def _snapshot() -> dict:
    return explore.snapshot(sections=[
        "identify_namespace", "smart_health", "error_information",
        "ocp_smart_health_extended",
    ])


def _error_log(snap: dict):
    return snap.get("log_pages", {}).get("error_information", {})


def run_scenario(name: str) -> dict:
    sc = scenarios.get(name)
    dev = explore.discover(None, None)
    ns, ctrl = dev.namespace, dev.controller

    before = _snapshot()
    injection = sc.inject(ns, ctrl)
    after = _snapshot()

    changes = explore.compute_diff(before, after)
    new_entries = errorlog.new_error_log_entries(_error_log(before), _error_log(after))
    findings_before = explore.evaluate(before)
    findings_after = explore.evaluate(after)
    new_findings = [f for f in findings_after if f not in findings_before]

    report = {
        "scenario": sc.name,
        "description": sc.description,
        "captured_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device": before["meta"]["device"],
        "injection": injection.as_dict(),
        "expectation": {
            "expected_sct": sc.expected_sct, "expected_sc": sc.expected_sc,
            "met": sc.matches_expectation(injection),
        },
        "completion_status": injection.status.as_dict() if injection.status else None,
        "error_log_0x01": {
            "new_entries": [e.as_dict() for e in new_entries],
            "note": ("QEMU 10.2 does not populate log page 0x01 — see "
                     "docs/injection-method.md" if not new_entries else ""),
        },
        "snapshot_diff": [c.as_dict() for c in changes],
        "threshold_findings": {
            "new": [vars(f) for f in new_findings],
            "after_all": [vars(f) for f in findings_after],
        },
    }
    _write_reports(sc.name, report, injection)
    return report


# --------------------------------------------------------------------------- #
def _write_reports(name: str, report: dict, injection) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.report.json").write_text(json.dumps(report, indent=2) + "\n")

    st = report["completion_status"]
    lines = [
        f"# Failure injection: `{name}`", "",
        report["description"], "",
        f"*Captured {report['captured_utc']} — "
        f"{report['device']['model']} ({report['device']['firmware']})*", "",
        "## What was injected", "",
    ]
    for c in injection.commands:
        lines.append(f"- `{c}`")
    if injection.notes:
        lines += ["", f"> {injection.notes}"]

    lines += ["", "## Completion-queue status", ""]
    if st:
        exp = report["expectation"]
        exp_str = (f"SCT {exp['expected_sct']}, SC 0x{exp['expected_sc']:02X}"
                   if exp["expected_sc"] is not None else "any non-zero status")
        lines += [
            f"- **{st['raw']}** — SCT {st['sct']} ({st['sct_name']}) / "
            f"SC {st['sc']} ({st['sc_name']})",
            f"- Flags: DNR={st['dnr']}  More={st['more']}",
            f"- Root cause: {st['root_cause_hint']}",
            f"- Expectation {'MET' if exp['met'] else 'NOT met'} (expected {exp_str})",
        ]
    else:
        lines.append("- no completion-queue error (detection is via the health log)")

    lines += ["", "## Error Information Log (0x01)", ""]
    ne = report["error_log_0x01"]["new_entries"]
    if ne:
        for e in ne:
            lines.append(f"- {e}")
    else:
        lines.append(f"- no new entries. {report['error_log_0x01']['note']}")

    lines += ["", "## Kernel log", ""]
    if injection.dmesg:
        lines += ["```"] + injection.dmesg + ["```"]
    else:
        lines.append("- (nothing)")

    lines += ["", "## Health-log threshold findings", ""]
    nf = report["threshold_findings"]["new"]
    allf = report["threshold_findings"]["after_all"]
    if nf:
        lines.append("New vs baseline:")
        for f in nf:
            lines.append(f"- **[{f['severity']}]** {f['rule']}: {f['message']}")
    elif allf:
        lines.append("None new vs baseline, but `explore.evaluate()` flags on the "
                     "post-injection snapshot (fault standing from boot):")
        for f in allf:
            lines.append(f"- **[{f['severity']}]** {f['rule']}: {f['message']}")
    else:
        lines.append("- no findings")

    lines += ["", "## Snapshot diff", ""]
    if report["snapshot_diff"]:
        lines.append("| field | before | after | Δ |")
        lines.append("|---|---|---|---|")
        for c in report["snapshot_diff"]:
            d = "" if c["delta"] is None else f"{c['delta']:+}"
            lines.append(f"| `{c['path']}` | {c['before']} | {c['after']} | {d} |")
    else:
        lines.append("- no log-page fields changed")

    lines += [
        "", "## See also", "",
        f"- Full data: [`{name}.report.json`]({name}.report.json)",
        "- Mechanism used and the log-page-0x01 gap: [`docs/injection-method.md`](../docs/injection-method.md)",
        "- All scenarios summarised: [`docs/findings.md`](../docs/findings.md)",
        f"- Curated copy of this run: [`samples/{name}.report.md`](../samples/{name}.report.md)",
    ]

    (OUT / f"{name}.report.md").write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
def cmd_run(args) -> int:
    names = args.scenarios or scenarios.CLIENT_SIDE
    rc = 0
    for name in names:
        print(f"\n=== {name} ===")
        report = run_scenario(name)
        st = report["completion_status"]
        met = report["expectation"]["met"]
        print(f"  status : {st['raw'] + ' ' + st['sc_name'] if st else '(none)'}")
        print(f"  expect : {'met' if met else 'NOT MET'}")
        print(f"  diff   : {len(report['snapshot_diff'])} field(s) changed")
        print(f"  report : output/{name}.report.md")
        if not met:
            rc = 1
    return rc


def cmd_list(args) -> int:
    for name, sc in scenarios.REGISTRY.items():
        tag = "blkdebug" if sc.needs_blkdebug else \
              ("device-prop" if sc.device_props else "client-side")
        print(f"  {name:16} [{tag:11}] {sc.description.splitlines()[0]}")
    return 0


def cmd_config(args) -> int:
    """Emit shell-eval'able launch requirements for a scenario (used by env/run.sh)."""
    sc = scenarios.get(args.scenario)
    print(f"NEEDS_BLKDEBUG={'1' if sc.needs_blkdebug else '0'}")
    print(f"BLKDEBUG_EVENTS_JSON={json.dumps(json.dumps(sc.blkdebug_events))}")
    props = "".join(f",{k}={v}" for k, v in sc.device_props.items())
    print(f"EXTRA_PROPS={json.dumps(props)}")
    return 0


def cmd_decode(args) -> int:
    val = int(args.value, 0)
    d = (errorlog.decode_error_log_status(val) if args.from_error_log
         else errorlog.decode_status(val))
    print(d)
    print(f"  root cause: {d.root_cause_hint}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="harness.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run scenario(s) and write reports")
    r.add_argument("scenarios", nargs="*", help=f"default: {' '.join(scenarios.CLIENT_SIDE)}")
    r.set_defaults(func=cmd_run)

    sub.add_parser("list", help="list scenarios").set_defaults(func=cmd_list)

    c = sub.add_parser("config", help="emit a scenario's launch requirements")
    c.add_argument("scenario")
    c.set_defaults(func=cmd_config)

    d = sub.add_parser("decode", help="decode an NVMe status value")
    d.add_argument("value", help="e.g. 0x4080 (as nvme-cli prints it)")
    d.add_argument("--from-error-log", action="store_true",
                   help="value is an Error Information Log Status Field, not a CQE")
    d.set_defaults(func=cmd_decode)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
