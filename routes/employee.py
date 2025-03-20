# routes only for employee

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel, Field
from models.meet import Meet, MeetStatus
from models.session import Session, SessionStatus
from models.chat import Chat
from models.employee import Employee, EmotionZone
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
import datetime
from collections import defaultdict


router = APIRouter()


async def verify_employee(token: str = Depends(JWTBearer())):
    """Verify that the user is an employee."""
    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials"
        )
    return payload


class MeetResponse(BaseModel):
    meet_id: str
    with_user_id: str
    scheduled_at: datetime.datetime
    duration_minutes: int
    meeting_link: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    chat_id: str
    scheduled_at: datetime.datetime
    notes: Optional[str] = None


class MoodScoreStats(BaseModel):
    average_score: float
    total_sessions: int
    emotion_distribution: dict[str, int]  # Count of each emotion zone
    last_5_scores: List[int]


class ChatSummary(BaseModel):
    total_chats: int
    average_mood_score: float
    last_chat_date: Optional[datetime.datetime]
    total_messages: int


class UserDetails(BaseModel):
    employee_id: str
    name: str
    email: str
    role: str
    manager_id: Optional[str]
    is_blocked: bool
    mood_stats: MoodScoreStats
    chat_summary: ChatSummary
    upcoming_meets: int
    upcoming_sessions: int
    company_data: Optional[dict]


@router.get("/profile", response_model=UserDetails, tags=["Employee"])
async def get_user_profile(
    employee: dict = Depends(verify_employee)
):
    """
    Get detailed information about the current user including:
    - Basic profile information
    - Mood score statistics
    - Chat history summary
    - Upcoming meetings and sessions
    - Company data
    """
    try:
        # Get employee details
        employee_data = await Employee.get_by_id(employee["employee_id"])
        if not employee_data:
            raise HTTPException(
                status_code=404,
                detail="Employee not found"
            )

        # Get all chats for mood analysis
        chats = await Chat.find({"user_id": employee["employee_id"]}).to_list()
        
        # Calculate mood statistics
        mood_scores = []
        emotion_distribution = defaultdict(int)
        total_sessions = 0
        
        for chat in chats:
            if chat.mood_score > 0:  # Only count sessions with assigned mood scores
                mood_scores.append(chat.mood_score)
                total_sessions += 1
                
                # Map mood score to emotion zone
                if chat.mood_score <= 2:
                    emotion_distribution[EmotionZone.SAD] += 1
                elif chat.mood_score <= 3:
                    emotion_distribution[EmotionZone.LEANING_SAD] += 1
                elif chat.mood_score == 4:
                    emotion_distribution[EmotionZone.NEUTRAL] += 1
                elif chat.mood_score <= 5:
                    emotion_distribution[EmotionZone.LEANING_HAPPY] += 1
                else:
                    emotion_distribution[EmotionZone.HAPPY] += 1

        # Calculate average mood score
        average_score = sum(mood_scores) / len(mood_scores) if mood_scores else 0
        
        # Get last 5 mood scores
        last_5_scores = sorted(mood_scores, reverse=True)[:5]

        # Calculate chat summary
        total_messages = sum(len(chat.messages) for chat in chats)
        last_chat = max(chats, key=lambda x: x.updated_at) if chats else None

        # Get upcoming meetings count
        upcoming_meets = await Meet.find({
            "$or": [
                {"user_id": employee["employee_id"]},
                {"with_user_id": employee["employee_id"]}
            ],
            "scheduled_at": {"$gt": datetime.datetime.utcnow()},
            "status": MeetStatus.SCHEDULED
        }).count()

        # Get upcoming sessions count
        upcoming_sessions = await Session.find({
            "user_id": employee["employee_id"],
            "scheduled_at": {"$gt": datetime.datetime.utcnow()},
            "status": SessionStatus.PENDING
        }).count()

        return UserDetails(
            employee_id=employee_data.employee_id,
            name=employee_data.name,
            email=employee_data.email,
            role=employee_data.role,
            manager_id=employee_data.manager_id,
            is_blocked=employee_data.is_blocked,
            mood_stats=MoodScoreStats(
                average_score=average_score,
                total_sessions=total_sessions,
                emotion_distribution=dict(emotion_distribution),
                last_5_scores=last_5_scores
            ),
            chat_summary=ChatSummary(
                total_chats=len(chats),
                average_mood_score=average_score,
                last_chat_date=last_chat.updated_at if last_chat else None,
                total_messages=total_messages
            ),
            upcoming_meets=upcoming_meets,
            upcoming_sessions=upcoming_sessions,
            company_data=employee_data.company_data.dict() if employee_data.company_data else None
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching user profile: {str(e)}"
        )


@router.get("/scheduled-meets", response_model=List[MeetResponse], tags=["Employee"])
async def get_scheduled_meets(
    employee: dict = Depends(verify_employee)
):
    """
    Get all scheduled meetings for the current user.
    Returns meetings where the user is either the organizer or participant.
    """
    try:
        # Get meetings where user is the organizer
        organizer_meets = await Meet.find({
            "user_id": employee["employee_id"],
            "scheduled_at": {"$gt": datetime.datetime.utcnow()},
            "status": MeetStatus.SCHEDULED
        }).to_list()

        # Get meetings where user is the participant
        participant_meets = await Meet.find({
            "with_user_id": employee["employee_id"],
            "scheduled_at": {"$gt": datetime.datetime.utcnow()},
            "status": MeetStatus.SCHEDULED
        }).to_list()

        # Combine and sort by scheduled time
        all_meets = organizer_meets + participant_meets
        all_meets.sort(key=lambda x: x.scheduled_at)

        return all_meets

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching scheduled meetings: {str(e)}"
        )


@router.get("/scheduled-sessions", response_model=List[SessionResponse], tags=["Employee"])
async def get_scheduled_sessions(
    employee: dict = Depends(verify_employee)
):
    """
    Get all scheduled sessions for the current user.
    Returns only pending sessions that are scheduled for the future.
    """
    try:
        sessions = await Session.find({
            "user_id": employee["employee_id"],
            "scheduled_at": {"$gt": datetime.datetime.utcnow()},
            "status": SessionStatus.PENDING
        }).sort("scheduled_at").to_list()

        return sessions

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching scheduled sessions: {str(e)}"
        )