from typing import List, Optional
from datetime import datetime, timezone, timedelta
from enum import Enum
from beanie import Document
from pydantic import BaseModel, Field
import uuid

class SenderType(str, Enum):
    BOT = "bot"
    EMPLOYEE = "emp"
    HR = "hr"

class ChatMode(str, Enum):
    BOT = "bot"
    HR = "hr"
    ADMIN = "admin"

class SentimentType(str, Enum):
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"

class Message(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of the message")
    sender_type: SenderType = Field(..., description="Type of the message sender (bot, employee, or hr)")
    text: str = Field(..., description="Content of the message")

class Chat(Document):
    chat_id: str = Field(default_factory=lambda: f"CHAT{uuid.uuid4().hex[:6].upper()}", description="Unique identifier for the chat")
    user_id: str = Field(..., description="Employee ID of the user associated with this chat")
    messages: List[Message] = Field(default_factory=list, description="List of messages in the chat")
    mood_score: int = Field(default=-1, ge=-1, le=6, description="Mood score assigned at the end of chat (-1 for unassigned, 1-6 for actual score)")
    chat_mode: ChatMode = Field(default=ChatMode.BOT, description="Current mode of the chat (bot or hr)")
    is_escalated: bool = Field(default=False, description="Whether the chat has been escalated to HR")
    escalation_reason: Optional[str] = Field(default=None, description="Reason for chat escalation")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the chat was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the chat was last updated")

    class Settings:
        name = "chats"
        indexes = [
            [("user_id", 1)],
            [("created_at", 1)],
            [("mood_score", 1)],
            [("chat_mode", 1)],
            [("is_escalated", 1)],
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "chat_id": "CHAT001",
                "user_id": "EMP0001",
                "messages": [
                    {
                        "timestamp": "2024-03-20T10:30:00Z",
                        "sender_type": "emp",
                        "text": "Hello, I need help with my project"
                    },
                    {
                        "timestamp": "2024-03-20T10:31:00Z",
                        "sender_type": "bot",
                        "text": "I'm here to help! What kind of project are you working on?"
                    }
                ],
                "mood_score": 5,
                "chat_mode": "bot",
                "is_escalated": False,
                "escalation_reason": None,
                "created_at": "2024-03-20T10:30:00Z",
                "updated_at": "2024-03-20T10:35:00Z"
            }
        }
    
    @classmethod
    async def get_chat_by_id(cls, chat_id: str):
        return await cls.find_one({"chat_id": chat_id})

    @classmethod
    async def get_chats_by_user(cls, user_id: str):
        return await cls.find({"user_id": user_id}).to_list()

    @classmethod
    async def get_chats_by_mood_score(cls, mood_score: int):
        return await cls.find({"mood_score": mood_score}).to_list()

    async def add_message(self, sender_type: SenderType, text: str):
        message = Message(sender_type=sender_type, text=text)
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)
        await self.save()

    async def set_mood_score(self, score: int):
        if not -1 <= score <= 6:
            raise ValueError("Mood score must be between -1 and 6")
        self.mood_score = score
        self.updated_at = datetime.now(timezone.utc)
        await self.save()

    async def update_chat_mode(self, mode: ChatMode):
        self.chat_mode = mode
        self.updated_at = datetime.now(timezone.utc)
        await self.save()

    async def escalate_chat(self, reason: str):
        self.is_escalated = True
        self.escalation_reason = reason
        self.chat_mode = ChatMode.HR
        self.updated_at = datetime.now(timezone.utc)
        await self.save() 