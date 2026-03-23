from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional

class FeedBase(BaseModel):
    name: str
    url: str
    enabled: bool = True

class FeedCreate(FeedBase):
    pass

class FeedResponse(FeedBase):
    id: int
    last_synced_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ItemBase(BaseModel):
    title: str
    link: str
    summary: Optional[str] = None
    published_at: Optional[datetime] = None

class ItemResponse(ItemBase):
    id: int
    feed_id: int
    title_zh: Optional[str] = None
    summary_zh: Optional[str] = None
    content: Optional[str] = None
    content_zh: Optional[str] = None
    summary_ai: Optional[str] = None
    score_summary: Optional[float] = None
    score_full: Optional[float] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class ItemUpdate(BaseModel):
    status: str

class ShareResponse(BaseModel):
    id: int
    item_id: int
    share_code: str
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class PreferenceResponse(BaseModel):
    id: int
    item_id: int
    feedback: str
    keywords: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
