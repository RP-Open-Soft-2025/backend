from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any, Set
from models.chat import Chat, ChatMode, SenderType, SentimentType
from models.session import Session, SessionStatus
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
from pydantic import BaseModel
from datetime import datetime
from config.config import Settings
import requests
from routes.admin_hr import verify_admin_or_hr
from routes.employee import ChatSummary, EmployeeChatsResponse 
from models import Employee

router = APIRouter()
llm_add = Settings().LLM_ADDR


class ChatMessageRequest(BaseModel):
    chatId: str
    message: str

class ChatStatusRequest(BaseModel):
    chatId: str
    status: ChatMode

class ChatEscalationRequest(BaseModel):
    chatId: str
    detectedSentiment: SentimentType
    reason: str

class ChatMessage(BaseModel):
    sender: str
    text: str
    timestamp: datetime

class ChatHistoryResponse(BaseModel):
    chatId: str
    messages: List[ChatMessage]

# Add WebSocket connection manager
class LLMConnectionManager:
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

llm_manager = LLMConnectionManager()

async def verify_employee(token: str = Depends(JWTBearer())):
    """Verify that the user is an employee."""
    payload = decode_jwt(token)
    if not payload or payload.get("role") != "employee":
        raise HTTPException(
            status_code=403,
            detail="Only employees can access this endpoint"
        )
    return payload

@router.websocket("/ws/llm/{chat_id}")
async def llm_websocket_endpoint(websocket: WebSocket, chat_id: str):
    """
    WebSocket endpoint for real-time LLM chat updates.
    """
    await llm_manager.connect(websocket, chat_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
            # For now, we'll just keep the connection alive
    except WebSocketDisconnect:
        llm_manager.disconnect(websocket, chat_id)

@router.post("/message")
async def send_message(
    request: ChatMessageRequest,
    employee: dict = Depends(verify_employee)
):
    """
    Send a message to the LLM bot and get a response.
    Also handles sentiment analysis and potential escalation.
    """
    # Get or create chat
    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Verify employee owns this chat
    if chat.user_id != employee["employee_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    
    # Get associated session
    session = await Session.find_one({"chat_id": chat.chat_id})
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")
    
    # Activate session if not already active
    if session.status != SessionStatus.ACTIVE:
        session.status = SessionStatus.ACTIVE
        await session.save()
    
    # Add employee message
    await chat.add_message(SenderType.EMPLOYEE, request.message)
    
    # Broadcast employee message
    await llm_manager.broadcast_to_chat(request.chatId, {
        "type": "new_message",
        "sender": SenderType.EMPLOYEE.value,
        "message": request.message,
        "timestamp": datetime.now().isoformat()
    })
    
    # TODO: Implement actual LLM integration here
    # For now, using placeholder response
    session_id = session.session_id
    bot_response = "Thank you for reaching out. I'm here to help. Can you tell me more about what's on your mind?"
    try:
        data = {"session_id": session_id, "message": request.message}
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{llm_add}/message", json=data, headers=headers)
        bot_response = response.json()["message"]
    except Exception as e:
        HTTPException(500, detail=str(e))
    await chat.add_message(SenderType.BOT, bot_response)
    
    # Broadcast bot response
    await llm_manager.broadcast_to_chat(request.chatId, {
        "type": "new_message",
        "sender": SenderType.BOT.value,
        "message": bot_response,
        "timestamp": datetime.now().isoformat()
    })
    
    # TODO: Implement sentiment analysis here
    # This would be called after every message
    # If sentiment is negative, escalate to HR
    
    return {
        "message": bot_response,
        "chatId": chat.chat_id,
        "sessionStatus": session.status
    }

@router.patch("/initiate-chat")
async def initiate_chat(request: ChatStatusRequest, current_user: dict = Depends(verify_employee)):
    """
    Initiate a chat between bot and employee
    """

    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Update created_at to current time
    chat.created_at = datetime.now().isoformat()
    
    # await chat.update_chat_mode(request.status)
    session = await Session.find_one({"chat_id": chat.chat_id})
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")
    
    session.status = SessionStatus.ACTIVE
    await session.save()
    session_id = session.session_id
    bot_response = "Good Morning. First Question?"
    try:
        response = requests.post(f"{llm_add}/start_session", data={"session_id": session_id, "employee_id": chat.user_id})
        bot_response = response.json()["message"]
    except Exception as e:
        HTTPException(500, detail=str(e))
        
    await chat.add_message(SenderType.BOT, bot_response)
    
    # Save the chat with updated created_at
    await chat.save()
    
    # Broadcast status update
    await llm_manager.broadcast_to_chat(request.chatId, {
        "type": "status_update",
        "status": request.status,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "message": bot_response,
        "chatId": chat.chat_id,
        "sessionStatus": session.status
    }

@router.patch("/escalate")
async def escalate_chat(request: ChatEscalationRequest, current_user: dict = Depends(verify_employee)):
    """
    Escalate chat to HR based on sentiment (placeholder logic)
    """
    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Placeholder escalation logic (to be replaced with actual sentiment analysis)
    if request.detectedSentiment in [SentimentType.VERY_NEGATIVE, SentimentType.NEGATIVE]:
        await chat.escalate_chat(request.reason)
        
        # Broadcast escalation
        await llm_manager.broadcast_to_chat(request.chatId, {
            "type": "escalation",
            "reason": request.reason,
            "sentiment": request.detectedSentiment,
            "timestamp": datetime.now().isoformat()
        })
        
        return {"message": "Chat flagged for HR review due to detected distress."}
    
    return {"message": "Chat escalation not required at this time."}

@router.get("/history/{chat_id}", response_model=List[ChatSummary])
async def get_chat_history(
    chat_id: str,
    employee: dict = Depends(verify_admin_or_hr)
):
    """
    Get chat history for the employee.
    """
    chat = Chat.find({"chat_id": chat_id})
    chat = await chat.to_list()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    user_id = chat[0].user_id

    user = await Employee.find_one({"employee_id": user_id})
    if employee.get("role") == "hr" and user.manager_id != employee.get("employee_id"):
        raise HTTPException(
            status_code=404,
            detail="HR Cannot perform this actions"
        )
    try:
        # Get all chats for the employee
        chats = Chat.find({"user_id": user_id})
        chats = await chats.to_list()
        chat_summaries = []
        for chat in chats:
            last_message = chat.messages[-1].text if chat.messages else None
            last_message_time = chat.messages[-1].timestamp if chat.messages else None
            
            summary = ChatSummary(
                chat_id=chat.chat_id,
                last_message=last_message,
                last_message_time=last_message_time,
                unread_count=getattr(chat, 'unread_count', 0),
                total_messages=len(chat.messages) if chat.messages else 0,
                chat_mode=getattr(chat, 'chat_mode', 'BOT').value if hasattr(chat, 'chat_mode') else "BOT",
                is_escalated=getattr(chat, 'is_escalated', False),
                created_at=chat.created_at
            )
            chat_summaries.append(summary)
        
        return chat_summaries
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching employee chats: {str(e)}"
        )
