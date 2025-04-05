from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any, Set, Optional
from models.chat import Chat, ChatMode, SenderType, SentimentType
from models.session import Session, SessionStatus
from models.chain import Chain, ChainStatus
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
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

class CreateSessionRequest(BaseModel):
    employee_id: str
    chain_id: Optional[str] = None
    context: Optional[str] = None

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
    response_from_llm = ""
    
    try:
        data = {
            "session_id": session.session_id,
            "chain_id": chain.chain_id,
            "message": request.message
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{llm_add}/chatbot/message", json=data, headers=headers)
        response_data = response.json()
        bot_response = response_data["message"]
        response_from_llm = response_data
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

    # Check if complete_the_chain or escalate_the_chain is true in LLM response
    if response_from_llm and isinstance(response_from_llm, dict):
        complete_the_chain = response_from_llm.get("complete_the_chain", False)
        escalate_the_chain = response_from_llm.get("escalate_the_chain", False)
        
        if complete_the_chain:
            await complete_chain(chain.chain_id)
        
        if escalate_the_chain:
            await escalate_chain(chain.chain_id)

    
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
        response = requests.post(f"{llm_add}/chatbot/start_session", json=data)
        print('response from llm backend received', response)
        response_data = response.json()
        bot_response = response_data["message"]
            
    except Exception as e:
        print('exception occurred ram', e)
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

@router.post("/create-session")
async def create_session(request: CreateSessionRequest):
    """
    Create a new session for the employee.
    """
    # find the chain id if provided
    if request.chain_id:
        chain = await Chain.find_one({"chain_id": request.chain_id})
        if not chain:
            raise HTTPException(status_code=404, detail="Chain not found")

        # check if the chain is active, if active create the session in the chain
        if chain.status == ChainStatus.ACTIVE:
            # create a new chat
            chat = Chat(user_id=request.employee_id)
            await chat.save()

            # create a new session
            session = await Session(
                employee_id=request.employee_id,
                chat_id=chat.chat_id,
                status=SessionStatus.PENDING,
            )
            await session.save()

            # update the chain with the new session id
            chain.session_ids.append(session.session_id)
            await chain.save()

            return session
        else:
            raise HTTPException(status_code=400, detail="Chain is not active")









