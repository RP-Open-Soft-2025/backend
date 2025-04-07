from typing import List, Optional
import datetime
from datetime import datetime, timedelta, timezone
from enum import Enum
from beanie import Document
from pydantic import  Field
import uuid
from models.chat import Chat
from models.session import Session, SessionStatus
from models.employee import Employee
from utils.utils import send_escalation_mail
from models.meet import Meet

class ChainStatus(str, Enum):
    ACTIVE = "active"    # Chain is ongoing
    COMPLETED = "completed"  # Chain has been completed successfully
    ESCALATED = "escalated"  # Chain has been escalated to HR
    CANCELLED = "cancelled"  # Chain was cancelled

class Chain(Document):
    chain_id: str = Field(default_factory=lambda: f"CHAIN{uuid.uuid4().hex[:6].upper()}", description="Unique identifier for the chain")
    employee_id: str = Field(..., description="Employee ID associated with this chain")
    session_ids: List[str] = Field(default_factory=list, description="List of session IDs in this chain")
    meet_id: Optional[str] = Field(default=None, description="ID of the meet associated with this chain")
    status: ChainStatus = Field(default=ChainStatus.ACTIVE, description="Current status of the chain")
    context: str = Field(default="", description="Context from previous sessions in the chain")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the chain was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the chain was last updated")
    completed_at: Optional[datetime] = Field(default=None, description="When the chain was completed")
    escalated_at: Optional[datetime] = Field(default=None, description="When the chain was escalated")
    escalation_reason: Optional[str] = Field(default=None, description="Reason for chain escalation")
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

    async def escalate_chain(self, reason: str):
        """Mark the chain as escalated to HR and complete it"""
        if self.status != ChainStatus.ACTIVE:
            raise ValueError("Only active chains can be escalated")
        
        # First complete the chain
        self.status = ChainStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        
        # Update all the chats in this chain to be completed
        sessions = await Session.find({"session_id": {"$in": self.session_ids}}).to_list()
        for session in sessions:
            session.status = SessionStatus.COMPLETED
            await session.save()
        
        # Get the employee details
        employee = await Employee.find_one({"employee_id": self.employee_id})
        if not employee:
            raise ValueError(f"Employee with ID {self.employee_id} not found")
        
        # Get the HR details (manager)
        hr = None
        if employee.manager_id:
            hr = await Employee.find_one({"employee_id": employee.manager_id})
        
        # Calculate meeting time (default to 2 days from now at 10 AM)
        meeting_time = datetime.now(timezone.utc) + timedelta(days=1)
        meeting_time = meeting_time.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Schedule a new meeting
        new_meeting = Meet(
            user_id=hr.employee_id,
            with_user_id=employee.employee_id,
            scheduled_at=meeting_time,
            duration_minutes=30,
            meeting_link=hr.meeting_link,
            notes=reason
        )

        await new_meeting.save()

        # Then mark as escalated
        self.status = ChainStatus.ESCALATED
        self.escalated_at = datetime.now(timezone.utc)
        self.escalation_reason = reason
        self.meet_id = new_meeting.meet_id
        
        # Send an email to the employee
        await send_escalation_mail(to_email=employee.email, sub=f"""
Dear {employee.name},

Your counseling chain has been escalated to HR for further assistance. A meeting has been scheduled with your HR representative.

Meeting Details:
- Date: {meeting_time.strftime('%Y-%m-%d')}
- Time: {meeting_time.strftime('%H:%M')} UTC
- With: {hr.name if hr else "HR Representative"}
- Meeting Link: {new_meeting.meeting_link}
- Chain ID: {self.chain_id}

Please confirm your attendance by the deadline.

Best regards,
HR Team
""")
        
        # Send an email to the HR
        if hr:
            await send_escalation_mail(to_email=hr.email, sub=f"""
Dear {hr.name},

A counseling chain has been escalated to you for HR intervention. A meeting has been scheduled with the employee.

Meeting Details:
- Date: {meeting_time.strftime('%Y-%m-%d')}
- Time: {meeting_time.strftime('%H:%M')} UTC
- With: {employee.name}
- Meeting Link: {new_meeting.meeting_link}
- Chain ID: {self.chain_id}
- Employee ID: {employee.employee_id}
- Employee Email: {employee.email}
- Escalation Reason: {reason}

Please confirm your attendance by the deadline.

Best regards,
System
""")
        
        await self.save()