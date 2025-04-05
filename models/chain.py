from typing import List, Optional
import datetime
from datetime import datetime, timedelta, timezone
from enum import Enum
from beanie import Document
from pydantic import BaseModel, Field
import uuid
from models.chat import Chat
from models.session import Session
from models.session import SessionStatus

class ChainStatus(str, Enum):
    ACTIVE = "active"    # Chain is ongoing
    COMPLETED = "completed"  # Chain has been completed successfully
    ESCALATED = "escalated"  # Chain has been escalated to HR
    CANCELLED = "cancelled"  # Chain was cancelled

class Chain(Document):
    chain_id: str = Field(default_factory=lambda: f"CHAIN{uuid.uuid4().hex[:6].upper()}", description="Unique identifier for the chain")
    employee_id: str = Field(..., description="Employee ID associated with this chain")
    session_ids: List[str] = Field(default_factory=list, description="List of session IDs in this chain")
    status: ChainStatus = Field(default=ChainStatus.ACTIVE, description="Current status of the chain")
    context: str = Field(default="", description="Context from previous sessions in the chain")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the chain was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the chain was last updated")
    completed_at: Optional[datetime] = Field(default=None, description="When the chain was completed")
    escalated_at: Optional[datetime] = Field(default=None, description="When the chain was escalated")
    cancelled_at: Optional[datetime] = Field(default=None, description="When the chain was cancelled")
    notes: Optional[str] = Field(default=None, description="Any additional notes about the chain")

    class Settings:
        name = "chains"
        indexes = [
            [("chain_id", 1)],
            [("employee_id", 1)],
            [("status", 1)],
            [("created_at", 1)]
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "chain_id": "CHAIN001",
                "employee_id": "EMP0001",
                "session_ids": ["SESS001", "SESS002"],
                "status": "active",
                "context": "Previous session discussed work-life balance issues",
                "created_at": "2024-03-25T14:00:00Z",
                "updated_at": "2024-03-25T14:00:00Z",
                "notes": "Initial counseling chain"
            }
        }

    @classmethod
    async def get_chains_by_employee(cls, employee_id: str):
        return await cls.find({"employee_id": employee_id}).to_list()
    
    @classmethod
    async def get_by_id(cls, chain_id: str):
        return await cls.find_one({"chain_id": chain_id})

    @classmethod
    async def get_chains_by_status(cls, status: ChainStatus):
        return await cls.find({"status": status}).to_list()

    @classmethod
    async def get_active_chains(cls):
        return await cls.find({"status": ChainStatus.ACTIVE}).to_list()

    async def add_session(self, session_id: str):
        """Add a new session to this chain"""
        self.session_ids.append(session_id)
        self.updated_at = datetime.now(timezone.utc)
        await self.save()

    async def update_context(self, new_context: str):
        """Update the chain's context with new information"""
        self.context = new_context
        self.updated_at = datetime.now(timezone.utc)
        await self.save()

    async def complete_chain(self):
        """Mark the chain as completed"""
        if self.status != ChainStatus.ACTIVE:
            raise ValueError("Only active chains can be completed")
        self.status = ChainStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

        # update all the chats in this chain to be completed
        sessions = await Session.find({"session_id": {"$in": self.session_ids}}).to_list()
        for session in sessions:
            await session.complete_session()
        
        await self.save()

    async def escalate_chain(self):
        """Mark the chain as escalated to HR"""
        if self.status != ChainStatus.ACTIVE:
            raise ValueError("Only active chains can be escalated")
        self.status = ChainStatus.ESCALATED
        self.escalated_at = datetime.now(timezone.utc)
        # update all the chats in this chain to be escalated
        sessions = await Session.find({"session_id": {"$in": self.session_ids}}).to_list()
        for session in sessions:
            chat = await Chat.get_by_id(session.chat_id)
            if chat:
                chat.is_escalated = True
                await chat.save()

        self.updated_at = datetime.now(timezone.utc)
        await self.save()

    async def cancel_chain(self):
        """Mark the chain as cancelled"""
        if self.status not in [ChainStatus.ACTIVE, ChainStatus.ESCALATED]:
            raise ValueError("Only active or escalated chains can be cancelled")
        self.status = ChainStatus.CANCELLED
        self.cancelled_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        await self.save() 