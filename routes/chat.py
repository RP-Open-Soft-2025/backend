from fastapi import APIRouter, Depends, HTTPException, status, Header, Body, WebSocket, WebSocketDisconnect
from typing import Dict, Any, List, Set
from auth.jwt_handler import decode_jwt
from auth.jwt_bearer import JWTBearer
from models.chat import Chat, SenderType
from datetime import timedelta, datetime
from pydantic import BaseModel
from models.session import Session, SessionStatus
from models.employee import Employee, Role
from models.meet import Meet, MeetStatus
from typing import Optional
from utils.verify_hr import verify_hr
from utils.verify_employee import verify_employee

router = APIRouter()
class EscalateChatRequest(BaseModel):
    chatId: str
    detectedSentiment: str
    reason: str
    timeDuration: Optional[int]

class ChatMessageRequest(BaseModel):
    chatId: str
    message: str

class ChatMessage(BaseModel):
    sender: str
    text: str
    timestamp: datetime

class ChatHistoryResponse(BaseModel):
    chatId: str
    messages: List[ChatMessage]

class ChatMessagesResponse(BaseModel):
    chat_id: str
    messages: List[ChatMessage]
    total_messages: int
    last_updated: datetime

# Add WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, chat_id: str):
        await websocket.accept()
        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = set()
        self.active_connections[chat_id].add(websocket)

    def disconnect(self, websocket: WebSocket, chat_id: str):
        if chat_id in self.active_connections:
            self.active_connections[chat_id].remove(websocket)
            if not self.active_connections[chat_id]:
                del self.active_connections[chat_id]

    async def broadcast_to_chat(self, chat_id: str, message: Dict[str, Any]):
        if chat_id in self.active_connections:
            for connection in self.active_connections[chat_id]:
                await connection.send_json(message)

manager = ConnectionManager()

async def verify_chat_access(admin_hr_id: str, chat_id: str, role: str):
    """Verify that the user has rights to access the chat."""
    if role == "admin":
        return True
    
    # Get the chat
    chat = await Chat.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(
            status_code=404,
            detail=f"Chat with ID {chat_id} not found"
        )
    
    # Get the employee associated with the chat
    employee = await Employee.get_by_id(chat.user_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee associated with chat {chat_id} not found"
        )
    
    # HR can only access chats for employees assigned to them
    if employee.manager_id != admin_hr_id:
        raise HTTPException(
            status_code=403,
            detail="You can only access chats for employees assigned to you"
        )
    
    return True

@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: str):
    """
    WebSocket endpoint for real-time chat updates.
    """
    await manager.connect(websocket, chat_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
            # For now, we'll just keep the connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)

@router.post("/message-to-employee")
async def send_message(
    request: ChatMessageRequest,
    admin_hr: dict = Depends(verify_hr)
):
    """
    Send a message to an employee.
    Only administrators and HR can access this endpoint.
    HR can only send messages to employees assigned to them.
    """
    # Verify access rights
    await verify_chat_access(admin_hr["employee_id"], request.chatId, admin_hr["role"])
    
    # Get the chat
    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Get associated session
    session = await Session.find_one({"chat_id": chat.chat_id})
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")
    
    # Activate session if not already active
    if session.status != SessionStatus.ACTIVE:
        session.status = SessionStatus.ACTIVE
        await session.save()
    
    # Add HR/Admin message
    await chat.add_message(
        admin_hr["role"],
        request.message
    )
    
    # Broadcast the new message to all connected clients
    await manager.broadcast_to_chat(request.chatId, {
        "type": "new_message",
        "sender": admin_hr["role"],
        "message": request.message,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "message": "Message sent successfully",
        "chatId": chat.chat_id,
        "sessionStatus": session.status
    }

@router.get("/history/{chat_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    chat_id: str,
    admin_hr: dict = Depends(verify_hr)
):
    """
    Get chat history for review.
    Only administrators and HR can access this endpoint.
    HR can only view chats for employees assigned to them.
    """
    # Verify access rights
    await verify_chat_access(admin_hr["employee_id"], chat_id, admin_hr["role"])
    
    chat = await Chat.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = [
        ChatMessage(
            sender=msg.sender_type.value,
            text=msg.text,
            timestamp=msg.timestamp
        )
        for msg in chat.messages
    ]
    
    # Broadcast that someone is viewing the chat
    await manager.broadcast_to_chat(chat_id, {
        "type": "viewer_joined",
        "viewer_role": admin_hr["role"],
        "timestamp": datetime.now().isoformat()
    })
    
    return ChatHistoryResponse(
        chatId=chat.chat_id,
        messages=messages
    )

@router.post("/message-from-employee")
async def receive_message(
    request: ChatMessageRequest,
    employee: dict = Depends(verify_employee)
):
    """
    Receive a message from an employee.
    """
    
    # Get the chat
    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Verify the employee owns this chat
    if chat.user_id != employee["employee_id"]:
        raise HTTPException(
            status_code=403,
            detail="You can only send messages to your own chat"
        )
    
    # Get associated session
    session = await Session.find_one({"chat_id": chat.chat_id})
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")
    
    # Activate session if not already active
    if session.status != SessionStatus.ACTIVE:
        session.status = SessionStatus.ACTIVE
        await session.save()
    
    # Add employee message
    await chat.add_message(
        SenderType.EMPLOYEE,
        request.message
    )
    
    # Broadcast the new message to all connected clients
    await manager.broadcast_to_chat(request.chatId, {
        "type": "new_message",
        "sender": SenderType.EMPLOYEE.value,
        "message": request.message,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "message": "Message sent successfully",
        "chatId": chat.chat_id,
        "sessionStatus": session.status
    }

def assignTimeCalendar(existing_meetings: list[Meet], duration: int = 60) -> datetime:
    """
    Find the earliest available time slot in a calendar using a greedy scheduling approach.
    
    Args:
        existing_meetings: List of existing Meet objects with scheduled_at and duration_minutes attributes
        duration: Duration in minutes for the new meeting (default 60 minutes)
        
    Returns:
        datetime: The earliest available datetime for scheduling the new meeting
    """
    
    current_time = datetime.datetime.now()
    earliest_start_time = current_time
    
    # If no meetings exist, use the earliest start time
    if not existing_meetings:
        return earliest_start_time
        
    # Sort existing meetings by start time
    sorted_meetings = sorted(existing_meetings, key=lambda m: m.scheduled_at)
    
    # Check if there's space before the first meeting
    first_meeting_start = sorted_meetings[0].scheduled_at
    if (first_meeting_start - earliest_start_time).total_seconds() / 60 >= duration:
        return earliest_start_time
    
    # Check for gaps between meetings
    for i in range(len(sorted_meetings) - 1):
        current_meeting_end = sorted_meetings[i].scheduled_at + timedelta(minutes=sorted_meetings[i].duration_minutes)
        next_meeting_start = sorted_meetings[i + 1].scheduled_at
        
        # If current meeting ends after our earliest possible start time
        # and there's enough gap before the next meeting
        if current_meeting_end >= earliest_start_time and \
           (next_meeting_start - current_meeting_end).total_seconds() / 60 >= duration:
            return max(current_meeting_end, earliest_start_time)
    
    # If no suitable gap found, schedule after the last meeting
    last_meeting = sorted_meetings[-1]
    last_meeting_end = last_meeting.scheduled_at + timedelta(minutes=last_meeting.duration_minutes)
    return max(last_meeting_end, earliest_start_time)