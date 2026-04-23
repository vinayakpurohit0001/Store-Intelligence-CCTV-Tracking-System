import numpy as np
import supervision as sv
from collections import defaultdict

class DirectionTracker:
    '''Wraps ByteTrack. Determines ENTRY/EXIT by centroid crossing a threshold line.
    threshold_y: pixel row of the virtual entry/exit line (0=top, frame_h=bottom).
    For a front-door camera, set threshold_y to ~60% of frame height.'''

    def __init__(self, threshold_y: float = 0.6, frame_height: int = 1080):
        self.tracker     = sv.ByteTrack()
        self.threshold_y = int(threshold_y * frame_height)
        self.prev_y      = {}   # tracker_id -> previous centroid y
        self.crossed     = {}   # tracker_id -> 'ENTRY'|'EXIT'|None
        self.active      = set()

    def update(self, detections: sv.Detections, frame_wh: tuple):
        '''Returns (tracked_detections, direction_events).
        direction_events: list of (tracker_id, 'ENTRY'|'EXIT', confidence)'''
        tracked = self.tracker.update_with_detections(detections=detections)
        events  = []

        tracker_ids = tracked.tracker_id if tracked.tracker_id is not None else []
        for i, tid in enumerate(tracker_ids):
            if tid is None: continue
            box  = tracked.xyxy[i]
            cy   = (box[1] + box[3]) / 2   # centroid y
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.9

            if tid in self.prev_y:
                prev = self.prev_y[tid]
                # Crossed line downward = ENTRY (moving into store)
                if prev < self.threshold_y <= cy and tid not in self.crossed:
                    events.append((tid, 'ENTRY', conf))
                    self.crossed[tid] = 'ENTRY'
                    self.active.add(tid)
                # Crossed line upward = EXIT
                elif prev > self.threshold_y >= cy and tid in self.active:
                    events.append((tid, 'EXIT', conf))
                    self.crossed[tid] = 'EXIT'
                    self.active.discard(tid)

            self.prev_y[tid] = cy

        return tracked, events
