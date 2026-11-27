#!/bin/bash
# Rivaluta i lab large generati, una modalità alla volta, con correction V3.
set -euo pipefail
cd "$(dirname "$0")/.."

if (( $# == 0 )); then
  set -- no_skill dns_only both_forced auto
fi

for modalita in "$@"; do
  case "$modalita" in
    no_skill|dns_only|both_forced|auto) ;;
    *) echo "Modalità non valida: $modalita" >&2; exit 2 ;;
  esac
  destinazione="results/general/dns_skill_pilot_v2_large_${modalita}_V3"
  if [[ -e "$destinazione" || -L "$destinazione" ]]; then
    .venv/bin/python -B - "$destinazione" "$modalita" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    manifest = json.loads((p / 'manifest.json').read_text())
    if manifest.get('status') != 'completed' or manifest.get('expected_runs') != 30:
        raise ValueError('valutazione incompleta')
    correction = Path('scenarios/lab_03/tasks/base/large/correction_large_custom_v3.yaml')
    digest = hashlib.sha256(correction.read_bytes()).hexdigest()
    if manifest.get('correction_sha256') != digest or manifest.get('selection', {}).get('skill_mode') != sys.argv[2]:
        raise ValueError('correction o modalità diversa')
    details = list((p / 'dettagli').glob('*/evaluation.json'))
    if len(details) != 30:
        raise ValueError('numero di risultati inatteso')
    failures = sum(json.loads(f.read_text()).get('status') != 'COMPLETED' for f in details)
except (OSError, ValueError, TypeError) as exc:
    raise SystemExit(f'Cartella già presente ma non completa: {p}: {exc}')
print(f'Già elaborata: {p}; errori tecnici: {failures}', flush=True)
PY
    continue
  fi
  echo "Avvio V3 large: $modalita"
  .venv/bin/python -B -u scripts/evaluate_existing_labs.py \
    --correction scenarios/lab_03/tasks/base/large/correction_large_custom_v3.yaml \
    --runs runs/dns_skill_pilot_v2/lab_03/base/large \
    --skill-mode "$modalita" \
    --checker-workers 2 \
    --output "$destinazione"
done
