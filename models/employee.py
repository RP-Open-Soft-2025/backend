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
    Date: datetime.date = Field(..., description="Date of the activity")
    Teams_Messages_Sent: int = Field(..., ge=0, description="Number of Teams messages sent")
    Emails_Sent: int = Field(..., ge=0, description="Number of emails sent") 
    Meetings_Attended: int = Field(..., ge=0, description="Number of meetings attended")
    Work_Hours: float = Field(..., ge=0, description="Number of work hours")

    @field_validator("Date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            try:
                # Try parsing different date formats
                if "/" in v:
                    # Handle format like "12/12/2023"
                    month, day, year = map(int, v.split("/"))
                    return datetime.date(year, month, day)
                elif "-" in v:
                    # Handle format like "2023-12-12"
                    return datetime.date.fromisoformat(v)
                else:
                    raise ValueError(f"Unsupported date format: {v}")
            except Exception as e:
                raise ValueError(f"Invalid date format: {v}. Error: {str(e)}")
        elif isinstance(v, datetime.date):
            return v
        elif isinstance(v, datetime.datetime):
            return v.date()
        raise ValueError(f"Invalid date type: {type(v)}")


class Leave(BaseModel):
    Leave_Type: LeaveType = Field(..., description="Type of leave taken")
    Leave_Days: int = Field(..., ge=1, description="Number of leave days")
    Leave_Start_Date: datetime.date = Field(..., description="Start date of the leave")
    Leave_End_Date: datetime.date = Field(..., description="End date of the leave")

    @field_validator("Leave_Start_Date", "Leave_End_Date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            try:
                if "/" in v:
                    month, day, year = map(int, v.split("/"))
                    return datetime.date(year, month, day)
                elif "-" in v:
                    return datetime.date.fromisoformat(v)
                else:
                    raise ValueError(f"Unsupported date format: {v}")
            except Exception as e:
                raise ValueError(f"Invalid date format: {v}. Error: {str(e)}")
        elif isinstance(v, datetime.date):
            return v
        elif isinstance(v, datetime.datetime):
            return v.date()
        raise ValueError(f"Invalid date type: {type(v)}")


class Onboarding(BaseModel):
    Joining_Date: datetime.date = Field(..., description="Date of joining")
    Onboarding_Feedback: OnboardingFeedback = Field(..., description="Feedback on onboarding experience")
    Mentor_Assigned: bool = Field(..., description="Whether a mentor was assigned")
    Initial_Training_Completed: bool = Field(..., description="Whether initial training was completed")

    @field_validator("Joining_Date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            try:
                if "/" in v:
                    month, day, year = map(int, v.split("/"))
                    return datetime.date(year, month, day)
                elif "-" in v:
                    return datetime.date.fromisoformat(v)
                else:
                    raise ValueError(f"Unsupported date format: {v}")
            except Exception as e:
                raise ValueError(f"Invalid date format: {v}. Error: {str(e)}")
        elif isinstance(v, datetime.date):
            return v
        elif isinstance(v, datetime.datetime):
            return v.date()
        raise ValueError(f"Invalid date type: {type(v)}")


class Performance(BaseModel):
    Review_Period: str = Field(..., description="Period of performance review")
    Performance_Rating: int = Field(..., ge=1, le=4, description="Performance rating from 1 to 4")
    Manager_Feedback: ManagerFeedback = Field(..., description="Feedback from the manager")
    Promotion_Consideration: bool = Field(..., description="Whether the employee is considered for promotion")


class Reward(BaseModel):
    Award_Type: AwardType = Field(..., description="Type of award received")
    Award_Date: datetime.date = Field(..., description="Date of the award")
    Reward_Points: int = Field(..., ge=0, description="Points awarded for the reward")

    @field_validator("Award_Date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            try:
                if "/" in v:
                    month, day, year = map(int, v.split("/"))
                    return datetime.date(year, month, day)
                elif "-" in v:
                    return datetime.date.fromisoformat(v)
                else:
                    raise ValueError(f"Unsupported date format: {v}")
            except Exception as e:
                raise ValueError(f"Invalid date format: {v}. Error: {str(e)}")
        elif isinstance(v, datetime.date):
            return v
        elif isinstance(v, datetime.datetime):
            return v.date()
        raise ValueError(f"Invalid date type: {type(v)}")


class VibeMeter(BaseModel):
    Response_Date: datetime.date = Field(..., description="Date of the vibe response")
    Vibe_Score: int = Field(..., ge=1, le=6, description="Score indicating the employee's vibe, from 1 to 6")
    Emotion_Zone: EmotionZone = Field(..., description="Emotional zone based on the vibe score")

    @field_validator("Response_Date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            try:
                if "/" in v:
                    month, day, year = map(int, v.split("/"))
                    return datetime.date(year, month, day)
                elif "-" in v:
                    return datetime.date.fromisoformat(v)
                else:
                    raise ValueError(f"Unsupported date format: {v}")
            except Exception as e:
                raise ValueError(f"Invalid date format: {v}. Error: {str(e)}")
        elif isinstance(v, datetime.date):
            return v
        elif isinstance(v, datetime.datetime):
            return v.date()
        raise ValueError(f"Invalid date type: {type(v)}")


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
    blocked_reason: Optional[str] = Field(default=None, description="Reason for blocking the employee")
    company_data: CompanyData = Field(default_factory=CompanyData, description="Company related data for the employee")
    account_activated: bool = Field(default=False, description="Whether the employee's account is activated")
    
    @field_validator("employee_id")
    @classmethod
    def validate_employee_id(cls, v):
        if not v.startswith("EMP") or not len(v) == 7 or not v[3:].isdigit():
            raise ValueError("Employee ID must be in the format EMP followed by 4 digits")
        return v
    
    class Settings:
        name = "employees"
        indexes = [
            "employee_id",
            "email",
            "role",
            "manager_id",
            "is_blocked",
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "EMP0001",
                "name": "John Doe",
                "email": "emp0001@gmail.com",
                "password": "password",
                "role": "employee",
                "manager_id": "EMP1001",
                "is_blocked": False,
                "blocked_at": None,
                "blocked_by": None,
                "company_data": {
                    "activity": [],
                    "leave": [],
                    "onboarding": [],
                    "performance": [],
                    "rewards": [],
                    "vibemeter": []
                }
            }
        }
    
    @classmethod
    async def get_by_id(cls, employee_id: str):
        return await cls.find_one({"employee_id": employee_id})
    
    @classmethod
    async def get_by_email(cls, email: str):
        return await cls.find_one({"email": email})
    
    @classmethod
    async def get_employees_by_manager(cls, manager_id: str):
        return await cls.find({"manager_id": manager_id}).to_list()
    
    @classmethod
    async def find_all(cls):
        return await cls.find({}).to_list()