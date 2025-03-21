from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Dict, Any
from auth.jwt_handler import decode_jwt
from models.chat import Chat, Message, SenderType

router = APIRouter()

async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials. Bearer token required."
        )
    
    token = authorization.replace("Bearer ", "")
    
    try:
        payload = decode_jwt(token)
        if not payload or "employee_id" not in payload or "role" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token or token expired"
            )
        return {"id": payload["employee_id"], "role": payload["role"]}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Error processing token: {str(e)}"
        )

@router.post("/message")
async def send_message(
    data: Dict[str, Any],
    current_user = Depends(get_current_user)
):
    user_id = current_user["id"]
    
    if "message" not in data or "chatId" not in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chatId and message are required"
        )
    
    user_message = data["message"]
    chat_id = data["chatId"]
    
    try:
        chat = await Chat.get_chat_by_id(chat_id)
        if chat:
            if chat.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to access this chat"
                )
        else:
            chat = Chat(user_id=user_id, id=chat_id)
            await chat.save()
        
        await chat.add_message(sender_type=SenderType.EMPLOYEE, text=user_message)
        
        #we need to implement the logic to get the bot(llm) response
        bot_response = "Thank you for reaching out. I'm here to help. Can you tell me more about what's on your mind?"
        await chat.add_message(sender_type=SenderType.BOT, text=bot_response)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat: {str(e)}"
        )
    
    return {"message": bot_response, "chatId": chat_id}

@router.patch("/status")
async def update_chat_status(
    data: Dict[str, Any],
    current_user = Depends(get_current_user)
):
    if current_user["role"] not in ["admin", "hr"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin and HR can update chat status"
        )
    
    if "chatId" not in data or "status" not in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chatId and status are required"
        )
    # print(f"Fetching chat with ID: {data['chatId']}")
    chat_id = data["chatId"]
    
    status_value = data["status"]
    
    try:
        chat = await Chat.get_chat_by_id(chat_id)
        # print(f"Chat fetched: {chat}")
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )
        
        chat.status = status_value
        await chat.save()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating chat status: {str(e)}"
        )
    
    return {"message": f"Chat status updated to {status_value} mode"}
