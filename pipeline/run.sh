#!/bin/bash
# Run detection pipeline against all real CCTV clips
# Usage: ./pipeline/run.sh dataset/CCTV\ Footage

CLIPS_DIR=${1:-'dataset/CCTV Footage'}
LAYOUT=${2:-dataset/store_layout.json}
START_UTC=${3:-2026-10-04T14:30:00Z}

echo 'Processing real store footage...'

python3 -m pipeline.detect \
    --video "$CLIPS_DIR/CAM 3.mp4" \
    --camera-id CAM_3 \
    --layout $LAYOUT --start-utc $START_UTC --post-live

python3 -m pipeline.detect \
    --video "$CLIPS_DIR/CAM 1.mp4" \
    --camera-id CAM_1 \
    --layout $LAYOUT --start-utc $START_UTC --post-live

python3 -m pipeline.detect \
    --video "$CLIPS_DIR/CAM 2.mp4" \
    --camera-id CAM_2 \
    --layout $LAYOUT --start-utc $START_UTC --post-live

python3 -m pipeline.detect \
    --video "$CLIPS_DIR/CAM 5.mp4" \
    --camera-id CAM_5 \
    --layout $LAYOUT --start-utc $START_UTC --post-live

echo 'Done. Check data/events_output.jsonl'
