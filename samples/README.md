# Curated reports

One `<scenario>.report.md` + `.json` per failure scenario, committed so the
findings in `docs/` are readable without standing up the VM. Regenerate all of
them with:

```
./env/run.sh
```

The `.json` files carry the full snapshot diff and decoded status; the `.md`
files are the human-readable root-cause summaries.
