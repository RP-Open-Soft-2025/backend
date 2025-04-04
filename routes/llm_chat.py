from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any, Set
from models.chat import Chat, ChatMode, SenderType, SentimentType
from models.session import Session, SessionStatus
from models.chain import Chain, ChainStatus
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
from pydantic import BaseModel, Field
from datetime import datetime
from config.config import Settings
import requests
from routes.admin import verify_hr
from routes.employee import ChatSummary, EmployeeChatsResponse 
from models import Employee, Notification
from models.employee import Role

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

class ChainContextUpdateRequest(BaseModel):
    chain_id: str
    session_id: str
    current_context: str

class ChainCompletionRequest(BaseModel):
    chain_id: str
    session_id: str
    reason: str

class EndSessionRequest(BaseModel):
    chat_id: str = Field(..., description="ID of the current chat")
    chain_id: str = Field(..., description="ID of the chain")

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
    
    # Get associated chain
    chain = await Chain.find_one({"session_ids": session.session_id})
    if not chain:
        raise HTTPException(status_code=404, detail="Associated chain not found")
    
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
    
    # Send message to LLM backend (without context)
    bot_response = "Thank you for reaching out. I'm here to help. Can you tell me more about what's on your mind?"
    try:
        data = {
            "session_id": session.session_id,
            "chain_id": chain.chain_id,
            "message": request.message
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{llm_add}/message", json=data, headers=headers)
        response_data = response.json()
        bot_response = response_data["message"]
            
    except Exception as e:
        raise HTTPException(500, detail=str(e))
        
    await chat.add_message(SenderType.BOT, bot_response)
    
    # Broadcast bot response
    await llm_manager.broadcast_to_chat(request.chatId, {
        "type": "new_message",
        "sender": SenderType.BOT.value,
        "message": bot_response,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "message": bot_response,
        "chatId": chat.chat_id,
        "sessionStatus": session.status,
        "chainStatus": chain.status
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
    
    session = await Session.find_one({"chat_id": chat.chat_id})
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")
    
    # Get associated chain
    chain = await Chain.find_one({"session_ids": session.session_id})
    if not chain:
        raise HTTPException(status_code=404, detail="Associated chain not found")
    
    session.status = SessionStatus.ACTIVE
    await session.save()
    
    bot_response = "Good Morning. First Question?"
    try:
        data = {
            "session_id": session.session_id,
            "chain_id": chain.chain_id,
            "employee_id": chat.user_id,
            "context": chain.context  # Send context only during initiation
        }
        print('try sending llm backend a request')
        response = requests.post(f"{llm_add}/start_session", json=data)
        print('response from llm backend recieved', response)
        response_data = response.json()
        bot_response = response_data["message"]
            
    except Exception as e:
        print('exception occured ram', e)
        raise HTTPException(500, detail=str(e))
        
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
        "sessionStatus": session.status,
        "chainStatus": chain.status
    }

@router.post("/update-chain-context")
async def update_chain_context(request: ChainContextUpdateRequest):
    """
    Update chain context after a session ends.
    Called by LLM backend.
    """
    chain = await Chain.get_by_id(request.chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    
    # Update chain context
    await chain.update_context(request.current_context)
    
    return {"message": "Chain context updated successfully"}

@router.post("/complete-chain")
async def complete_chain(request: ChainCompletionRequest):
    """
    Mark a chain as completed.
    Called by LLM backend when it's satisfied with the conversation.
    """
    chain = await Chain.get_by_id(request.chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    
    if chain.status != ChainStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Chain is not active")

    await chain.complete_chain()
    return {"message": "Chain completed successfully"}

@router.post("/escalate-chain")
async def escalate_chain(request: ChainCompletionRequest):
    """
    Mark a chain as escalated to HR.
    Called by LLM backend when it detects need for HR intervention.
    """
    chain = await Chain.get_by_id(request.chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    
    if chain.status != ChainStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Chain is not active")

    await chain.escalate_chain()
    return {"message": "Chain escalated to HR"}

@router.get("/history/{chat_id}", response_model=List[ChatSummary])
async def get_chat_history(
    chat_id: str,
    employee: dict = Depends(verify_hr)
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
        response = requests.get(f"{llm_add}/chat_history/{chat_id}")
        return response.json()
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@router.post("/end-session", tags=["LLM"])
async def end_session(
    request: EndSessionRequest,
    employee: dict = Depends(verify_employee)
):
    """
    End the current session, update chain context, and create a new session.
    """
    try:
        # Get current chat
        chat = await Chat.get_chat_by_id(request.chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Verify employee owns this chat
        if chat.user_id != employee["employee_id"]:
            raise HTTPException(status_code=403, detail="Not authorized to access this chat")
        
        # Get current session
        session = await Session.find_one({"chat_id": chat.chat_id})
        if not session:
            raise HTTPException(status_code=404, detail="Associated session not found")
        
        # Get associated chain
        chain = await Chain.get_by_id(request.chain_id)
        if not chain:
            raise HTTPException(status_code=404, detail="Chain not found")
        
        # Verify session belongs to chain
        if session.session_id not in chain.session_ids:
            raise HTTPException(status_code=400, detail="Session does not belong to this chain")
        
        # Complete current session
        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.now(datetime.UTC)
        await session.save()
        
        # Get all messages from current session
        current_session_messages = [
            {
                "sender": msg.sender.value,
                "text": msg.text,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in chat.messages
        ]
        
        # Prepare data for LLM backend
        data = {
            "chain_id": chain.chain_id,
            "session_id": session.session_id,
            "current_context": chain.context,
            "current_session_messages": current_session_messages
        }
        
        # Call LLM backend to end session and get updated context
        response = requests.post(f"{llm_add}/end_session", json=data)
        response_data = response.json()
        
        # Update chain context with response from LLM
        updated_context = response_data.get("updated_context")
        if updated_context:
            await chain.update_context(updated_context)
        
        # Create new session for tomorrow
        tomorrow = datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        scheduled_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Create new chat for next session
        new_chat = Chat(user_id=employee["employee_id"])
        await new_chat.save()
        
        # Create new session
        new_session = Session(
            user_id=employee["employee_id"],
            chat_id=new_chat.chat_id,
            scheduled_at=scheduled_time,
            notes=f"Follow-up session for chain {chain.chain_id}"
        )
        await new_session.save()
        
        # Add new session to chain
        await chain.add_session(new_session.session_id)
        
        # Create notification for the employee
        notification = Notification(
            employee_id=employee["employee_id"],
            title="Next Support Session Scheduled",
            description=f"Your next support session has been scheduled for {scheduled_time.strftime('%Y-%m-%d %H:%M')} UTC."
        )
        await notification.save()
        
        return {
            "message": "Session ended successfully",
            "new_session_id": new_session.session_id,
            "scheduled_time": scheduled_time,
            "updated_context": updated_context
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error ending session: {str(e)}"
        )
