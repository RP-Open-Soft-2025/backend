from typing import Optional
import datetime
from enum import Enum
from beanie import Document
from pydantic import BaseModel, Field
import uuid

class MeetStatus(str, Enum):
    SCHEDULED = "SCHEDULED"  # Meeting is scheduled
    IN_PROGRESS = "IN_PROGRESS"  # Meeting is currently happening
    COMPLETED = "COMPLETED"  # Meeting has ended
    CANCELLED = "CANCELLED"  # Meeting was cancelled
    NO_SHOW = "NO_SHOW"  # One or more participants didn't show up


class Meet(Document):
    meet_id: str = Field(default_factory=lambda: f"MEET{uuid.uuid4().hex[:6].upper()}", description="Unique identifier for the meeting")
    user_id: str = Field(..., description="Employee ID of the user who scheduled the meeting")
    with_user_id: str = Field(..., description="Employee ID of the person the meeting is with")
    scheduled_at: datetime.datetime = Field(..., description="When the meeting is scheduled for")
    duration_minutes: int = Field(..., ge=1, le=480, description="Duration of the meeting in minutes (1-480)")
    status: MeetStatus = Field(default=MeetStatus.SCHEDULED, description="Current status of the meeting")
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC), description="When the meeting was created")
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC), description="When the meeting was last updated")
    started_at: Optional[datetime.datetime] = Field(default=None, description="When the meeting started")
    ended_at: Optional[datetime.datetime] = Field(default=None, description="When the meeting ended")
    cancelled_at: Optional[datetime.datetime] = Field(default=None, description="When the meeting was cancelled")
    cancelled_by: Optional[str] = Field(default=None, description="Employee ID of who cancelled the meeting")
    meeting_link: Optional[str] = Field(default=None, description="Link to the meeting (if virtual)")
    location: Optional[str] = Field(default=None, description="Physical location of the meeting (if in-person)")
    notes: Optional[str] = Field(default=None, description="Any additional notes about the meeting")

    class Settings:
        name = "meets"
        indexes = [
            [("meet_id", 1)],
            [("user_id", 1)],
            [("with_user_id", 1)],
            [("status", 1)],
            [("scheduled_at", 1)]
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "meet_id": "MEET001",
                "user_id": "EMP0001",
                "with_user_id": "EMP0002",
                "scheduled_at": "2024-03-25T14:00:00Z",
                "duration_minutes": 60,
                "status": "scheduled",
                "created_at": "2024-03-20T10:00:00Z",
                "updated_at": "2024-03-20T10:00:00Z",
                "meeting_link": "https://meet.google.com/abc-defg-hij",
                "location": "Conference Room A",
                "notes": "Quarterly review meeting"
            }
        }

    @classmethod
    async def get_meets_by_user(cls, user_id: str):
        return await cls.find({"user_id": user_id}).to_list()

    @classmethod
    async def get_meets_with_user(cls, with_user_id: str):
        return await cls.find({"with_user_id": with_user_id}).to_list()

    @classmethod
    async def get_meets_by_status(cls, status: MeetStatus):
        return await cls.find({"status": status}).to_list()

    @classmethod
    async def get_upcoming_meets(cls, user_id: str):
        now = datetime.datetime.now(datetime.UTC)
        return await cls.find({
            "user_id": user_id,
            "scheduled_at": {"$gt": now},
            "status": MeetStatus.SCHEDULED
        }).to_list()
    
    async def initiate_meeting(self):
        self.status = MeetStatus.SCHEDULED
        self.created_at = datetime.datetime.now(datetime.UTC)
        self.updated_at = datetime.datetime.now(datetime.UTC)
        await self.save()

    async def start_meeting(self):
        if self.status != MeetStatus.SCHEDULED:
            raise ValueError("Only scheduled meetings can be started")
        self.status = MeetStatus.IN_PROGRESS
        self.started_at = datetime.datetime.now(datetime.UTC)
        self.updated_at = datetime.datetime.now(datetime.UTC)
        await self.save()

    async def complete_meeting(self):
        if self.status != MeetStatus.IN_PROGRESS:
            raise ValueError("Only in-progress meetings can be completed")
        self.status = MeetStatus.COMPLETED
        self.ended_at = datetime.datetime.now(datetime.UTC)
        self.updated_at = datetime.datetime.now(datetime.UTC)
        await self.save()

    async def mark_as_no_show(self):
        if self.status != MeetStatus.SCHEDULED:
            raise ValueError("Only scheduled meetings can be marked as no-show")
        self.status = MeetStatus.NO_SHOW
        self.updated_at = datetime.datetime.now(datetime.UTC)
        await self.save()

    async def cancel_meeting(self, cancelled_by: str):
        if self.status not in [MeetStatus.SCHEDULED, MeetStatus.IN_PROGRESS]:
            raise ValueError("Only scheduled or in-progress meetings can be cancelled")
        self.status = MeetStatus.CANCELLED
        self.cancelled_at = datetime.datetime.now(datetime.UTC)
        self.cancelled_by = cancelled_by
        self.updated_at = datetime.datetime.now(datetime.UTC)
        await self.save() 