# schemas common for all three types of users (admin, hr, user)
from pydantic import BaseModel, EmailStr
import datetime
from typing import Optional
from models.employee import CompanyData, Role
from fastapi.security import HTTPBasicCredentials

class EmployeeSignIn(HTTPBasicCredentials):
    class Config:
        json_schema_extra = {
            "example": {
                "username": "EMP0001",
                "password": "password"
            }
        }

class EmployeeData(BaseModel):
    employee_id: str
    email: EmailStr
    role: Role
    manager_id: Optional[str] = None
    company_data: Optional[CompanyData] = None

    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": "EMP0001",
                "email": "employee@example.com",
                "role": "employee",
                "manager_id": "EMP1001",
                "company_data": {
                    "activity": [
                        {
                            "date": "2023-10-01",
                            "teams_messages_sent": 10,
                            "emails_sent": 5,
                            "meetings_attended": 2,
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
                            "joining_date": "2023-09-01",
                            "onboarding_feedback": "Good",
                            "mentor_assigned": True,
                            "initial_training_completed": True
                        }
                    ],
                    "performance": [
                        {
                            "review_period": "Q3 2023",
                            "performance_rating": 3,
                            "manager_feedback": "Meets Expectations",
                            "promotion_consideration": False
                        }
                    ],
                    "rewards": [
                        {
                            "award_type": "Star Performer",
                            "award_date": "2023-09-15",
                            "reward_points": 100
                        }
                    ],
                    "vibemeter": [
                        {
                            "response_date": "2023-10-05",
                            "vibe_score": 5,
                            "emotion_zone": "Happy Zone"
                        }
                    ]
                }
            }
        }
