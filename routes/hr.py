# routes only for hr
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from typing import List, Optional
from datetime import datetime
from models.chat import Chat, SenderType
from auth.jwt_bearer import JWTBearer
from pydantic import BaseModel

router = APIRouter()
token_listener = JWTBearer()

# Request/Response Models
class ChatResponse(BaseModel):
    chat_id: str
    user_id: str
    status: str
    last_message: Optional[str]
    messages: List[dict]

class ChatMessagesResponse(BaseModel):
    chat_id: str
    messages: List[dict]

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}

    async def connect(self, websocket: WebSocket, chat_id: str):
        await websocket.accept()
        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = []
        self.active_connections[chat_id].append(websocket)

    def disconnect(self, websocket: WebSocket, chat_id: str):
        if chat_id in self.active_connections:
            self.active_connections[chat_id].remove(websocket)
            if not self.active_connections[chat_id]:
                del self.active_connections[chat_id]

    async def broadcast_to_chat(self, chat_id: str, message: dict):
        if chat_id in self.active_connections:
            for connection in self.active_connections[chat_id]:
                await connection.send_json(message)

manager = ConnectionManager()

# Routes
@router.get("/chats", response_model=List[ChatResponse], tags=["HR"])
async def get_assigned_chats(
    hr_id: str,
    token: str = Depends(token_listener)
):
    """Get all chat sessions assigned to the HR"""
    try:
        chats = await Chat.find({"status": "active"}).to_list()
        return [
            ChatResponse(
                chat_id=chat.chat_id,
                user_id=chat.user_id,
                status=chat.status,
                last_message=chat.last_message,
                messages=[
                    {
                        "sender": msg.sender_type,
                        "text": msg.text,
                        "timestamp": msg.timestamp.isoformat()
                    }
                    for msg in chat.messages
                ]
            )
            for chat in chats
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/{chat_id}", response_model=ChatMessagesResponse, tags=["HR"])
async def get_chat_messages(
    chat_id: str,
    hr_id: str,
    token: str = Depends(token_listener)
):
    """Get messages for a specific chat"""
    try:
        chat = await Chat.get(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        return ChatMessagesResponse(
            chat_id=chat.chat_id,
            messages=[
                {
                    "sender": msg.sender_type,
                    "text": msg.text,
                    "timestamp": msg.timestamp.isoformat()
                }
                for msg in chat.messages
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/{chat_id}/message", tags=["HR"])
async def send_hr_message(
    chat_id: str,
    message: str,
    hr_id: str,
    token: str = Depends(token_listener)
):
    """Send a message as HR"""
    try:
        chat = await Chat.get(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        await chat.add_message(sender_type=SenderType.HR, text=message)
        
        # Broadcast new message
        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "new_message",
                "sender": SenderType.HR,
                "text": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        return {"message": "Message sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/chat/{chat_id}/archive", tags=["HR"])
async def archive_chat(
    chat_id: str,
    hr_id: str,
    token: str = Depends(token_listener)
):
    """Archive a chat session"""
    try:
        chat = await Chat.get(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        await chat.archive_chat()
        
        # Broadcast archive event
        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "chat_archived",
                "message": "Chat has been archived"
            }
        )
        
        return {"message": "Chat archived successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint for real-time updates
@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: str):
    await manager.connect(websocket, chat_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)