from fastapi import APIRouter, Depends, HTTPException, status, Header, Body
from typing import Dict, Any
from auth.jwt_handler import decode_jwt
from models.chat import Chat, Message, SenderType
from datetime import timedelta,datetime
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer, HTTPAuthorizationCredentials
from models.session import Session
from models.employee import Employee, Role
from models.meet import Meet, MeetStatus
from typing import Optional

router = APIRouter()
security = OAuth2PasswordBearer(tokenUrl="token")
class EscalateChatRequest(BaseModel):
    chatId: str
    detectedSentiment: str
    reason: str
    timeDuartion: Optional[int]

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


@router.patch("/escalate")
async def escalate_chat(request: EscalateChatRequest = Body(...)):
    chat_det = await Session.find_one({"chat_id": request.chatId})
    if not chat_det:
        raise HTTPException(404, "Given chatId doesn't exist")
    
    user = await Employee.find_one({"employee_id": chat_det.user_id})
    if not user:
        raise HTTPException(404, "Given employee doesn't exist")
    
    manager_id = user.manager_id
    existing_meetings = await Meet.find({"with_user_id": manager_id}).to_list()
    duration_minutes = 480 if not request.timeDuartion else request.timeDuartion

    proposed_time = assignTimeCalendar(existing_meetings, duration_minutes)
    new_meet = Meet(
        user_id=user.employee_id,
        with_user_id=user.manager_id,
        scheduled_at=proposed_time,
        duration_minutes=duration_minutes,
        status=MeetStatus.SCHEDULED
    )
    
    await new_meet.save()
    
    return {"message": "Chat flagged for HR review due to detected distress."}

@router.get("/history/{chatId}")
async def get_chat_history(chatId: str, token: HTTPAuthorizationCredentials = Depends(security)):
    # Check if token is valid
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorised")
    
    # Decode JWT and get employee details
    claims_jwt = decode_jwt(token)
    user = await Employee.find_one({"employee_id": claims_jwt["employee_id"]})
    
    # Check authorization
    if not user:
        raise HTTPException(401, "User not found")
    
    if not (user.role == Role.HR or user.role == Role.ADMIN):
        raise HTTPException(401, "User is not allowed to perform this action")
    
    # Get chat details
    chat = await Chat.find_one({"chat_id": chatId})
    
    if not chat:
        raise HTTPException(404, "Chat with the given id is not found")
    
    # Return the chat with its messages
    return chat

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