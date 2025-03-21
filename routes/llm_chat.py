from fastapi import APIRouter, HTTPException, Depends
from typing import List
from models.chat import Chat, ChatMode, SenderType, SentimentType
from auth.auth import get_current_user
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/llm/chat", tags=["llm_chat"])

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

@router.post("/message")
async def send_message(request: ChatMessageRequest, current_user: dict = Depends(get_current_user)):
    """
    Send a message to the chat system (placeholder for future LLM integration)
    """
    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Add user message
    await chat.add_message(SenderType.EMPLOYEE, request.message)
    
    # Placeholder bot response (to be replaced with actual LLM integration)
    bot_response = "Thank you for reaching out. I'm here to help. Can you tell me more about what's on your mind?"
    await chat.add_message(SenderType.BOT, bot_response)
    
    return {"message": bot_response}

@router.patch("/status")
async def update_chat_status(request: ChatStatusRequest, current_user: dict = Depends(get_current_user)):
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
async def escalate_chat(request: ChatEscalationRequest, current_user: dict = Depends(get_current_user)):
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
async def get_chat_history(chat_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get chat history for review (Admin & HR only)
    """
    if current_user["role"] not in ["admin", "hr"]:
        raise HTTPException(status_code=403, detail="Only admin and HR can view chat history")
    
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
    
    return ChatHistoryResponse(
        chatId=chat.chat_id,
        messages=messages
    ) 