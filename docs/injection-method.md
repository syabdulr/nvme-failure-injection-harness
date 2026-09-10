# Injection method — what's used and why

## What QEMU 10.2's `nvme` device offers

`qemu-system-x86_64 -device nvme,help` on the pinned build (10.2.1) — the
injection-relevant properties:

| Property | Effect |
|---|---|
| `smart_critical_warning=<uint8>` | sets the SMART/Health **Critical Warning** byte directly (also settable at runtime via QMP `qom-set`) |
| `ocp=on` | enables the OCP 0xC0 extended health log (used by Project 1) |
| `zoned=on` (+ `zoned.*` on `nvme-ns`) | zone state machine — zone-append/boundary errors |
| `detached=on` (on `nvme-ns`) | namespace present but not attached → "Namespace Not Ready" |
| `account-failed`, `account-invalid` | whether failed/invalid ops are counted in block stats |

There is **no** "media error at LBA X" knob on the `nvme` device itself (unlike
`scsi-hd`'s `werror` / `rerror`). That capability comes from the **block layer**:
backing the namespace with a `blkdebug` node injects I/O errors that the NVMe
device then reports up as media errors.

## Mechanisms this harness uses

### Client-side (no special device config) — `oob_write`, `invalid_opcode`, `malformed_trim`

Issue a command the controller must reject:

- **`oob_write`** — `nvme write --start-block <2^40>` → starting LBA past `nsze`
- **`invalid_opcode`** — `nvme io-passthru --opcode 0xff` → reserved opcode
- **`malformed_trim`** — `nvme dsm --slbs <2^40> --ad` → deallocate range past `nsze`

These are real NVMe error-handling paths (the controller validates the command
and returns a status), just induced from the host rather than by breaking the
device internally. They need no device reconfiguration, so all three run in one
VM boot.

### QEMU-native — `media_error` (blkdebug)

`env/run.sh` writes a `blkdebug` config and boots with:

```
-drive file=blkdebug:env/blkdebug-media_error.conf:env/nvme-backing.raw,if=none,id=nvm0,format=raw
```

```ini
[inject-error]
event = "read_aio"
errno = "5"          # EIO
sector = "2048"      # 512-byte sector 2048 == LBA 256 at 4 KiB blocks
once  = "off"
```

A `nvme read` of LBA 256 then fails: the block backend returns EIO, and the NVMe
device reports **Media and Data Integrity Errors / Unrecovered Read Error
(SCT 0x2 / SC 0x81)**. Reads of every other LBA succeed. This is the closest
thing to a NAND defect the emulator can produce.

### QEMU-native — `smart_warning` (`smart_critical_warning`)

Boot with `-device nvme,...,smart_critical_warning=0x04`. Bit 2 (NVM subsystem
reliability degraded) is set in the SMART/Health Critical Warning field from the
first read. No command fails — the regression is only visible in the health log,
and detection is entirely `explore.evaluate()`'s job.

## The Error Information Log (0x01) gap

**QEMU 10.2's `nvme` device does not implement log page 0x01, nor does it
increment the SMART `media_errors` / `num_err_log_entries` counters** — not for
client-side command rejections, and not for genuine blkdebug I/O failures.

Verified three ways (see `docs/findings.md` for the raw output):

1. `oob_write` / `invalid_opcode` — command rejected with a correct CQE status;
   `nvme error-log` afterwards is still all-zero, `num_err_log_entries = 0`.
2. `media_error` — `nvme read` returns SCT 0x2 / SC 0x81 and the kernel logs
   `critical medium error`; `nvme error-log` still all-zero, `media_errors = 0`.
3. dmesg confirms the driver received `sct 0x2 / sc 0x81` — so the status
   reaches the host, it's just never persisted to the log page.

**Consequence for the harness:** detection keys on the **completion-queue
status** (always present, spec-accurate) plus the kernel log and any SMART
deltas. `errorlog.py` still implements a complete 0x01 Status-Field decoder
(`decode_error_log_status`, `interpret_error_log_page`), unit-tested against
synthetic entries, so the tool is correct for physical hardware where 0x01 is
populated. This is the same honesty stance Project 1 took on static wear
counters: the command paths and decode logic are real; the emulator just doesn't
model the physics behind one log page.
