# Failure injection: `compare_mismatch`

Write pattern A to an LBA, then NVMe Compare it against pattern B. Expected: Media and Data Integrity / Compare Failure.

*Captured 2026-09-10T19:46:34+00:00 — QEMU NVMe Ctrl (10.2.1)*

## What was injected

- `nvme write /dev/nvme0n1 --start-block 10 --block-count 0 --data-size 4096 --data /tmp/tmp4fupqqg2/a  (rc=0)`
- `nvme compare /dev/nvme0n1 --start-block 10 --block-count 0 --data-size 4096 --data /tmp/tmp4fupqqg2/b`

> the write lands cleanly; only the Compare against the wrong expected data fails, which is how a drive signals a miscompare.

## Completion-queue status

- **0x4285** — SCT 2 (Media and Data Integrity Errors) / SC 0x85 (Compare Failure)
- Flags: DNR=True  More=False
- Root cause: Compare command miscompare — media contents differ from the expected buffer
- Expectation MET (expected SCT 2, SC 0x85)

## Error Information Log (0x01)

- no new entries. QEMU 10.2 does not populate log page 0x01 — see docs/injection-method.md

## Kernel log

- (nothing)

## Health-log threshold findings

None new vs baseline, but `explore.evaluate()` flags on the post-injection snapshot (fault standing from boot):
- **[INFO]** available_spare: available spare and threshold both 0 — device does not report spare

## Snapshot diff

| field | before | after | Δ |
|---|---|---|---|
| `ocp_smart_health_extended.Physical media units written.lo` | 0 | 4096 | +4096 |
| `smart_health.data_units_written` | 0 | 1 | +1 |
| `smart_health.host_write_commands` | 0 | 1 | +1 |
