from typing import Optional
from enum import Enum
from datetime import datetime
from beanie import Document
from pydantic import BaseModel, Field

class NotificationStatus(str, Enum):
    READ = "read"
    UNREAD = "unread"

class Notification(Document):
    employee_id: str = Field(..., description="ID of the employee who should receive this notification")
    title: str = Field(..., description="Title of the notification")
    description: str = Field(..., description="Description/content of the notification")
    created_at: datetime = Field(default_factory=lambda: datetime.now(), description="When the notification was created")
    status: NotificationStatus = Field(default=NotificationStatus.UNREAD, description="Read status of the notification")

    class Settings:
        name = "notifications"
        indexes = [
            [("employee_id", 1)],
            [("status", 1)],
            [("created_at", 1)]
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "EMP0001",
                "title": "New Message",
                "description": "You have received a new message from HR",
                "created_at": "2024-03-30T10:00:00Z",
                "status": "unread"
            }
        }

    @classmethod
    async def get_notifications_by_employee(cls, employee_id: str):
        """Get all notifications for a specific employee"""
        return await cls.find({"employee_id": employee_id}).to_list()

    @classmethod
    async def get_unread_notifications(cls, employee_id: str):
        """Get unread notifications for a specific employee"""
        return await cls.find({
            "employee_id": employee_id,
            "status": NotificationStatus.UNREAD
        }).to_list()

    async def mark_as_read(self):
        """Mark notification as read"""
        self.status = NotificationStatus.READ
        await self.save() 