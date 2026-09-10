# Failure injection: `invalid_opcode`

Submit an I/O command with a reserved opcode (0xFF) via io-passthru. The controller must reject it with Generic / Invalid Command Opcode.

*Captured 2026-09-10T19:46:34+00:00 — QEMU NVMe Ctrl (10.2.1)*

## What was injected

- `nvme io-passthru /dev/nvme0n1 --opcode 0xff --namespace-id 1`

> 0xFF is reserved in the NVM command set; a firmware regression that mis-dispatches opcodes would surface here.

## Completion-queue status

- **0x4001** — SCT 0 (Generic Command Status) / SC 0x01 (Invalid Command Opcode)
- Flags: DNR=True  More=False
- Root cause: malformed command — reserved/unsupported opcode reached the controller
- Expectation MET (expected SCT 0, SC 0x01)

## Error Information Log (0x01)

- no new entries. QEMU 10.2 does not populate log page 0x01 — see docs/injection-method.md

## Kernel log

- (nothing)

## Health-log threshold findings

None new vs baseline, but `explore.evaluate()` flags on the post-injection snapshot (fault standing from boot):
- **[INFO]** available_spare: available spare and threshold both 0 — device does not report spare

## Snapshot diff

- no log-page fields changed
