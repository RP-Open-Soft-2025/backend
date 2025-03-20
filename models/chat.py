from typing import List, Optional
import datetime
from enum import Enum
from beanie import Document
from pydantic import BaseModel, Field


class SenderType(str, Enum):
    BOT = "bot"
    EMPLOYEE = "emp"


class Message(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Timestamp of the message")
    sender_type: SenderType = Field(..., description="Type of the message sender (bot or employee)")
    text: str = Field(..., description="Content of the message")


class Chat(Document):
    user_id: str = Field(..., description="Employee ID of the user associated with this chat")
    messages: List[Message] = Field(default_factory=list, description="List of messages in the chat")
    mood_score: int = Field(default=-1, ge=-1, le=6, description="Mood score assigned at the end of chat (-1 for unassigned, 1-6 for actual score)")
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Timestamp when the chat was created")
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Timestamp when the chat was last updated")

    class Settings:
        name = "chats"
        indexes = [
            [("user_id", 1)],
            [("created_at", 1)],
            [("mood_score", 1)]
        ]

    class Config:
        json_schema_extra = {
            "example": {
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
                "created_at": "2024-03-20T10:30:00Z",
                "updated_at": "2024-03-20T10:35:00Z"
            }
        }

    @classmethod
    async def get_chats_by_user(cls, user_id: str):
        return await cls.find({"user_id": user_id}).to_list()

    @classmethod
    async def get_chats_by_mood_score(cls, mood_score: int):
        return await cls.find({"mood_score": mood_score}).to_list()

    async def add_message(self, sender_type: SenderType, text: str):
        message = Message(sender_type=sender_type, text=text)
        self.messages.append(message)
        self.updated_at = datetime.datetime.utcnow()
        await self.save()

    async def set_mood_score(self, score: int):
        if not -1 <= score <= 6:
            raise ValueError("Mood score must be between -1 and 6")
        self.mood_score = score
        self.updated_at = datetime.datetime.utcnow()
        await self.save() 