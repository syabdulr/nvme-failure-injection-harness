# Failure injection: `oob_write`

Issue a write whose starting LBA is past the namespace size. A conforming controller rejects it with Generic / LBA Out of Range.

*Captured 2026-09-10T19:46:33+00:00 — QEMU NVMe Ctrl (10.2.1)*

## What was injected

- `nvme write /dev/nvme0n1 --start-block 1099511627776 --block-count 0 --data-size 4096 --data /dev/zero`

> start LBA 1099511627776 is far beyond nsze; the transfer never reaches the backing store.

## Completion-queue status

- **0x4080** — SCT 0 (Generic Command Status) / SC 0x80 (LBA Out of Range)
- Flags: DNR=True  More=False
- Root cause: LBA range starts or extends past the namespace size
- Expectation MET (expected SCT 0, SC 0x80)

## Error Information Log (0x01)

- no new entries. QEMU 10.2 does not populate log page 0x01 — see docs/injection-method.md

## Kernel log

- (nothing)

## Health-log threshold findings

None new vs baseline, but `explore.evaluate()` flags on the post-injection snapshot (fault standing from boot):
- **[INFO]** available_spare: available spare and threshold both 0 — device does not report spare

## Snapshot diff

- no log-page fields changed

## See also

- Full data: [`oob_write.report.json`](oob_write.report.json)
- Mechanism used and the log-page-0x01 gap: [`docs/injection-method.md`](../docs/injection-method.md)
- All scenarios summarised: [`docs/findings.md`](../docs/findings.md)
- Regenerate with: [`README.md`](../README.md) → `env/run.sh`
