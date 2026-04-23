from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import numpy as np
from app.reid import registry

router = APIRouter(prefix="/reid")

class MatchRequest(BaseModel):
    embedding: List[float]

class MatchResponse(BaseModel):
    visitor_id: str

class ExitRequest(BaseModel):
    visitor_id: str

@router.post("/match", response_model=MatchResponse)
async def match_visitor(req: MatchRequest):
    emb = np.array(req.embedding, dtype=np.float32)
    # Ensure L2 normalized if not already (registry expects normalized for dot product)
    norm = np.linalg.norm(emb)
    if norm > 0: emb /= norm
    
    visitor_id = registry.match_or_create(emb)
    return MatchResponse(visitor_id=visitor_id)

@router.post("/exit")
async def register_exit(req: ExitRequest):
    registry.mark_exit(req.visitor_id)
    return {"status": "ok"}
