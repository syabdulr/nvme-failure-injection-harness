#!/usr/bin/env bash
# Run failure-injection scenarios, each in a fresh emulated-device VM configured
# for what that scenario needs (plain / blkdebug backend / extra device props).
#
#   env/run.sh                 # all scenarios
#   env/run.sh oob_write       # just one
#   env/run.sh media_error smart_warning
#
# Reports land in output/<scenario>.report.{json,md}.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require vng
require "$QEMU_BIN"
create_backing
mkdir -p "$REPO_ROOT/output"

PY="${PYTHON:-python3}"
mapfile -t ALL < <("$PY" "$REPO_ROOT/harness.py" list | awk '{print $1}')
SCENARIOS=("${@:-${ALL[@]}}")

# group scenarios that need no special device config into a single VM boot
plain=()
special=()
for s in "${SCENARIOS[@]}"; do
  eval "$("$PY" "$REPO_ROOT/harness.py" config "$s")"
  if [[ "$NEEDS_BLKDEBUG" == "0" && -z "$EXTRA_PROPS" ]]; then
    plain+=("$s")
  else
    special+=("$s")
  fi
done

FAILED=0
run_vm() {  # $@ = scenario names; a scenario mismatch must not abort the rest
  log "booting VM for: $*"
  NVME_BLKDEBUG_CONF="${NVME_BLKDEBUG_CONF:-}" NVME_EXTRA_PROPS="${NVME_EXTRA_PROPS:-}" \
    "$ENV_DIR/up.sh" -- "$PY" harness.py run "$@" || FAILED=1
}

if [[ ${#plain[@]} -gt 0 ]]; then
  ( unset NVME_BLKDEBUG_CONF NVME_EXTRA_PROPS; run_vm "${plain[@]}" ) || FAILED=1
fi

for s in "${special[@]}"; do
  eval "$("$PY" "$REPO_ROOT/harness.py" config "$s")"
  export NVME_EXTRA_PROPS="$EXTRA_PROPS"
  export NVME_BLKDEBUG_CONF=""
  if [[ "$NEEDS_BLKDEBUG" == "1" ]]; then
    conf="$ENV_DIR/blkdebug-$s.conf"
    "$PY" - "$BLKDEBUG_EVENTS_JSON" > "$conf" <<'PY'
import json, sys
for ev in json.loads(sys.argv[1]):
    print("[inject-error]")
    print(f'event = "{ev["event"]}"')
    print(f'errno = "{ev["errno"]}"')
    if "sector" in ev:
        print(f'sector = "{ev["sector"]}"')
    print(f'once = "{"on" if ev.get("once") else "off"}"')
    print('immediately = "off"')
    print()
PY
    export NVME_BLKDEBUG_CONF="$conf"
  fi
  run_vm "$s"
  unset NVME_EXTRA_PROPS NVME_BLKDEBUG_CONF
done

echo
log "reports:"
ls -1 "$REPO_ROOT"/output/*.report.md 2>/dev/null || true
[[ $FAILED -eq 0 ]] || { log "one or more scenarios did not meet expectation"; exit 1; }
