from typing import List, Optional, Union
import datetime
from enum import Enum
from beanie import Document, Link
from pydantic import BaseModel, Field, field_validator


class LeaveType(str, Enum):
    CASUAL = "Casual Leave"
    UNPAID = "Unpaid Leave"
    ANNUAL = "Annual Leave"
    SICK = "Sick Leave"


class OnboardingFeedback(str, Enum):
    POOR = "Poor"
    AVERAGE = "Average"
    GOOD = "Good"
    EXCELLENT = "Excellent"


class ManagerFeedback(str, Enum):
    NEEDS_IMPROVEMENT = "Needs Improvement"
    MEETS_EXPECTATIONS = "Meets Expectations"
    EXCEEDS_EXPECTATIONS = "Exceeds Expectations"


class AwardType(str, Enum):
    STAR_PERFORMER = "Star Performer"
    BEST_TEAM_PLAYER = "Best Team Player"
    INNOVATION = "Innovation Award"
    LEADERSHIP = "Leadership Excellence"


class EmotionZone(str, Enum):
    LEANING_SAD = "Leaning to Sad Zone"
    NEUTRAL = "Neutral Zone (OK)"
    LEANING_HAPPY = "Leaning to Happy Zone"
    SAD = "Sad Zone"
    HAPPY = "Happy Zone"
    EXCITED = "Excited Zone"
    FRUSTRATED = "Frustrated Zone"


class Role(str, Enum):
    EMPLOYEE = "employee"
    HR = "hr"
    ADMIN = "admin"


class Activity(BaseModel):
    date: datetime.date = Field(..., description="Date of the activity")
    teams_messages_sent: int = Field(..., ge=0, description="Number of Teams messages sent")
    emails_sent: int = Field(..., ge=0, description="Number of emails sent")
    meetings_attended: int = Field(..., ge=0, description="Number of meetings attended")
    work_hours: float = Field(..., ge=0, description="Number of work hours")


class Leave(BaseModel):
    leave_type: LeaveType = Field(..., description="Type of leave taken")
    leave_days: int = Field(..., ge=1, description="Number of leave days")
    leave_start_date: datetime.date = Field(..., description="Start date of the leave")
    leave_end_date: datetime.date = Field(..., description="End date of the leave")


class Onboarding(BaseModel):
    joining_date: datetime.date = Field(..., description="Date of joining")
    onboarding_feedback: OnboardingFeedback = Field(..., description="Feedback on onboarding experience")
    mentor_assigned: bool = Field(..., description="Whether a mentor was assigned")
    initial_training_completed: bool = Field(..., description="Whether initial training was completed")


class Performance(BaseModel):
    review_period: str = Field(..., description="Period of performance review")
    performance_rating: int = Field(..., ge=1, le=4, description="Performance rating from 1 to 4")
    manager_feedback: ManagerFeedback = Field(..., description="Feedback from the manager")
    promotion_consideration: bool = Field(..., description="Whether the employee is considered for promotion")


class Reward(BaseModel):
    award_type: AwardType = Field(..., description="Type of award received")
    award_date: datetime.date = Field(..., description="Date of the award")
    reward_points: int = Field(..., ge=0, description="Points awarded for the reward")


class VibeMeter(BaseModel):
    response_date: datetime.date = Field(..., description="Date of the vibe response")
    vibe_score: int = Field(..., ge=1, le=6, description="Score indicating the employee's vibe, from 1 to 6")
    emotion_zone: EmotionZone = Field(..., description="Emotional zone based on the vibe score")


class CompanyData(BaseModel):
    activity: List[Activity] = Field(default_factory=list, description="Employee activity data")
    leave: List[Leave] = Field(default_factory=list, description="Employee leave data")
    onboarding: List[Onboarding] = Field(default_factory=list, description="Employee onboarding data")
    performance: List[Performance] = Field(default_factory=list, description="Employee performance data")
    rewards: List[Reward] = Field(default_factory=list, description="Employee rewards data")
    vibemeter: List[VibeMeter] = Field(default_factory=list, description="Employee vibemeter data")


class Employee(Document):
    employee_id: str = Field(..., description="Unique identifier for the employee")
    name: str = Field(..., description="Full name of the employee")
    email: str = Field(..., description="Employee email address")
    password: str = Field(..., description="Employee password (hashed)")
    role: Role = Field(..., description="User role in the system")
    manager_id: Optional[str] = Field(default=None, description="ID of the employee's manager")
    is_blocked: bool = Field(default=False, description="Whether the employee is blocked")
    blocked_at: Optional[datetime.datetime] = Field(default=None, description="Timestamp when the employee was blocked")
    blocked_by: Optional[str] = Field(default=None, description="Employee ID of who blocked this employee")
    company_data: CompanyData = Field(default_factory=CompanyData, description="Company related data for the employee")
    account_activated: bool = Field(default=False, description="Whether the employee's account is activated")
    
    @field_validator("employee_id")
    @classmethod
    def validate_employee_id(cls, v):
        if not v.startswith("EMP") or not len(v) == 7 or not v[3:].isdigit():
            raise ValueError("Employee ID must be in the format EMP followed by 4 digits")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "EMP0001",
                "name": "John Doe",
                "email": "EMP0001@gmail.com",
                "password": "password",
                "role": "employee",
                "manager_id": "EMP1001",
                "is_blocked": False,
                "blocked_at": None,
                "blocked_by": None,
                "company_data": {
                    "activity": [
                        {
                            "date": "2023-10-01",
                            "teams_messages_sent": 10,
                            "emails_sent": 5,
                            "meetings_attended": 3,
                            "work_hours": 8.0
                        }
                    ],
                    "leave": [
                        {
                            "leave_type": "Casual Leave",
                            "leave_days": 2,
                            "leave_start_date": "2023-10-10",
                            "leave_end_date": "2023-10-11"
                        }
                    ],
                    "onboarding": [
                        {
                            "joining_date": "2023-01-01",
                            "onboarding_feedback": "Good",
                            "mentor_assigned": True,
                            "initial_training_completed": True
                        }
                    ],
                    "performance": [
                        {
                            "review_period": "Q1 2023",
                            "performance_rating": 3,
                            "manager_feedback": "Meets Expectations",
                            "promotion_consideration": False
                        }
                    ],
                    "rewards": [
                        {
                            "award_type": "Star Performer",
                            "award_date": "2023-05-01",
                            "reward_points": 100
                        }
                    ],
                    "vibemeter": [
                        {
                            "response_date": "2023-09-01",
                            "vibe_score": 5,
                            "emotion_zone": "Happy Zone"
                        }
                    ]
                }
            }
        }

    class Settings:
        name = "employees"
        indexes = [
            [("employee_id", 1)],  # Correct format for an ascending index
        ]

    @classmethod
    async def get_by_id(cls, employee_id: str):
        return await cls.find_one({"employee_id": employee_id})
    
    @classmethod
    async def get_by_email(cls, email: str):
        return await cls.find_one({"email": email})
    
    @classmethod
    async def get_employees_by_manager(cls, manager_id: str):
        return await cls.find({"manager_id": manager_id}).to_list()