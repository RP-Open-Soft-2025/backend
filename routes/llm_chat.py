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
from utils.utils import send_new_session_email, send_escalation_mail
from utils.chain_creation import analyze_employee_report
from utils.verify_employee import verify_employee

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
    employee: Employee = Depends(verify_employee)
):
    """
    Send a message to the LLM bot and get a response.
    """
    # Get or create chat
    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Verify employee owns this chat
    if chat.user_id != employee.employee_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    
    # Get associated session
    session = await Session.find_one({"chat_id": chat.chat_id})
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")

    # check if the session is active
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Session is not active")
    
    # Get associated chain
    chain = await Chain.find_one({"session_ids": session.session_id})
    if not chain:
        raise HTTPException(status_code=404, detail="Associated chain not found")

    # check if the chain is active
    if chain.status != ChainStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Chain is not active")
    
    if(chat.messages[-1].sender_type == SenderType.EMPLOYEE):
        raise HTTPException(status_code=400, detail="Please wait for the bot to respond before sending a message")

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
            await chain.complete_chain()
        
        if escalate_the_chain:
            await chain.escalate_chain(reason=f"Chain escalated for the employee {employee.employee_id} by Chatbot")

    # count the number of messages in the chat from the employee
    employee_messages_length = len([msg for msg in chat.messages if msg.sender_type != SenderType.BOT])
    
    return {
        "message": bot_response,
        "chatId": chat.chat_id,
        "sessionStatus": session.status,
        "chainStatus": chain.status,
        "can_end_chat": employee_messages_length >= 10,
        "ended": complete_the_chain or escalate_the_chain
    }

@router.patch("/initiate-chat")
async def initiate_chat(request: ChatStatusRequest, employee: Employee = Depends(verify_employee)):
    """
    Initiate a chat between bot and employee
    """
    chat = await Chat.get_chat_by_id(request.chatId)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if chat.user_id != employee.employee_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat")
    
    # Update created_at to current time
    chat.created_at = datetime.now().isoformat()
    
    session = await Session.find_one({"chat_id": chat.chat_id})
    if not session:
        raise HTTPException(status_code=404, detail="Associated session not found")
    
    if session.status != SessionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Session is not pending")
    
    # Convert scheduled_at to UTC if it's not already timezone-aware
    scheduled_time = session.scheduled_at
    if scheduled_time.tzinfo is None:
        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
    
    if scheduled_time < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Please start the session at the scheduled time")

    # Get associated chain
    chain = await Chain.find_one({"session_ids": session.session_id})
    if not chain:
        raise HTTPException(status_code=404, detail="Associated chain not found")
    
    
    bot_response = "Good Morning. First Question?"
    try:
        # call the api "/report-exists/"
        report_exists = requests.get(f"{llm_add}/report/report-exists/{chain.chain_id}")
        report_exists = report_exists.json()
        if not report_exists.get("exists"):
            employee = await Employee.find_one({"employee_id": chain.employee_id})
            try: 
                await analyze_employee_report(chain.chain_id, employee)
            except Exception as e:
                raise HTTPException(500, detail=f'exception occurred while analyzing employee report: {e}')
        
        data = {
            "session_id": session.session_id,
            "chain_id": chain.chain_id,
            "employee_id": chat.user_id,
            "context": chain.context  # Send context only during initiation
        }
        print('try sending llm backend a request. Data: ', data)
        response = requests.post(f"{llm_add}/chatbot/start_session", json=data, timeout=300)
        print('response from llm backend received', response)
        response_data = response.json()
        bot_response = response_data["message"]

        session.status = SessionStatus.ACTIVE
        await session.save()
            
    except Exception as e:
        print('exception occurred while initiating chat', e)
        raise HTTPException(500, detail=str(e))
        
    await chat.add_message(SenderType.BOT, bot_response)
    
    # Broadcast status update
    await llm_manager.broadcast_to_chat(request.chatId, {
        "type": "status_update",
        "status": request.status,
        "timestamp": datetime.now().isoformat(),
        "message": bot_response
    })
    
    return {
        "message": bot_response,
        "chatId": chat.chat_id,
        "sessionStatus": session.status,
        "chainStatus": chain.status
    }

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

            # get the employee details
            user = await Employee.find_one({"employee_id": request.employee_id})

            # send a notification to the employee
            await send_new_session_email(
                to_email=user.email,
                sub=f"""Dear {user.name},

A counseling session has been scheduled for you based on our employee wellness program.

Session Details:
- Date: {datetime.now().strftime('%Y-%m-%d')}
- Time: {datetime.now().strftime('%H:%M')} timezone.utc
- Deadline: {(datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')}
- Session ID: {session.session_id}
- Chain ID: {chain.chain_id}

Please make sure to attend the session at the scheduled time. If you need to reschedule, please contact your HR representative.

Best regards,
HR Team"""
            )

            return session
        else:
            raise HTTPException(status_code=400, detail="Chain is not active")

class EndSessionRequest(BaseModel):
    chat_id: str = Field(..., description="ID of the current chat")

@router.post("/end-session")
async def end_session(
    request: EndSessionRequest,
    employee: Employee = Depends(verify_employee)
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
        if chat.user_id != employee.employee_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this chat")
        
        # Get current session
        session = await Session.find_one({"chat_id": chat.chat_id})
        if not session:
            raise HTTPException(status_code=404, detail="Associated session not found")
        
        # Get associated chain
        chain = await Chain.find_one({"session_ids": {"$in": [session.session_id]}})
        if not chain:
            raise HTTPException(status_code=404, detail="Chain not found")

        # count the number of messages in the current session from the employee
        employee_messages_length = len([msg for msg in chat.messages if msg.sender_type != SenderType.BOT])

        # if the number of employee messages is greater than 10, end the chat
        if employee_messages_length < 10:
            raise HTTPException(status_code=400, detail="Cannot end the chat as the employee has not sent more than 10 messages")

        # Get all messages from current session
        current_session_messages = [
            {
                "sender": msg.sender_type,
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
        response = requests.post(f"{llm_add}/chatbot/end_session", json=data)
        response_data = response.json()
        
        # Update chain context with response from LLM
        updated_context = response_data.get("updated_context")
        if updated_context:
            await chain.update_context(updated_context)
        else:
            raise HTTPException(status_code=400, detail="No updated context received from LLM")
        
        # Complete current session
        await session.complete_session()
        
        # Create new session for tomorrow
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        scheduled_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Create new chat for next session
        new_chat = Chat(user_id=employee.employee_id)
        await new_chat.save()
        
        # Create new session
        new_session = Session(
            user_id=employee.employee_id,
            chat_id=new_chat.chat_id,
            scheduled_at=scheduled_time,
            notes=f"Follow-up session for chain {chain.chain_id}"
        )
        await new_session.save()
        
        # Add new session to chain
        await chain.add_session(new_session.session_id)
        
        # Create notification for the employee
        notification = Notification(
            employee_id=employee.employee_id,
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
