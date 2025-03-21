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

class Leave(BaseModel):
    Leave_Type: LeaveType = Field(..., description="Type of leave taken")
    Leave_Days: int = Field(..., ge=1, description="Number of leave days")
    Leave_Start_Date: datetime.date = Field(..., description="Start date of the leave")
    Leave_End_Date: datetime.date = Field(..., description="End date of the leave")


class Onboarding(BaseModel):
    Joining_Date: datetime.date = Field(..., description="Date of joining")
    Onboarding_Feedback: OnboardingFeedback = Field(..., description="Feedback on onboarding experience")
    Mentor_Assigned: bool = Field(..., description="Whether a mentor was assigned")
    Initial_Training_Completed: bool = Field(..., description="Whether initial training was completed")


class Performance(BaseModel):
    Review_Period: str = Field(..., description="Period of performance review")
    Performance_Rating: int = Field(..., ge=1, le=4, description="Performance rating from 1 to 4")
    Manager_Feedback: ManagerFeedback = Field(..., description="Feedback from the manager")
    Promotion_Consideration: bool = Field(..., description="Whether the employee is considered for promotion")


class Reward(BaseModel):
    Award_Type: AwardType = Field(..., description="Type of award received")
    Award_Date: datetime.date = Field(..., description="Date of the award")
    Reward_Points: int = Field(..., ge=0, description="Points awarded for the reward")


class VibeMeter(BaseModel):
    Response_Date: datetime.date = Field(..., description="Date of the vibe response")
    Vibe_Score: int = Field(..., ge=1, le=6, description="Score indicating the employee's vibe, from 1 to 6")
    Emotion_Zone: EmotionZone = Field(..., description="Emotional zone based on the vibe score")


class CompanyData(BaseModel):
    activity: Optional[List[Optional[Activity]]] = Field(default=None, description="Employee activity data")
    leave: Optional[List[Optional[Leave]]] = Field(default=None, description="Employee leave data")
    onboarding: Optional[List[Optional[Onboarding]]] = Field(default=None, description="Employee onboarding data")
    performance: Optional[List[Optional[Performance]]] = Field(default=None, description="Employee performance data")
    rewards: Optional[List[Optional[Reward]]] = Field(default=None, description="Employee rewards data")
    vibemeter: Optional[List[Optional[VibeMeter]]] = Field(default=None, description="Employee vibemeter data")


class Employee(Document):
    employee_id: str = Field(..., description="Unique identifier for the employee")
    email: str = Field(..., description="Employee email address")
    password: str = Field(..., description="Employee password (hashed)")
    role: Role = Field(..., description="User role in the system")
    manager_id: Optional[str] = Field(default=None, description="ID of the employee's manager")
    company_data: Optional[CompanyData] = Field(default=None, description="Company related data for the employee")
    
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
                "email": "EMP0001@gmail.com",
                "password": "password",
                "role": "employee",
                "manager_id": "EMP1001",
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