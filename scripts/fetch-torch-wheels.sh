#!/usr/bin/env bash
# Fast, verified download of the PyTorch CUDA wheels for Windows / Python 3.11, for slow or flaky
# connections where one pip download of the 2.5 GB wheel crawls or arrives with a few bad bytes.
#  1. The file is split into PARTS byte ranges fetched in parallel; finished parts survive restarts.
#  2. The joined file is checked against the sha256 the PyTorch index publishes.
#  3. On a mismatch the file is kept and scripts/repair_wheel.py re-downloads only the damaged
#     ZIP members (found by their CRC32) instead of the whole 2.5 GB.
# Run from Git Bash:   bash scripts/fetch-torch-wheels.sh
# scripts/setup-windows.ps1 then installs from the downloaded folder instead of downloading again.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${DEST:-$TEMP/vq-wheels}"
PARTS="${PARTS:-8}"
PY="${PY:-$LOCALAPPDATA/Programs/Python/Python311/python.exe}"
mkdir -p "$DEST"

fetch() {  # package version
  local pkg=$1 ver=$2
  local file="${pkg}-${ver}+cu124-cp311-cp311-win_amd64.whl"
  local enc="${file//+/%2B}"
  # download.pytorch.org serves the original upload, which is what the published sha256 describes.
  local url="https://download.pytorch.org/whl/cu124/${enc}"
  local out="$DEST/$file"

  local sha
  sha=$(curl -fsSL "https://download.pytorch.org/whl/cu124/${pkg}/" | grep -o "${enc}#sha256=[0-9a-f]*" | head -1 | cut -d= -f2)
  [ -n "$sha" ] || { echo "[$pkg] no published hash"; exit 1; }

  if [ ! -f "$out" ]; then
    local size
    size=$(curl -fsSIL "$url" | tr -d '\r' | awk 'tolower($1)=="content-length:"{v=$2} END{print v}')
    [ -n "$size" ] || { echo "[$pkg] could not read file size"; exit 1; }
    echo "[$pkg] $((size / 1048576)) MB in $PARTS parts"
    local chunk=$(( (size + PARTS - 1) / PARTS ))
    for round in 1 2 3; do
      local pids=()
      for i in $(seq 0 $((PARTS - 1))); do
        local start=$(( i * chunk )) end=$(( (i + 1) * chunk - 1 ))
        (( end >= size )) && end=$(( size - 1 ))
        local part="$out.part$i" want=$(( end - start + 1 ))
        if [ -f "$part" ] && [ "$(stat -c %s "$part")" -eq "$want" ]; then continue; fi
        # Resume each part from its current length (survives dropped connections and power cuts).
        ( for try in $(seq 1 30); do
            have=0; [ -f "$part" ] && have=$(stat -c %s "$part")
            (( have > want )) && { rm -f "$part"; have=0; }
            (( have == want )) && exit 0
            curl -fsL --retry 5 --retry-all-errors --speed-limit 1024 --speed-time 60 \
              -r "$(( start + have ))-${end}" "$url" >> "$part"
            [ "$(stat -c %s "$part")" -eq "$want" ] && exit 0
            sleep 3
          done; exit 1 ) &
        pids+=($!)
      done
      local ok=1
      for p in "${pids[@]}"; do wait "$p" || ok=0; done
      (( ok )) && break
      echo "[$pkg] some parts failed, retrying them"
    done
    cat $(for i in $(seq 0 $((PARTS - 1))); do echo "$out.part$i"; done) > "$out"
    rm -f "$out".part*
  fi

  echo "[$pkg] checking sha256"
  if "$PY" "$HERE/repair_wheel.py" "$out" "$url" "$sha"; then
    echo "[$pkg] OK sha256 verified"
  else
    echo "[$pkg] FAILED (file kept at $out)"; exit 1
  fi
}

fetch torch 2.5.1
fetch torchvision 0.20.1
echo WHEELS_DONE
