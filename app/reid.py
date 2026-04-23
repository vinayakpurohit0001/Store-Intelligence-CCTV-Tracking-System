import numpy as np
import time
from typing import Dict, Optional, Tuple
from collections import OrderedDict

class GlobalReIDRegistry:
    '''Centralized registry for cross-camera visitor re-identification.'''
    
    def __init__(self, threshold: float = 0.75, exit_window_sec: float = 600):
        self.threshold = threshold
        self.exit_window = exit_window_sec
        # visitor_id -> {embedding: np.array, last_seen: float, is_active: bool}
        self.registry: Dict[str, dict] = {}

    def match_or_create(self, query_emb: np.ndarray) -> str:
        '''Matches query embedding against active/recent visitors. 
        Returns existing visitor_id or a new one.'''
        best_id, best_sim = None, 0.0
        now = time.time()

        for vid, data in self.registry.items():
            # Skip if visitor exited a long time ago
            if not data['is_active'] and (now - data['last_seen'] > self.exit_window):
                continue
                
            sim = float(np.dot(query_emb, data['embedding']))
            if sim > best_sim:
                best_sim, best_id = sim, vid

        if best_sim >= self.threshold:
            self.registry[best_id]['last_seen'] = now
            self.registry[best_id]['is_active'] = True
            return best_id
        
        # Create new visitor
        new_id = f"VIS_{int(time.time() * 1000) % 1000000:06d}"
        self.registry[new_id] = {
            'embedding': query_emb,
            'last_seen': now,
            'is_active': True
        }
        return new_id

    def mark_exit(self, visitor_id: str):
        if visitor_id in self.registry:
            self.registry[visitor_id]['is_active'] = False
            self.registry[visitor_id]['last_seen'] = time.time()

# Singleton instance
registry = GlobalReIDRegistry()
