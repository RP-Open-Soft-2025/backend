from typing import Optional
import datetime
from enum import Enum
from beanie import Document
from pydantic import BaseModel, Field
import uuid

class SessionStatus(str, Enum):
    PENDING = "pending"  # Yet to attend
    ACTIVE = "active"    # Currently attending
    COMPLETED = "completed"  # Has attended
    CANCELLED = "cancelled"  # Session was cancelled


class Session(Document):
    session_id: str = Field(default_factory=lambda: f"SESS{uuid.uuid4().hex[:6].upper()}", description="Unique identifier for the session")
    user_id: str = Field(..., description="Employee ID of the user assigned to this session")
    chat_id: str = Field(..., description="ID of the chat associated with this session")
    status: SessionStatus = Field(default=SessionStatus.PENDING, description="Current status of the session")
    scheduled_at: datetime.datetime = Field(..., description="When the session is scheduled for")
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="When the session was created")
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="When the session was last updated")
    completed_at: Optional[datetime.datetime] = Field(default=None, description="When the session was completed")
    cancelled_at: Optional[datetime.datetime] = Field(default=None, description="When the session was cancelled")
    cancelled_by: Optional[str] = Field(default=None, description="Employee ID of who cancelled the session")
    notes: Optional[str] = Field(default=None, description="Any additional notes about the session")

    class Settings:
        name = "sessions"
        indexes = [
            [("session_id", 1)],
            [("user_id", 1)],
            [("chat_id", 1)],
            [("status", 1)],
            [("scheduled_at", 1)]
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "SESS001",
                "user_id": "EMP0001",
                "chat_id": "CHAT001",
                "status": "pending",
                "scheduled_at": "2024-03-25T14:00:00Z",
                "created_at": "2024-03-20T10:00:00Z",
                "updated_at": "2024-03-20T10:00:00Z",
                "notes": "Initial counseling session"
            }
        }

    @classmethod
    async def get_sessions_by_user(cls, user_id: str):
        return await cls.find({"user_id": user_id}).to_list()

    @classmethod
    async def get_sessions_by_status(cls, status: SessionStatus):
        return await cls.find({"status": status}).to_list()

    @classmethod
    async def get_active_sessions(cls):
        return await cls.find({"status": SessionStatus.ACTIVE}).to_list()

    async def start_session(self):
        if self.status != SessionStatus.PENDING:
            raise ValueError("Only pending sessions can be started")
        self.status = SessionStatus.ACTIVE
        self.updated_at = datetime.datetime.utcnow()
        await self.save()

    async def complete_session(self):
        if self.status != SessionStatus.ACTIVE:
            raise ValueError("Only active sessions can be completed")
        self.status = SessionStatus.COMPLETED
        self.completed_at = datetime.datetime.utcnow()
        self.updated_at = datetime.datetime.utcnow()
        await self.save()

    async def cancel_session(self, cancelled_by: str):
        if self.status not in [SessionStatus.PENDING, SessionStatus.ACTIVE]:
            raise ValueError("Only pending or active sessions can be cancelled")
        self.status = SessionStatus.CANCELLED
        self.cancelled_at = datetime.datetime.utcnow()
        self.cancelled_by = cancelled_by
        self.updated_at = datetime.datetime.utcnow()
        await self.save() 