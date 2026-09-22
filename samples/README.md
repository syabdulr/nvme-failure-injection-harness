# Curated reports

One `<scenario>.report.md` + `.json` per failure scenario, committed so the
findings in [`docs/findings.md`](../docs/findings.md) are readable without
standing up the VM. Regenerate all of them with:

```
./env/run.sh
```

The `.json` files carry the full snapshot diff and decoded status; the `.md`
files are the human-readable root-cause summaries:

- [`oob_write.report.md`](oob_write.report.md)
- [`invalid_opcode.report.md`](invalid_opcode.report.md)
- [`compare_mismatch.report.md`](compare_mismatch.report.md)
- [`media_error.report.md`](media_error.report.md)
- [`smart_warning.report.md`](smart_warning.report.md)

See the [top-level README](../README.md) and
[`docs/injection-method.md`](../docs/injection-method.md) for how each was produced.
