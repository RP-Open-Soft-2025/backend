from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any, Set
from models.chat import Chat, ChatMode, SenderType, SentimentType
from models.session import Session, SessionStatus
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

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
    bot_response = "Thank you for reaching out. I'm here to help. Can you tell me more about what's on your mind?"
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
    
    # await chat.update_chat_mode(request.status)
    session = await Session.find_one({"chat_id": chat.chat_id})
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")
    
    session.status = SessionStatus.ACTIVE
    await session.save()

    bot_response = "Good Morning. First Question?"
    await chat.add_message(SenderType.BOT, bot_response)
    
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

@router.get("/history/{chat_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    chat_id: str,
    employee: dict = Depends(verify_employee)
):
    """
    Get chat history for the employee.
    """
    chat = await Chat.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Verify employee owns this chat
    if chat.user_id != employee["employee_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    
    messages = [
        ChatMessage(
            sender=msg.sender_type.value,
            text=msg.text,
            timestamp=msg.timestamp
        )
        for msg in chat.messages
    ]
    
    return ChatHistoryResponse(
        chatId=chat.chat_id,
        messages=messages
    ) 