import numpy as np
import cv2
import torch
import torchvision.transforms as T
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
import requests
from collections import defaultdict

# ── Lightweight feature extractor (MobileNetV3 without classifier head) ──
_weights   = MobileNet_V3_Small_Weights.DEFAULT
_model     = mobilenet_v3_small(weights=_weights)
_model.classifier = torch.nn.Identity()   # strip head, keep 576-d features
_model.eval()

_transform = T.Compose([
    T.ToPILImage(),
    T.Resize((128, 64)),
    T.ToTensor(),
    T.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
])

def _extract(crop_bgr: np.ndarray) -> np.ndarray:
    '''Return 576-d L2-normalised embedding for a BGR image crop.'''
    if crop_bgr is None or crop_bgr.size == 0:
        return np.zeros(576, dtype=np.float32)
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    t   = _transform(rgb).unsqueeze(0)
    with torch.no_grad():
        feat = _model(t).squeeze().numpy()
    norm = np.linalg.norm(feat)
    return feat / norm if norm > 0 else feat

class ReIDGallery:
    '''Stores one embedding per visitor_id.
    match() returns (visitor_id, similarity) of best match above threshold,
    or (None, 0.0) if no match found.'''

    def __init__(self, threshold: float = 0.72, reentry_window_sec: float = 600, api_url: str = None):
        self.threshold        = threshold
        self.reentry_window   = reentry_window_sec
        self.api_url          = api_url
        self._gallery: dict[str, np.ndarray] = {}   # visitor_id -> embedding
        self._exit_time: dict[str, float]    = {}   # visitor_id -> exit timestamp_sec

    def add(self, visitor_id: str, crop_bgr: np.ndarray):
        '''Register or update a visitor's embedding.'''
        self._gallery[visitor_id] = _extract(crop_bgr)

    def mark_exit(self, visitor_id: str, timestamp_sec: float):
        self._exit_time[visitor_id] = timestamp_sec
        if self.api_url:
            try: requests.post(f"{self.api_url}/reid/exit", json={"visitor_id": visitor_id}, timeout=0.5)
            except: pass

    def match(self, crop_bgr: np.ndarray, current_sec: float) -> tuple[str|None, float]:
        '''Find best match among recently-exited visitors OR via global API.'''
        query = _extract(crop_bgr)
        
        # 1. Try local match (fast)
        best_id, best_sim = None, 0.0
        for vid, emb in self._gallery.items():
            exit_t = self._exit_time.get(vid)
            if exit_t is None: continue
            if current_sec - exit_t > self.reentry_window: continue
            sim = float(np.dot(query, emb))
            if sim > best_sim:
                best_sim, best_id = sim, vid

        if best_sim >= self.threshold:
            return best_id, best_sim

        # 2. Try global match (cross-camera)
        if self.api_url:
            try:
                resp = requests.post(
                    f"{self.api_url}/reid/match", 
                    json={"embedding": query.tolist()},
                    timeout=1.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # We treat global matches with high confidence as threshold=1.0 for simplicity
                    return data['visitor_id'], 1.0
            except:
                pass

        return None, 0.0
