# Failure injection: `smart_warning`

Bring the device up with SMART Critical Warning bit 2 set. No command fails; the regression is only visible in the health log and must be caught there.

*Captured 2026-09-10T19:48:28+00:00 — QEMU NVMe Ctrl (10.2.1)*

## What was injected

- `(no failing command — SMART Critical Warning preset at boot)`
- `nvme smart-log /dev/nvme0`

> Detection path is explore.evaluate() flagging critical_warning, not a completion-queue status.

## Completion-queue status

- no completion-queue error (detection is via the health log)

## Error Information Log (0x01)

- no new entries. QEMU 10.2 does not populate log page 0x01 — see docs/injection-method.md

## Kernel log

- (nothing)

## Health-log threshold findings

None new vs baseline, but `explore.evaluate()` flags on the post-injection snapshot (fault standing from boot):
- **[CRITICAL]** critical_warning: NVM subsystem reliability degraded
- **[INFO]** available_spare: available spare and threshold both 0 — device does not report spare

## Snapshot diff

- no log-page fields changed

## See also

- Full data: [`smart_warning.report.json`](smart_warning.report.json)
- Mechanism used and the log-page-0x01 gap: [`docs/injection-method.md`](../docs/injection-method.md)
- All scenarios summarised: [`docs/findings.md`](../docs/findings.md)
- Regenerate with: [`README.md`](../README.md) → `env/run.sh`
