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
    average_score: float = 0.0
    total_sessions: int = 0
    emotion_distribution: dict[str, int] = Field(default_factory=lambda: {
        "Sad Zone": 0,
        "Leaning to Sad Zone": 0,
        "Neutral Zone (OK)": 0,
        "Leaning to Happy Zone": 0,
        "Happy Zone": 0
    })
    last_5_scores: List[int] = Field(default_factory=list)


class ChatSummary(BaseModel):
    total_chats: int = 0
    average_mood_score: float = 0.0
    last_chat_date: Optional[datetime.datetime] = None
    total_messages: int = 0


class UserDetails(BaseModel):
    employee_id: str
    name: str
    email: str
    role: str
    manager_id: Optional[str] = None
    is_blocked: bool = False
    mood_stats: MoodScoreStats = Field(default_factory=MoodScoreStats)
    chat_summary: ChatSummary = Field(default_factory=ChatSummary)
    upcoming_meets: int = 0
    upcoming_sessions: int = 0
    company_data: Optional[dict] = None


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
    - Company dataaa
    """
    try:
        # Get employee details
        employee_data = await Employee.get_by_id(employee["user_id"])
        if not employee_data:
            raise HTTPException(
                status_code=404,
                detail="Employee not found"
            )

        # Initialize response with default values
        response = UserDetails(
            employee_id=employee_data.employee_id,
            name=employee_data.name,
            email=employee_data.email,
            role=employee_data.role,
            manager_id=employee_data.manager_id,
            is_blocked=employee_data.is_blocked
        )

        try:
            # Get all chats for mood analysis
            chats = await Chat.find({"user_id": employee["user_id"]}).to_list()
            
            if chats:
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

                # Calculate mood stats if there are valid scores
                if mood_scores:
                    average_score = sum(mood_scores) / len(mood_scores)
                    last_5_scores = sorted(mood_scores, reverse=True)[:5]
                    
                    response.mood_stats = MoodScoreStats(
                        average_score=average_score,
                        total_sessions=total_sessions,
                        emotion_distribution=dict(emotion_distribution),
                        last_5_scores=last_5_scores
                    )

                # Calculate chat summary
                total_messages = sum(len(chat.messages) for chat in chats)
                last_chat = max(chats, key=lambda x: x.updated_at) if chats else None
                
                response.chat_summary = ChatSummary(
                    total_chats=len(chats),
                    average_mood_score=response.mood_stats.average_score,
                    last_chat_date=last_chat.updated_at if last_chat else None,
                    total_messages=total_messages
                )
        except Exception as e:
            # If there's an error getting chat data, continue with default values
            print(f"Error processing chat data: {str(e)}")

        try:
            # Get upcoming meetings count
            response.upcoming_meets = await Meet.find({
                "$or": [
                    {"user_id": employee["user_id"]},
                    {"with_user_id": employee["user_id"]}
                ],
                "scheduled_at": {"$gt": datetime.datetime.utcnow()},
                "status": MeetStatus.SCHEDULED
            }).count()
        except Exception as e:
            print(f"Error getting upcoming meets: {str(e)}")

        try:
            # Get upcoming sessions count
            response.upcoming_sessions = await Session.find({
                "user_id": employee["user_id"],
                "scheduled_at": {"$gt": datetime.datetime.utcnow()},
                "status": SessionStatus.PENDING
            }).count()
        except Exception as e:
            print(f"Error getting upcoming sessions: {str(e)}")

        # Add company data if available
        if employee_data.company_data:
            try:
                response.company_data = employee_data.company_data.dict()
            except Exception as e:
                print(f"Error processing company data: {str(e)}")

        return response

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
        organizer_meets = []
        participant_meets = []

        # Get meetings where user is the organizer
        try:
            organizer_meets = await Meet.find({
                "user_id": employee["user_id"],
                "scheduled_at": {"$gt": datetime.datetime.utcnow()},
                "status": MeetStatus.SCHEDULED
            }).to_list()
        except Exception as e:
            print(f"Error fetching organizer meetings: {str(e)}")

        # Get meetings where user is the participant
        try:
            participant_meets = await Meet.find({
                "with_user_id": employee["user_id"],
                "scheduled_at": {"$gt": datetime.datetime.utcnow()},
                "status": MeetStatus.SCHEDULED
            }).to_list()
        except Exception as e:
            print(f"Error fetching participant meetings: {str(e)}")

        # Combine and sort by scheduled time
        all_meets = organizer_meets + participant_meets
        if all_meets:
            all_meets.sort(key=lambda x: x.scheduled_at)

        return all_meets

    except Exception as e:
        print(f"Error in get_scheduled_meets: {str(e)}")
        return []  # Return empty list instead of raising error


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
            "user_id": employee["user_id"],
            "scheduled_at": {"$gt": datetime.datetime.utcnow()},
            "status": SessionStatus.PENDING
        }).sort("scheduled_at").to_list()

        return sessions or []  # Return empty list if no sessions found

    except Exception as e:
        print(f"Error in get_scheduled_sessions: {str(e)}")
        return []  # Return empty list instead of raising error