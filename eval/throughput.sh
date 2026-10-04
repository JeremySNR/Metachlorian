#!/usr/bin/env bash
# Throughput: process a folder of footage from scratch with the production server
# (metachlorian serve with N workers) and report footage hours per wall-clock hour.
#
# usage: eval/throughput.sh <footage-dir>... [-- workers]
#   METACHLORIAN_MODELS must point at installed models. Uses a temporary library.
set -euo pipefail
WORKERS=3
DIRS=()
while [ $# -gt 0 ]; do
  if [ "$1" = "--" ]; then WORKERS=$2; shift 2; else DIRS+=("$1"); shift; fi
done
LIB=$(mktemp -d)
PORT=${PORT:-8790}
metachlorian --data "$LIB" init >/dev/null
for d in "${DIRS[@]}"; do metachlorian --data "$LIB" add "$d" >/dev/null; done
START=$(date +%s)
metachlorian --data "$LIB" serve --port "$PORT" --workers "$WORKERS" >"$LIB/serve.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
pending() {
  metachlorian --data "$LIB" status | python3 -c "import json,sys;j=json.load(sys.stdin)['jobs'];print(j.get('queued',0)+j.get('running',0)+j.get('retry',0))"
}
sleep 20
until [ "$(pending)" = 0 ]; do sleep 10; done
END=$(date +%s)
metachlorian --data "$LIB" status | python3 -c "
import json, sys
s = json.load(sys.stdin)
wall = ($END - $START) / 3600
print(json.dumps({'files': s['assets'], 'shots': s['shots'], 'footage_hours': round(s['hours'], 4), 'wall_hours': round(wall, 4),
                  'footage_hours_per_hour': round(s['hours'] / wall, 3), 'workers': $WORKERS, 'jobs': s['jobs'],
                  'analyser_seconds': s['throughput'].get('analyser_seconds')}, indent=1))"
kill $PID
rm -rf "$LIB"
