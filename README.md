# NVMe Failure-Injection Regression Harness

Inject a fault into an NVMe device, then use the completion-queue status, the
NVMe log pages, and the kernel log to detect and characterise it — the
"analyse regression failures, perform root-cause analysis" loop, as a repeatable
test.

Builds directly on **[nvme-logpage-explorer](https://github.com/syabdulr/nvme-logpage-explorer)**
(Project 1): the log-page capture, snapshot diffing, and health-log threshold
rules are imported from it, not reimplemented.

```
pip install -e ../nvme-logpage-explorer      # or: pip install -r requirements.txt
./env/run.sh                                  # all scenarios, reports in output/
```

## The loop

For every scenario, inside the emulated-device VM:

```
explore.snapshot()  →  inject fault  →  explore.snapshot()
   → explore.compute_diff(before, after)        # what moved in the log pages
   → errorlog.decode_status(<CQE status>)       # SCT/SC/DNR → human meaning + root cause
   → errorlog.new_error_log_entries(before,after)# diff of Error Information Log 0x01
   → explore.evaluate(after)                    # health-log threshold rules
   → output/<scenario>.report.{json,md}
```

## Scenarios

| Scenario | Mechanism | Expected status |
|---|---|---|
| `oob_write` | write with start LBA past `nsze` | Generic / LBA Out of Range (`0x0` / `0x80`) |
| `invalid_opcode` | I/O command, reserved opcode `0xFF` | Generic / Invalid Command Opcode (`0x0` / `0x01`) |
| `compare_mismatch` | write pattern A, NVMe Compare against pattern B | Media / Compare Failure (`0x2` / `0x85`) |
| `media_error` | **QEMU blkdebug** — backing sector wired to EIO | Media / Unrecovered Read Error (`0x2` / `0x81`) |
| `smart_warning` | **QEMU `smart_critical_warning`** device prop | no failing command — caught by `explore.evaluate()` in the health log |

`oob_write` / `invalid_opcode` / `compare_mismatch` are client-side and run in one
VM boot; `media_error` and `smart_warning` each need a specially-configured
device and get their own boot. `env/run.sh` handles the grouping.

## What's new here vs Project 1

1. **The injection mechanisms** — `scenarios/`, both client-side (malformed
   commands) and QEMU-native (`blkdebug` I/O errors, `smart_critical_warning`).
2. **`errorlog.py`** — NVMe status decoding (SCT/SC/DNR/More, the generic /
   command-specific / media / path code tables) and Error Information Log (0x01)
   interpretation with per-`(SCT, SC)` root-cause hints. Project 1 *captures*
   0x01; this *reads* it.
3. **`harness.py`** — the baseline → inject → capture → diff → report loop as a
   regression test with pass/fail expectations per scenario (non-zero exit on a
   mismatch, for CI).

## Emulation limits (see `docs/injection-method.md`)

QEMU 10.2's NVMe model **does not populate the Error Information Log (0x01)** or
the SMART `media_errors` / `num_err_log_entries` counters, even for genuine I/O
failures. Verified three ways in `docs/findings.md`. The harness therefore keys
detection on the **completion-queue status** (always present and spec-accurate)
and the kernel log, while `errorlog.py` keeps a full, unit-tested 0x01 decoder
for real hardware.

## Layout

```
harness.py            the loop + reporting
errorlog.py           NVMe status / Error Information Log decoding  (the new logic)
scenarios/            one file per fault; scenarios/__init__.py is the registry
env/                  emulated-device launch (from Project 1) + run.sh orchestrator
docs/injection-method.md   which mechanism, and why the 0x01 gap
docs/findings.md      recorded per-scenario results
tests/test_errorlog.py     status-decode + interpretation tests (no device)
```

`make test` runs the unit tests. MIT licensed.
