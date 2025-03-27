# routes only for employee

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel, Field
from models.meet import Meet, MeetStatus
from models.session import Session, SessionStatus
from models.chat import Chat, Message, SenderType
from models.employee import Employee, EmotionZone, CompanyData
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

    # use the payload.employee_id to get the employee details
    employee = await Employee.get_by_id(payload["employee_id"])
    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Employee not found"
        )

    # check if the employee is blocked
    if employee.is_blocked:
        raise HTTPException(
            status_code=401,
            detail="Employee is blocked"
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
    user_id: str
    chat_id: str
    status: SessionStatus
    scheduled_at: datetime.datetime
    created_at: datetime.datetime
    updated_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None
    cancelled_at: Optional[datetime.datetime] = None
    cancelled_by: Optional[str] = None
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
    chat_id: str
    last_message: Optional[str] = None
    last_message_time: Optional[datetime.datetime] = None
    unread_count: int = 0
    total_messages: int = 0
    chat_mode: str
    is_escalated: bool = False


class EmployeeChatsResponse(BaseModel):
    chats: List[ChatSummary]
    total_chats: int


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
    company_data: CompanyData = Field(default_factory=CompanyData)

class ChatMessage(BaseModel):
    sender: str
    text: str
    timestamp: datetime.datetime

class ChatMessagesResponse(BaseModel):
    chat_id: str
    messages: List[ChatMessage]
    total_messages: int
    last_updated: datetime.datetime
    chat_mode: str
    is_escalated: bool = False


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

        # Initialize response with default values
        response = UserDetails(
            employee_id=employee_data.employee_id,
            name=employee_data.name,
            email=employee_data.email,
            role=employee_data.role,
            manager_id=employee_data.manager_id,
            is_blocked=employee_data.is_blocked,
            mood_stats=MoodScoreStats(),
            chat_summary=ChatSummary(
                chat_id="",
                chat_mode="BOT"
            ),
            upcoming_meets=0,
            upcoming_sessions=0,
            company_data=employee_data.company_data
        )

        try:
            # Get all chats for mood analysis
            chats = await Chat.find({"user_id": employee["employee_id"]}).to_list()
            
            if chats and len(chats) > 0:
                # Calculate mood statistics
                mood_scores = []
                emotion_distribution = defaultdict(int)
                total_sessions = 0
                
                for chat in chats:
                    if hasattr(chat, 'mood_score') and chat.mood_score and chat.mood_score > 0:
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
                total_messages = 0
                for chat in chats:
                    if hasattr(chat, 'messages') and chat.messages:
                        total_messages += len(chat.messages)
                
                # Find latest chat
                last_chat = None
                if chats:
                    try:
                        last_chat = max(chats, key=lambda x: x.updated_at if hasattr(x, 'updated_at') else datetime.datetime.min)
                    except Exception as e:
                        print(f"Error finding last chat: {str(e)}")
                
                if last_chat:
                    last_message = None
                    last_message_time = None
                    
                    try:
                        if hasattr(last_chat, 'messages') and last_chat.messages and len(last_chat.messages) > 0:
                            last_message_obj = last_chat.messages[-1]
                            if hasattr(last_message_obj, 'text'):
                                last_message = last_message_obj.text
                            else:
                                last_message = str(last_message_obj)
                                
                            if hasattr(last_message_obj, 'timestamp'):
                                last_message_time = last_message_obj.timestamp
                            else:
                                last_message_time = last_chat.updated_at
                        else:
                            last_message_time = last_chat.updated_at if hasattr(last_chat, 'updated_at') else datetime.datetime.now()
                    except Exception as e:
                        print(f"Error extracting message data: {str(e)}")
                    
                    try:
                        response.chat_summary = ChatSummary(
                            chat_id=last_chat.chat_id,
                            last_message=last_message,
                            last_message_time=last_message_time,
                            unread_count=last_chat.unread_count if hasattr(last_chat, 'unread_count') else 0,
                            total_messages=total_messages,
                            chat_mode=last_chat.chat_mode.value if hasattr(last_chat, 'chat_mode') else "BOT",
                            is_escalated=last_chat.is_escalated if hasattr(last_chat, 'is_escalated') else False
                        )
                    except Exception as e:
                        print(f"Error creating chat summary: {str(e)}")
                        
        except Exception as e:
            # If there's an error getting chat data, continue with default values
            print(f"Error processing chat data: {str(e)}")

        try:
            # Get upcoming meetings count
            response.upcoming_meets = await Meet.find({
                "$or": [
                    {"user_id": employee["employee_id"]},
                    {"with_user_id": employee["employee_id"]}
                ],
                "scheduled_at": {"$gt": datetime.datetime.now(datetime.UTC)},
                "status": MeetStatus.SCHEDULED
            }).count()
        except Exception as e:
            print(f"Error getting upcoming meets: {str(e)}")

        try:
            # Get upcoming sessions count
            response.upcoming_sessions = await Session.find({
                "user_id": employee["employee_id"],
                "scheduled_at": {"$gt": datetime.datetime.now(datetime.UTC)},
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
                if hasattr(employee_data.company_data, "__dict__"):
                    response.company_data = employee_data.company_data.__dict__
                else:
                    response.company_data = None

        return response

    except Exception as e:
        import traceback
        print(f"Error fetching user profile: {str(e)}")
        print(traceback.format_exc())
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
            # print('employee_id: ',employee["employee_id"])
            organizer_meets = await Meet.find({
                "user_id": employee["employee_id"],
                # "scheduled_at": {"$gt": datetime.datetime.now(datetime.UTC)},
                "status": MeetStatus.SCHEDULED
            }).to_list()
            print(organizer_meets)
        except Exception as e:
            print(f"Error fetching organizer meetings: {str(e)}")

        # Get meetings where user is the participant
        try:
            participant_meets = await Meet.find({
                "with_user_id": employee["employee_id"],
                # "scheduled_at": {"$gt": datetime.datetime.now(datetime.UTC)},  
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
            "user_id": employee["employee_id"],
            # "scheduled_at": {"$gt": datetime.datetime.now(datetime.UTC)},
            "status": {"$in": [SessionStatus.PENDING, SessionStatus.ACTIVE]}
        }).to_list()

        return sessions or []

    except Exception as e:
        print(f"Error in get_scheduled_sessions: {str(e)}")
        return []  # Return empty list instead of raising error


# Add WebSocket connection manager for employee chats
class EmployeeChatManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, employee_id: str):
        await websocket.accept()
        if employee_id not in self.active_connections:
            self.active_connections[employee_id] = set()
        self.active_connections[employee_id].add(websocket)

    def disconnect(self, websocket: WebSocket, employee_id: str):
        if employee_id in self.active_connections:
            self.active_connections[employee_id].remove(websocket)
            if not self.active_connections[employee_id]:
                del self.active_connections[employee_id]

    async def broadcast_to_employee(self, employee_id: str, message: Dict[str, Any]):
        if employee_id in self.active_connections:
            for connection in self.active_connections[employee_id]:
                await connection.send_json(message)

employee_chat_manager = EmployeeChatManager()

@router.websocket("/ws/chats/{employee_id}")
async def employee_chats_websocket(websocket: WebSocket, employee_id: str):
    """
    WebSocket endpoint for real-time employee chat updates.
    """
    await employee_chat_manager.connect(websocket, employee_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
            # For now, we'll just keep the connection alive
    except WebSocketDisconnect:
        employee_chat_manager.disconnect(websocket, employee_id)

@router.get("/chats", response_model=EmployeeChatsResponse, tags=["Employee"])
async def get_employee_chats(
    employee: dict = Depends(verify_employee)
):
    """
    Get all chats for the current employee with real-time updates.
    Returns a summary of each chat including:
    - Last message
    - Last message time
    - Unread message count
    - Total messages
    - Chat mode
    - Escalation status
    """
    try:
        # Get all chats for the employee
        chats = await Chat.find({"user_id": employee["employee_id"]}).to_list()

        chat_summaries = []
        for chat in chats:
            # Get the last message if any
            last_message = None
            last_message_time = None
            if chat.messages:
                last_message = chat.messages[-1].text
                last_message_time = chat.messages[-1].timestamp
            
            # Create chat summary
            summary = ChatSummary(
                chat_id=chat.chat_id,
                last_message=last_message,
                last_message_time=last_message_time,
                unread_count=chat.unread_count if hasattr(chat, 'unread_count') else 0,
                total_messages=len(chat.messages),
                chat_mode=chat.chat_mode.value if hasattr(chat, 'chat_mode') else "BOT",
                is_escalated=chat.is_escalated if hasattr(chat, 'is_escalated') else False
            )
            chat_summaries.append(summary)
        
        # Sort chats by last message time (most recent first)
        # chat_summaries.sort(key=lambda x: x.last_message_time or datetime.datetime.min, reverse=True)

        # Broadcast that the employee is viewing their chats
        await employee_chat_manager.broadcast_to_employee(employee["employee_id"], {
            "type": "chats_viewed",
            "timestamp": datetime.datetime.now().isoformat(),
            "total_chats": len(chat_summaries)
        })
        
        return EmployeeChatsResponse(
            chats=chat_summaries,
            total_chats=len(chat_summaries)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching employee chats: {str(e)}"
        )

@router.get("/chats/{chat_id}/messages", response_model=ChatMessagesResponse, tags=["Employee"])
async def get_chat_messages(
    chat_id: str,
    employee: dict = Depends(verify_employee)
):
    """
    Get all messages for a specific chat.
    Only accessible to the employee who owns the chat.
    """
    # Get the chat
    chat = await Chat.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Verify the employee owns this chat
    if chat.user_id != employee["employee_id"]:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own chats"
        )
    
    # Transform messages to the expected format
    messages = []
    try:
        for msg in chat.messages:
            messages.append(ChatMessage(
                sender=msg.sender_type.value,
                text=msg.text,
                timestamp=msg.timestamp
            ))
    except Exception as e:
        print(f"Error processing messages: {str(e)}")
        import traceback
        print(traceback.format_exc())
    
    # Broadcast that the employee is viewing the chat
    await employee_chat_manager.broadcast_to_employee(employee["employee_id"], {
        "type": "chat_viewed",
        "chat_id": chat_id,
        "timestamp": datetime.datetime.now().isoformat()
    })
    
    return ChatMessagesResponse(
        chat_id=chat.chat_id,
        messages=messages,
        total_messages=len(messages),
        last_updated=chat.updated_at,
        chat_mode=chat.chat_mode.value if hasattr(chat, 'chat_mode') else "BOT",
        is_escalated=chat.is_escalated if hasattr(chat, 'is_escalated') else False
    )

@router.get("/ping")
async def ping_user(employee: dict = Depends(verify_employee)):
    """
    Update the last known ping time for the employee.
    """
    emp_id = employee["employee_id"]
    try:
        await Employee.update(
            {"employee_id": emp_id},
            {"$set": {"last_ping_time": datetime.datetime.now()}}
        )
        return {"message": "Ping time updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating ping time: {str(e)}"
        )
