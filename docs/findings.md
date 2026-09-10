# Findings

Recorded from `./env/run.sh` against the emulated device (QEMU 10.2.1,
nvme-cli 2.16, NVMe 1.4.0 controller from Project 1's `env/`, booted with
virtme-ng). Per-scenario reports are regenerated into `output/`; curated copies
are in `samples/`.

**All five scenarios meet their expected NVMe status (`env/run.sh` exits 0).**

## Summary

| Scenario | Injected | Completion status | SCT / SC | DNR | 0x01 entry | dmesg |
|---|---|---|---|---|---|---|
| `oob_write` | write, start LBA 2⁴⁰ | `0x4080` LBA Out of Range | 0 / 0x80 | yes | none | — |
| `invalid_opcode` | io-passthru opcode `0xFF` | `0x4001` Invalid Command Opcode | 0 / 0x01 | yes | none | — |
| `compare_mismatch` | write A, Compare B | `0x4285` Compare Failure | **2** / 0x85 | yes | none | — |
| `media_error` | blkdebug EIO on sector 2048 | `0x0281` Unrecovered Read Error | **2** / 0x81 | no | none | **yes** |
| `smart_warning` | `smart_critical_warning=0x04` at boot | *(no command fails)* | — | — | none | — |

## Per scenario

### `oob_write` — Generic / LBA Out of Range

```
nvme write /dev/nvme0n1 --start-block 1099511627776 --block-count 0 --data-size 4096 --data /dev/zero
→ NVMe status: LBA Out of Range (0x4080)
```

`0x4080` → SCT 0, SC 0x80, **DNR set** (do not retry — the command is malformed,
retrying cannot help). The starting LBA is past `nsze`, so the transfer never
reaches the backing store. No log-page fields change.

### `invalid_opcode` — Generic / Invalid Command Opcode

```
nvme io-passthru /dev/nvme0n1 --opcode 0xff --namespace-id 1
→ NVMe status: Invalid Command Opcode (0x4001)
```

`0x4001` → SCT 0, SC 0x01, DNR. `0xFF` is reserved in the NVM command set; this
is the path a firmware regression that mis-dispatches opcodes would take.

### `compare_mismatch` — Media and Data Integrity / Compare Failure

```
nvme write   /dev/nvme0n1 --start-block 10 ... --data <pattern A>   (rc=0)
nvme compare /dev/nvme0n1 --start-block 10 ... --data <pattern B>
→ NVMe status: Compare Failure (0x4285)
```

`0x4285` → **SCT 2 (Media and Data Integrity Errors)**, SC 0x85, DNR. The write
lands cleanly; only the Compare against the wrong expected data fails — the same
status a drive raises for a real miscompare from silent corruption. The
preceding write is visible in the snapshot diff:

| field | before | after | Δ |
|---|---|---|---|
| `ocp_smart_health_extended.Physical media units written.lo` | 0 | 4096 | +4096 |
| `smart_health.data_units_written` | 0 | 1 | +1 |
| `smart_health.host_write_commands` | 0 | 1 | +1 |

### `media_error` — Media / Unrecovered Read Error (QEMU-native)

Booted with the namespace backed by `blkdebug` returning EIO on 512-byte
sector 2048.

```
nvme read /dev/nvme0n1 --start-block 256 --block-count 0 --data-size 4096 --data /dev/null
→ NVMe status: Unrecovered Read Error (0x0281)

dmesg:
  nvme0n1: I/O Cmd(0x2) @ LBA 256, 1 blocks, I/O Error (sct 0x2 / sc 0x81)
```

`0x0281` → SCT 2, SC 0x81, **DNR not set** (a media read error *is* worth a
retry). Reads of every other LBA succeed. The kernel's own decode
(`sct 0x2 / sc 0x81`) matches the harness's — confirming the status reaches the
host driver intact.

### `smart_warning` — health-log detection (QEMU-native)

Booted with `-device nvme,...,smart_critical_warning=0x04`. No command fails.
`explore.evaluate()` on the post-injection snapshot returns:

```
[CRITICAL] critical_warning: NVM subsystem reliability degraded
```

Because the fault is standing from boot it appears in the report's "after_all"
findings, not "new vs baseline". A production regression suite would diff
`explore.evaluate()` against a **golden snapshot from a separate clean boot**
rather than a baseline from the same faulted one; the harness supports both
(`compute_diff` / `evaluate` take any two snapshots).

## The Error Information Log (0x01) gap — confirmed

Across all five scenarios: **zero new entries in log page 0x01**, and
`num_err_log_entries` / `media_errors` stayed at 0 — including `media_error`,
where the kernel itself logged a media error. QEMU 10.2's `nvme` device returns
correct completion-queue status but never persists it to 0x01. Cross-checked
three ways in [`injection-method.md`](injection-method.md).

`errorlog.py`'s 0x01 decoder (`decode_error_log_status`,
`interpret_error_log_page`, `new_error_log_entries`) is exercised by
`tests/test_errorlog.py` against synthetic Status Fields, so it is ready for
hardware that does populate the log. This is the same stance Project 1 took on
static wear counters: the command paths and decode logic are real; the emulator
just doesn't model the mechanism behind one log page.

## Also observed

- `nvme dsm` (Trim) with a start LBA past `nsze` returns **success** on QEMU —
  the DSM path does no range validation. That's why the "malformed trim"
  scenario was dropped in favour of `compare_mismatch`, which QEMU does police.
