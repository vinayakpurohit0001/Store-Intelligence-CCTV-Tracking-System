import multiprocessing as mp
import cv2
import numpy as np
import time
from datetime import datetime
from pipeline.detect import process_clip

CAMERAS = [
    {"File": "CAM 1.mp4", "ID": "CAM_1"},
    {"File": "CAM 2.mp4", "ID": "CAM_2"},
    {"File": "CAM 3.mp4", "ID": "CAM_3"},
    {"File": "CAM 5.mp4", "ID": "CAM_5"}
]

def run_camera(cam, q):
    clip_start = datetime.fromisoformat('2026-10-04T14:30:00+00:00')
    process_clip(
        video_path=f"dataset/CCTV Footage/{cam['File']}",
        camera_id=cam['ID'],
        layout_path="dataset/store_layout.json",
        clip_start_utc=clip_start,
        post_live=True,  # Set to True to post events to dashboard while running grid
        show_video=False,
        frame_queue=q
    )

def main():
    queues = []
    processes = []
    
    for cam in CAMERAS:
        q = mp.Queue(maxsize=2)
        queues.append(q)
        p = mp.Process(target=run_camera, args=(cam, q), daemon=True)
        processes.append(p)
        p.start()
        
    print("[Grid] Started 5 background processing workers.")
    
    frames = [None] * 4
    GRID_WIDTH = 640
    GRID_HEIGHT = 360
    
    blank_frame = np.zeros((GRID_HEIGHT, GRID_WIDTH, 3), dtype=np.uint8)
    cv2.putText(blank_frame, "Store Intelligence", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
    cv2.putText(blank_frame, "Live Overview", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
    cv2.putText(blank_frame, "(Press Q to quit)", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 2)
    
    while True:
        # Update frames from queues
        for i, q in enumerate(queues):
            try:
                # get_nowait to not block if one camera is slower
                frame = q.get_nowait()
                frames[i] = cv2.resize(frame, (GRID_WIDTH, GRID_HEIGHT))
            except mp.queues.Empty:
                pass
            except Exception:
                pass
                
        # Initialize missing frames with black screen
        display_frames = [f if f is not None else np.zeros((GRID_HEIGHT, GRID_WIDTH, 3), dtype=np.uint8) for f in frames]
        
        # Build 2x2 Grid (4 slots)
        row1 = np.hstack([display_frames[0], display_frames[1]])
        row2 = np.hstack([display_frames[2], display_frames[3]])
        
        grid = np.vstack([row1, row2])
        
        cv2.imshow("Store Intelligence - Live Grid", grid)
        
        # 30 fps refresh rate
        if cv2.waitKey(33) & 0xFF == ord('q'):
            print("[Grid] Quitting...")
            break
            
    for p in processes:
        p.terminate()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    mp.freeze_support()
    main()
