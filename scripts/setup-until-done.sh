#!/usr/bin/env bash
# Re-run scripts/setup-windows.ps1 until it succeeds: on a flaky connection pip often gives up on
# one package index page; each run keeps what earlier runs installed, so retries only fetch the rest.
#   bash scripts/setup-until-done.sh
cd "$(dirname "$0")/.."
for try in $(seq 1 30); do
  echo "=== setup attempt $try  [$(date +%T)]" >> setup-attempts.log
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 > setup-windows.log 2>&1
  if grep -q SETUP_DONE setup-windows.log; then
    echo "SETUP_DONE on attempt $try" >> setup-attempts.log
    exit 0
  fi
  grep -aE "^ERROR: (No matching|Could not)" setup-windows.log | head -2 >> setup-attempts.log
  sleep 30
done
echo "GAVE_UP after 30 attempts" >> setup-attempts.log
exit 1
