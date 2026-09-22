# Failure injection: `media_error`

Read an LBA whose backing sector is wired to return EIO (via QEMU blkdebug). Expected: Media and Data Integrity / Unrecovered Read Error.

*Captured 2026-09-10T19:47:31+00:00 — QEMU NVMe Ctrl (10.2.1)*

## What was injected

- `nvme read /dev/nvme0n1 --start-block 256 --block-count 0 --data-size 4096 --data /dev/null`

> LBA 256 (sector 2048) is wired to EIO in the blkdebug backend; other LBAs read fine.

## Completion-queue status

- **0x0281** — SCT 2 (Media and Data Integrity Errors) / SC 0x81 (Unrecovered Read Error)
- Flags: DNR=False  More=False
- Root cause: unrecoverable read — ECC/XOR could not reconstruct the block
- Expectation MET (expected SCT 2, SC 0x81)

## Error Information Log (0x01)

- no new entries. QEMU 10.2 does not populate log page 0x01 — see docs/injection-method.md

## Kernel log

```
[   16.426872] nvme0n1: I/O Cmd(0x2) @ LBA 256, 1 blocks, I/O Error (sct 0x2 / sc 0x81)
[   16.434178] nvme0n1: I/O Cmd(0x2) @ LBA 256, 1 blocks, I/O Error (sct 0x2 / sc 0x81)
```

## Health-log threshold findings

None new vs baseline, but `explore.evaluate()` flags on the post-injection snapshot (fault standing from boot):
- **[INFO]** available_spare: available spare and threshold both 0 — device does not report spare

## Snapshot diff

- no log-page fields changed

## See also

- Full data: [`media_error.report.json`](media_error.report.json)
- Mechanism used and the log-page-0x01 gap: [`docs/injection-method.md`](../docs/injection-method.md)
- All scenarios summarised: [`docs/findings.md`](../docs/findings.md)
- Regenerate with: [`README.md`](../README.md) → `env/run.sh`
