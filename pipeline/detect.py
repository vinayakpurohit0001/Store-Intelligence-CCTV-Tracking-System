import cv2, uuid, argparse, time
from datetime import datetime, timezone
from pathlib import Path
from ultralytics import YOLO
import supervision as sv
import numpy as np
from pipeline.tracker import DirectionTracker
from pipeline.zones import load_zones, get_visitor_zone, get_store_id, get_camera_resolution
from pipeline.emit    import make_event, write_jsonl, post_to_api
from pipeline.reid    import ReIDGallery
from pipeline.staff   import is_staff as classify_staff

# ── Config ────────────────────────────────────────────────────────────
MODEL_PATH      = 'yolov8n.pt'
CONFIDENCE_THRESHOLD = 0.35
DWELL_INTERVAL_SEC   = 30       # emit ZONE_DWELL every N seconds
BATCH_SIZE           = 50       # events to buffer before POST
FRAME_SKIP           = 2        # process every Nth frame (15fps -> 7.5 effective)

def process_clip(video_path: str, camera_id: str,
                 layout_path: str, clip_start_utc: datetime,
                 post_live: bool = False, show_video: bool = False,
                 frame_queue=None):
    
    store_id = get_store_id(layout_path)

    model    = YOLO(MODEL_PATH)
    video_source = int(video_path) if video_path.isdigit() else video_path
    cap      = cv2.VideoCapture(video_source)
    fps      = cap.get(cv2.CAP_PROP_FPS) or 15
    w        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h        = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    tracker  = DirectionTracker(threshold_y=0.6, frame_height=h)
    zones    = load_zones(layout_path, camera_id)

    api_url = "http://localhost:8000" if post_live else None
    gallery = ReIDGallery(threshold=0.72, reentry_window_sec=600, api_url=api_url)
    exited_visitors = set()   # visitor_ids that have exited

    # Per-visitor state
    visitor_map   = {}  # tracker_id -> visitor_id
    zone_entry_t  = {}  # visitor_id -> {zone_id: frame_number}
    last_dwell_t  = {}  # visitor_id -> {zone_id: last_dwell_frame}
    session_seq   = {}  # visitor_id -> int

    events_buffer = []
    frame_num     = 0

    def flush(force=False):
        if events_buffer and (force or len(events_buffer) >= BATCH_SIZE):
            write_jsonl(events_buffer)
            if post_live:
                post_to_api(list(events_buffer))
            events_buffer.clear()

    def add_event(visitor_id, event_type, frame_no, conf,
                  zone_id=None, dwell_ms=0, queue_depth=None,
                  is_staff_override=False):
        offset_sec = frame_no / fps
        seq = session_seq.get(visitor_id, 0) + 1
        session_seq[visitor_id] = seq
        e = make_event(
            store_id=store_id, camera_id=camera_id,
            visitor_id=visitor_id, event_type=event_type,
            timestamp_offset_sec=offset_sec,
            clip_start_utc=clip_start_utc,
            zone_id=zone_id, dwell_ms=dwell_ms,
            confidence=conf, queue_depth=queue_depth,
            session_seq=seq, is_staff=is_staff_override
        )
        events_buffer.append(e)
        flush()

    print(f'[detect] Processing {video_path} | {store_id} | {camera_id}')

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        frame_num += 1
        if frame_num % FRAME_SKIP != 0: continue

        # ── Detection ─────────────────────────────────────────────────
        results = model(frame, classes=[0], conf=CONFIDENCE_THRESHOLD, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(results)

        # ── Tracking + direction ──────────────────────────────────────
        tracked, dir_events = tracker.update(detections, (w, h))

        for tid, direction, conf in dir_events:
            tracker_ids = tracked.tracker_id if tracked.tracker_id is not None else np.array([])
            box_idx_matches = np.where(tracker_ids == tid)[0]
            crop = None
            if len(box_idx_matches) > 0:
                bx = tracked.xyxy[box_idx_matches[0]]
                x1,y1,x2,y2 = [int(v) for v in bx]
                crop = frame[max(0,y1):y2, max(0,x1):x2]

            current_sec = frame_num / fps

            if direction == 'ENTRY':
                # Check Re-ID gallery for re-entry
                matched_id, sim = gallery.match(crop, current_sec) if crop is not None else (None, 0.0)

                if matched_id:
                    # Same person returning — REENTRY event, reuse visitor_id
                    visitor_map[tid] = matched_id
                    exited_visitors.discard(matched_id)
                    add_event(matched_id, 'REENTRY', frame_num, conf)
                else:
                    # New visitor
                    visitor_map[tid] = f'VIS_{uuid.uuid4().hex[:6]}'

                vid = visitor_map[tid]
                # Staff classification
                staff_flag = False
                if crop is not None and crop.size > 0:
                    bx = tracked.xyxy[box_idx_matches[0]] if len(box_idx_matches) > 0 else None
                    if bx is not None:
                        staff_flag = classify_staff(frame, bx)

                if not matched_id:
                    # Register new visitor in gallery
                    if crop is not None:
                        gallery.add(vid, crop)
                    add_event(vid, 'ENTRY', frame_num, conf,
                              is_staff_override=staff_flag)

            elif direction == 'EXIT':
                if tid in visitor_map:
                    vid = visitor_map[tid]
                    gallery.mark_exit(vid, frame_num / fps)
                    exited_visitors.add(vid)
                    add_event(vid, 'EXIT', frame_num, conf)

        if show_video or frame_queue is not None:
            annotated_frame = frame.copy()
            tracker_ids_viz = tracked.tracker_id if tracked.tracker_id is not None else []
            for j, tid_viz in enumerate(tracker_ids_viz):
                if tid_viz is None: continue
                box_viz = tracked.xyxy[j]
                x1, y1, x2, y2 = [int(v) for v in box_viz]
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated_frame, f"ID: {tid_viz}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Draw tripwire
            thresh_y = int(h * 0.6)
            cv2.line(annotated_frame, (0, thresh_y), (w, thresh_y), (0, 0, 255), 2)
            
            if frame_queue is not None:
                if frame_queue.full():
                    try: frame_queue.get_nowait()
                    except: pass
                frame_queue.put(annotated_frame)
                
            if show_video:
                cv2.imshow(f"Store Intelligence Tracking - {camera_id}", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        # ── Zone tracking ─────────────────────────────────────────────
        tracker_ids = tracked.tracker_id if tracked.tracker_id is not None else []
        for i, tid in enumerate(tracker_ids):
            if tid is None or tid not in visitor_map: continue
            vid  = visitor_map[tid]
            box  = tracked.xyxy[i]
            cx   = (box[0] + box[2]) / 2
            cy   = (box[1] + box[3]) / 2
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.9
            current_zone = get_visitor_zone(cx, cy, zones)

            prev_zones = zone_entry_t.get(vid, {})

            # ZONE_ENTER
            if current_zone and current_zone not in prev_zones:
                add_event(vid, 'ZONE_ENTER', frame_num, conf, zone_id=current_zone)
                prev_zones[current_zone] = frame_num
                zone_entry_t[vid] = prev_zones

            # ZONE_EXIT
            for z in list(prev_zones):
                if z != current_zone:
                    dwell = int((frame_num - prev_zones[z]) / fps * 1000)
                    add_event(vid, 'ZONE_EXIT', frame_num, conf, zone_id=z, dwell_ms=dwell)
                    del prev_zones[z]

            # ZONE_DWELL — every DWELL_INTERVAL_SEC of continuous presence
            if current_zone:
                last = last_dwell_t.get(vid, {}).get(current_zone, prev_zones.get(current_zone, frame_num))
                if (frame_num - last) / fps >= DWELL_INTERVAL_SEC:
                    dwell = int((frame_num - prev_zones.get(current_zone, frame_num)) / fps * 1000)
                    add_event(vid, 'ZONE_DWELL', frame_num, conf, zone_id=current_zone, dwell_ms=dwell)
                    last_dwell_t.setdefault(vid, {})[current_zone] = frame_num

    cap.release()
    flush(force=True)
    print(f'[detect] Done. {len(events_buffer)} events flushed.')

# ── CLI entry point ───────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--video',    required=True)
    parser.add_argument('--camera-id',required=True)
    parser.add_argument('--layout',   default='dataset/store_layout.json')
    parser.add_argument('--start-utc',default='2026-10-04T14:30:00Z')
    parser.add_argument('--post-live',action='store_true')
    parser.add_argument('--show-video',action='store_true')
    args = parser.parse_args()

    clip_start = datetime.fromisoformat(args.start_utc.replace('Z','+00:00'))
    process_clip(
        video_path     = args.video,
        camera_id      = args.camera_id,
        layout_path    = args.layout,
        clip_start_utc = clip_start,
        post_live      = args.post_live,
        show_video     = args.show_video
    )
