from fastapi import APIRouter, HTTPException, Depends
from typing import List
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

async def verify_employee(token: str = Depends(JWTBearer())):
    """Verify that the user is an employee."""
    payload = decode_jwt(token)
    if not payload or payload.get("role") != "employee":
        raise HTTPException(
            status_code=403,
            detail="Only employees can access this endpoint"
        )
    return payload

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
    session = await Session.get(chat.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")
    
    # Activate session if not already active
    if session.status != SessionStatus.ACTIVE:
        session.status = SessionStatus.ACTIVE
        await session.save()
    
    # Add employee message
    await chat.add_message(SenderType.EMPLOYEE, request.message)
    
    # TODO: Implement actual LLM integration here
    # For now, using placeholder response
    bot_response = "Thank you for reaching out. I'm here to help. Can you tell me more about what's on your mind?"
    await chat.add_message(SenderType.BOT, bot_response)
    
    # TODO: Implement sentiment analysis here
    # This would be called after every message
    # If sentiment is negative, escalate to HR
    
    return {
        "message": bot_response,
        "chatId": chat.chat_id,
        "sessionStatus": session.status
    }

@router.patch("/status")
async def update_chat_status(request: ChatStatusRequest, current_user: dict = Depends(verify_employee)):
    """
    Update chat mode between bot and HR (Admin & HR only)
    """
    if current_user["role"] not in ["admin", "hr"]:
        raise HTTPException(status_code=403, detail="Only admin and HR can update chat status")
    
    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    await chat.update_chat_mode(request.status)
    return {"message": f"Chat status updated to {request.status} mode"}

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