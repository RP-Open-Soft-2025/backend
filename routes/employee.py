# routes only for employee

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel, Field
from models.meet import Meet, MeetStatus
from models.session import Session, SessionStatus
from models.chat import Chat
from models.employee import Employee, CompanyData
from models.chain import Chain, ChainStatus
import datetime
from models.notification import Notification, NotificationStatus
from bson import ObjectId
from config.config import Settings
from utils.verify_employee import verify_employee

router = APIRouter()

llm_add = Settings().LLM_ADDR

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
    # emotion_distribution: dict[str, int] = Field(default_factory=lambda: {
    #     "Sad Zone": 0,
    #     "Leaning to Sad Zone": 0,
    #     "Neutral Zone (OK)": 0,
    #     "Leaning to Happy Zone": 0,
    #     "Happy Zone": 0
    # })
    last_5_scores: List[int] = Field(default_factory=list)


class ChatSummary(BaseModel):
    chat_id: str
    last_message: Optional[str] = None
    last_message_time: Optional[datetime.datetime] = None
    unread_count: int = 0
    total_messages: int = 0
    chat_mode: str
    is_escalated: bool = False
    created_at: Optional[datetime.datetime] = None


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
    meeting_link: Optional[str] = None
    recent_chains: List[Dict[str, Any]] = Field(default_factory=list)

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


class NotificationResponse(BaseModel):
    id: str
    employee_id: str
    title: str
    description: str
    created_at: datetime.datetime
    status: NotificationStatus

class SessionMessageGroup(BaseModel):
    session_id: str
    chat_id: str
    messages: List[ChatMessage]
    total_messages: int

class ChainMessagesResponse(BaseModel):
    chain_id: str
    sessions: List[SessionMessageGroup]
    total_sessions: int
    total_messages: int
    last_updated: datetime.datetime
    chat_mode: str
    is_escalated: bool = False

async def get_formatted_meeting(meet_id: str):
    """Helper function to get a meeting and format it properly for serialization"""
    meeting = await Meet.find_one({"meet_id": meet_id})
    if not meeting:
        return None
    
    # Convert to dictionary and remove _id field which contains PydanticObjectId
    meeting_dict = meeting.model_dump(exclude={"id"})
    return meeting_dict

