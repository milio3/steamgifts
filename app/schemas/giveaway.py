from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class GiveawayInfo(BaseModel):
    game_name: str
    giveaway_code: str
    giveaway_url: str
    points_cost: int
    entries_count: int
    copies: int
    time_remaining: str
    category: str
    level_required: Optional[int] = 0
    is_entered: bool

class EntryResult(BaseModel):
    giveaway_code: str
    game_name: str
    result: str # success, error, skipped
    points_remaining: Optional[int] = None
    error_message: Optional[str] = None

class RunSummary(BaseModel):
    run_id: int
    started_at: datetime
    finished_at: Optional[datetime]
    total_entries: int
    total_points_spent: int
    initial_points: int
    final_points: Optional[int]
    status: str
    entries: List[EntryResult]

class AccountInfo(BaseModel):
    points: int
    level: int
    username: str
    xsrf_token: Optional[str] = None

class RunRequest(BaseModel):
    categories: Optional[List[str]] = None
