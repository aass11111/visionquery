#!/usr/bin/env bash
# End-to-end smoke test against a running backend on :8000 (Colab cell, or inside the container):
#   docker compose exec -T backend bash -s < scripts/e2e.sh
# Builds a 4 s panning clip from ultralytics' bundled bus.jpg (no downloads), then exercises
# upload -> search -> preview -> recolor through the HTTP API and checks the output video.
set -euo pipefail
API=http://localhost:8000/api
WORK=/tmp/e2e && mkdir -p $WORK && cd $WORK
QUERY=${QUERY:-bus}

json() { python -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

ASSETS=$(python -c "import ultralytics,os; print(os.path.join(os.path.dirname(ultralytics.__file__),'assets'))")
ffmpeg -y -loglevel error -loop 1 -i "$ASSETS/bus.jpg" \
  -vf "scale=1600:-2,crop=1280:720:'(iw-1280)*t/4':'(ih-720)*0.55'" \
  -t 4 -r 25 -c:v libx264 -pix_fmt yuv420p clip.mp4
echo "clip: $(du -h clip.mp4 | cut -f1)"

curl -fsS $API/health | json "d['device'], d['gpu_name']"

VID=$(curl -fsS -F "file=@clip.mp4;type=video/mp4" $API/videos | json "d['video_id']")
echo "video_id=$VID"

wait_job() {
  local id=$1 t0=$SECONDS
  while true; do
    local s; s=$(curl -fsS $API/jobs/$id)
    local st; st=$(echo "$s" | json "d['status']")
    if [[ $st == done || $st == error ]]; then
      echo "$s" > job_$id.json
      echo "job $id -> $st in $((SECONDS - t0))s: $(echo "$s" | json "d['error'] or d['message']")"
      [[ $st == done ]] || exit 1
      return
    fi
    sleep 1
  done
}

SJ=$(curl -fsS -H 'Content-Type: application/json' \
  -d "{\"video_id\":\"$VID\",\"query\":\"$QUERY\",\"frame_step\":5,\"conf\":0.15,\"use_clip\":true}" \
  $API/search | json "d['job_id']")
wait_job $SJ
python - "$WORK/job_$SJ.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))["result"]
print(f"search: {len(r['hits'])} hits / {r['frames_scanned']} frames scanned")
for h in r["hits"][:3]:
    d = h["detections"][0]
    print(f"  frame {h['frame_index']:3d} score {d['score']:.2f} det {d['det_score']:.2f} clip {d['clip_score']} box {[round(v) for v in d['box']]}")
assert r["hits"], "no hits"
h = r["hits"][len(r["hits"]) // 2]
json.dump({"frame_index": h["frame_index"], "box": h["detections"][0]["box"]}, open("pick.json", "w"))
PY

PICK=$(cat pick.json)
FI=$(echo "$PICK" | json "d['frame_index']")
BOX=$(echo "$PICK" | json "json.dumps(d['box'])")

curl -fsS -o preview.jpg -w "preview: HTTP %{http_code}, %{size_download} bytes, %{time_total}s\n" \
  -H 'Content-Type: application/json' \
  -d "{\"video_id\":\"$VID\",\"frame_index\":$FI,\"box\":$BOX,\"color\":\"#22c55e\",\"strength\":0.9}" $API/preview

RJ=$(curl -fsS -H 'Content-Type: application/json' \
  -d "{\"video_id\":\"$VID\",\"query\":\"$QUERY\",\"frame_index\":$FI,\"box\":$BOX,\"color\":\"#22c55e\",\"strength\":0.9,\"frame_step\":5}" \
  $API/recolor | json "d['job_id']")
wait_job $RJ
cat job_$RJ.json | json "'recolor:', d['result']"

curl -fsS -o out.mp4 $API/outputs/$RJ.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,nb_frames -of csv=p=0 out.mp4 \
  | sed 's/^/output video: /'
# Save a side-by-side still (original | recolored) of the picked frame for visual inspection.
ffmpeg -y -loglevel error -i clip.mp4 -i out.mp4 -filter_complex \
  "[0:v]select=eq(n\,$FI)[a];[1:v]select=eq(n\,$FI)[b];[a][b]hstack" -frames:v 1 compare.jpg
curl -fsS $API/health | json "'vram used GB:', d['vram_used_gb'], 'loaded:', d['loaded_models']"
echo "E2E OK  (artifacts in $WORK: preview.jpg compare.jpg out.mp4)"