@router.get("/profile", response_model=UserDetails, tags=["Employee"])
async def get_user_profile(
    employee: dict = Depends(verify_employee)
):
    """
    Get detailed information about the current user including:
    - Basic profile information
    - Mood score statistics
    - Chat history summary (most recently updated chat)
    - Upcoming meetings and sessions
    - Company data
    """
    try:
        response = UserDetails(
            employee_id=employee.employee_id,
            name=employee.name,
            email=employee.email,
            role=employee.role,
            manager_id=employee.manager_id,
            is_blocked=employee.is_blocked,
            mood_stats=MoodScoreStats(),
            chat_summary=ChatSummary(
                chat_id="",
                chat_mode="BOT"
            ),
            upcoming_meets=0,
            upcoming_sessions=0,
            company_data=employee.company_data,
            meeting_link=employee.meeting_link
        )

        try:
            # Get all chats for mood analysis
            chats = await Chat.find({"user_id": employee.employee_id}).to_list()
            
            if chats and len(chats) > 0:
                # Calculate mood statistics
                mood_scores = []
                total_sessions = 0
                
                for chat in chats:
                    if hasattr(chat, 'mood_score') and chat.mood_score and chat.mood_score > 0:
                        mood_scores.append(chat.mood_score)
                        total_sessions += 1

                # Calculate mood stats if there are valid scores
                if mood_scores:
                    average_score = sum(mood_scores) / len(mood_scores)
                    last_5_scores = sorted(mood_scores, reverse=True)[:5]
                    
                    response.mood_stats = MoodScoreStats(
                        average_score=average_score,
                        total_sessions=total_sessions,
                        last_5_scores=last_5_scores
                    )

                # Find the most recently updated chat
                latest_chat = max(chats, key=lambda x: x.updated_at.replace(tzinfo=datetime.timezone.utc) if hasattr(x, 'updated_at') else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
                
                if latest_chat:
                    last_message = None
                    last_message_time = None
                    
                    if hasattr(latest_chat, 'messages') and latest_chat.messages and len(latest_chat.messages) > 0:
                        last_message_obj = latest_chat.messages[-1]
                        if hasattr(last_message_obj, 'text'):
                            last_message = last_message_obj.text
                        if hasattr(last_message_obj, 'timestamp'):
                            last_message_time = last_message_obj.timestamp.replace(tzinfo=datetime.timezone.utc)
                    
                    response.chat_summary = ChatSummary(
                        chat_id=latest_chat.chat_id,
                        last_message=last_message,
                        last_message_time=last_message_time or latest_chat.updated_at.replace(tzinfo=datetime.timezone.utc),
                        unread_count=latest_chat.unread_count if hasattr(latest_chat, 'unread_count') else 0,
                        total_messages=len(latest_chat.messages),
                        chat_mode=latest_chat.chat_mode.value if hasattr(latest_chat, 'chat_mode') else "BOT",
                        is_escalated=latest_chat.is_escalated if hasattr(latest_chat, 'is_escalated') else False,
                        created_at=latest_chat.created_at.replace(tzinfo=datetime.timezone.utc)
                    )
                        
        except Exception as e:
            print(f"Error processing chat data: {str(e)}")

        try:
            # Get upcoming meetings count
            response.upcoming_meets = await Meet.find({
                "$or": [
                    {"user_id": employee.employee_id},
                    {"with_user_id": employee.employee_id}
                ],
                "scheduled_at": {"$gt": datetime.datetime.now(datetime.timezone.utc)},
                "status": MeetStatus.SCHEDULED
            }).count()
        except Exception as e:
            print(f"Error getting upcoming meets: {str(e)}")

        try:
            # Get upcoming sessions count
            response.upcoming_sessions = await Session.find({
                "user_id": employee.employee_id,
                "scheduled_at": {"$gt": datetime.datetime.now(datetime.timezone.utc)},
                "status": SessionStatus.PENDING
            }).count()
        except Exception as e:
            print(f"Error getting upcoming sessions: {str(e)}")

        # Add company data if available
        if employee.company_data:
            try:
                response.company_data = employee.company_data
            except Exception as e:
                print(f"Error processing company data: {str(e)}")
                response.company_data = None

        try:
            # Fetch the last 4 recent chains for the employee
            recent_chains = await Chain.find({"employee_id": employee.employee_id}).sort("-created_at").limit(4).to_list()
            response.recent_chains = [
                {
                    "chain_id": chain.chain_id,
                    "status": chain.status,
                    "notes": chain.notes,
                    "created_at": chain.created_at,
                    "meeting": await get_formatted_meeting(chain.meet_id) if chain.status == ChainStatus.ESCALATED and chain.meet_id else None
                }
                for chain in recent_chains
            ]
        except Exception as e:
            print(f"Error fetching recent chains: {str(e)}")
            response.recent_chains = []

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
            organizer_meets = await Meet.find({
                "user_id": employee.employee_id,
                "scheduled_at": {"$gt": datetime.datetime.now(datetime.timezone.utc)},
                "status": MeetStatus.SCHEDULED
            }).to_list()
            print(organizer_meets)
        except Exception as e:
            print(f"Error fetching organizer meetings: {str(e)}")

        # Get meetings where user is the participant
        try:
            participant_meets = await Meet.find({
                "with_user_id": employee.employee_id,
                "scheduled_at": {"$gt": datetime.datetime.now(datetime.timezone.utc)},  
                "status": MeetStatus.SCHEDULED
            }).to_list()
        except Exception as e:
            print(f"Error fetching participant meetings: {str(e)}")

        # Combine and sort by scheduled time
        all_meets = organizer_meets + participant_meets
        if all_meets:
            all_meets.sort(key=lambda x: x.scheduled_at)

            # For each meeting, get the HR's meeting link if the user is a participant
            for meet in all_meets:
                if meet.with_user_id == employee.employee_id:
                    # User is a participant, get the organizer's (HR's) meeting link
                    hr = await Employee.get_by_id(meet.user_id)
                    if hr and hr.meeting_link:
                        meet.meeting_link = hr.meeting_link

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
            "user_id": employee.employee_id,
            # "scheduled_at": {"$gt": datetime.datetime.now(datetime.timezone.utc)},
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
    - Chat Creation time
    """
    try:
        # Get all chats for the employee
        chats = await Chat.find({"user_id": employee.employee_id}).to_list()

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
                is_escalated=chat.is_escalated if hasattr(chat, 'is_escalated') else False,
                created_at=chat.created_at
            )
            chat_summaries.append(summary)
        
        # Sort chats by last message time (most recent first)
        # chat_summaries.sort(key=lambda x: x.last_message_time or datetime.datetime.min, reverse=True)

        # Broadcast that the employee is viewing their chats
        await employee_chat_manager.broadcast_to_employee(employee.employee_id, {
            "type": "chats_viewed",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
    if chat.user_id != employee.employee_id:
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
    
    return ChatMessagesResponse(
        chat_id=chat.chat_id,
        messages=messages,
        total_messages=len(messages),
        last_updated=chat.updated_at,
        chat_mode=chat.chat_mode.value if hasattr(chat, 'chat_mode') else "BOT",
        is_escalated=chat.is_escalated if hasattr(chat, 'is_escalated') else False
    )

@router.get("/ping", response_model=dict)
async def ping_user(employee: dict = Depends(verify_employee)):
    """
    Update the last known ping time for the employee and return notifications.
    """
    emp_id = employee.employee_id
    try:
        # Update last ping time
        await Employee.find_one({"employee_id": emp_id}).update_one({"$set": {"last_ping": datetime.datetime.now(datetime.timezone.utc)}})
        
        # Get all notifications for the employee
        notifications = await Notification.get_notifications_by_employee(emp_id)
        
        # Format notifications for response
        notification_list = [
            NotificationResponse(
                id=str(notification.id),
                employee_id=notification.employee_id,
                title=notification.title,
                description=notification.description,
                created_at=notification.created_at,
                status=notification.status
            )
            for notification in notifications
        ]
        
        return {
            "message": "Ping time updated successfully",
            "notifications": notification_list
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating ping time: {str(e)}"
        )

@router.patch("/notification/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    employee: dict = Depends(verify_employee)
):
    """
    Mark a notification as read.
    Only the employee who owns the notification can mark it as read.
    """
    try:
        # Convert string ID to ObjectId
        notification_object_id = ObjectId(notification_id)
        
        # Get the notification
        notification = await Notification.find_one({"_id": notification_object_id})
        if not notification:
            raise HTTPException(
                status_code=404,
                detail="Notification not found"
            )
        
        # Verify the notification belongs to the employee
        if notification.employee_id != employee.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only mark your own notifications as read"
            )
        
        # Mark as read
        notification.status = NotificationStatus.READ
        await notification.save()
        
        return NotificationResponse(
            id=str(notification.id),
            employee_id=notification.employee_id,
            title=notification.title,
            description=notification.description,
            created_at=notification.created_at,
            status=notification.status
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error marking notification as read: {str(e)}"
        )

@router.patch("/notification/mark_all_as_read", response_model=List[NotificationResponse])
async def mark_all_notifications_read(
    employee: dict = Depends(verify_employee)
):
    """
    Mark all notifications as read for the current employee.
    Returns the list of updated notifications.
    """
    try:
        # Get all unread notifications for the employee
        notifications = await Notification.find({
            "employee_id": employee.employee_id,
            "status": NotificationStatus.UNREAD
        }).to_list()
        
        # Mark all notifications as read
        for notification in notifications:
            notification.status = NotificationStatus.READ
            await notification.save()
        
        # Return the updated notifications
        return [
            NotificationResponse(
                id=str(notification.id),
                employee_id=notification.employee_id,
                title=notification.title,
                description=notification.description,
                created_at=notification.created_at,
                status=notification.status
            )
            for notification in notifications
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error marking notifications as read: {str(e)}"
        )

class ChainResponse(BaseModel):
    chain_id: str
    employee_id: str
    session_ids: List[str]
    status: ChainStatus
    created_at: datetime.datetime
    notes: Optional[str] = None

@router.get("/chains", response_model=List[ChainResponse], tags=["Employee"])
async def get_employee_chains(employee: dict = Depends(verify_employee)):
    """
    Get all chains for the current employee.
    """
    try:
        chains = await Chain.find({"employee_id": employee.employee_id}).to_list()
        return chains
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving chains: {str(e)}"
        )

@router.get("/chains/{chain_id}", response_model=ChainResponse, tags=["Employee"])
async def get_chain_details(chain_id: str, employee: dict = Depends(verify_employee)):
    """
    Get details of a specific chain.
    """
    try:
        chain = await Chain.get_by_id(chain_id)
        if not chain:
            raise HTTPException(
                status_code=404,
                detail=f"Chain with ID {chain_id} not found"
            )
        
        # Verify the chain belongs to the employee
        if chain.employee_id != employee.employee_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this chain"
            )
        
        return chain
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving chain details: {str(e)}"
        )

@router.get("/chains/{chain_id}/messages", response_model=ChainMessagesResponse, tags=["Employee"])
async def get_chain_messages(
    chain_id: str,
    employee: dict = Depends(verify_employee)
):
    """
    Get all messages from all sessions in a chain, grouped by session.
    """
    try:
        chain = await Chain.get_by_id(chain_id)
        if not chain:
            raise HTTPException(
                status_code=404,
                detail=f"Chain with ID {chain_id} not found"
            )
        
        # Verify the chain belongs to the employee
        if chain.employee_id != employee.employee_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this chain"
            )
        
        # Get all sessions in the chain
        sessions = await Session.find({"session_id": {"$in": chain.session_ids}}).to_list()
        
        # Process each session and its chat
        session_groups = []
        total_messages = 0
        last_updated = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        
        for session in sessions:
            # Get chat for this session
            chat = await Chat.find_one({"chat_id": session.chat_id})
            if chat and chat.messages:
                # Convert messages to ChatMessage model and ensure timestamps are timezone-aware
                messages = []
                for msg in chat.messages:
                    # Ensure timestamp is timezone-aware
                    msg_timestamp = msg.timestamp
                    if msg_timestamp and msg_timestamp.tzinfo is None:
                        msg_timestamp = msg_timestamp.replace(tzinfo=datetime.timezone.utc)
                    
                    messages.append(ChatMessage(
                        sender=msg.sender_type.value,
                        text=msg.text,
                        timestamp=msg_timestamp
                    ))
                
                # Sort messages by timestamp
                messages.sort(key=lambda x: x.timestamp)
                
                # Update last_updated if this chat has more recent messages
                if messages:
                    latest_msg_time = max(
                        (msg.timestamp for msg in messages if msg.timestamp is not None),
                        default=datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
                    )
                    if latest_msg_time > last_updated:
                        last_updated = latest_msg_time
                
                # Create session group
                session_group = SessionMessageGroup(
                    session_id=session.session_id,
                    chat_id=chat.chat_id,
                    messages=messages,
                    total_messages=len(messages)
                )
                session_groups.append(session_group)
                total_messages += len(messages)
        
        # Sort session groups by their first message timestamp
        session_groups.sort(
            key=lambda x: min(
                (msg.timestamp for msg in x.messages if msg.timestamp is not None),
                default=datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
            )
        )
        
        return ChainMessagesResponse(
            chain_id=chain_id,
            sessions=session_groups,
            total_sessions=len(session_groups),
            total_messages=total_messages,
            last_updated=last_updated,
            chat_mode="BOT",
            is_escalated=chain.status == ChainStatus.ESCALATED
        )
    except Exception as e:
        print(f"Chain messages error: {str(e)}")  # Add logging
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving chain messages: {str(e)}"
        )

class ChatToChainResponse(BaseModel):
    chain_id: str
    status: ChainStatus

@router.get("/chat-to-chain/{chat_id}", response_model=ChatToChainResponse, tags=["Employee"])
async def get_chain_from_chat(
    chat_id: str,
    employee: dict = Depends(verify_employee)
):
    """
    Get the chain ID associated with a chat ID.
    Verifies that the chat belongs to the requesting user.
    """
    try:
        # Get the chat
        chat = await Chat.get_chat_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Verify the employee owns this chat
        if chat.user_id != employee.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only access your own chats"
            )
        
        # Find the session that contains this chat
        session = await Session.find_one({"chat_id": chat_id})
        if not session:
            raise HTTPException(status_code=404, detail="No session found for this chat")
        
        # Find the chain that contains this session
        chain = await Chain.find_one({"session_ids": session.session_id})
        if not chain:
            raise HTTPException(status_code=404, detail="No chain found for this chat")
        
        return ChatToChainResponse(
            chain_id=chain.chain_id,
            status=chain.status
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving chain for chat: {str(e)}"
        )
