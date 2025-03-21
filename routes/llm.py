from fastapi import APIRouter, Body, HTTPException, Depends
from pydantic import BaseModel
from models.session import Session
from models.employee import Employee, Role
from models.meet import Meet, MeetStatus
from models.chat import Chat
from datetime import timedelta,datetime
from typing import Optional
import random
from fastapi.security import OAuth2PasswordBearer, HTTPAuthorizationCredentials
from auth.jwt_handler import decode_jwt

router = APIRouter()
security = OAuth2PasswordBearer(tokenUrl="token")


class EscalateChatRequest(BaseModel):
    chatId: str
    detectedSentiment: str
    reason: str
    timeDuartion: Optional[int]

@router.patch("/chat/escalate")
async def escalate_chat(request: EscalateChatRequest = Body(...)):
    chat_det = await Session.find_one({"chat_id": request.chatId})
    if not chat_det:
        raise HTTPException(404, "Given chatId doesn't exist")
    
    user = await Employee.find_one({"employee_id": chat_det.user_id})
    if not user:
        raise HTTPException(404, "Given employee doesn't exist")
    
    manager_id = user.manager_id
    existing_meetings = await Meet.find({"with_user_id": manager_id}).to_list()
    
    current_time = datetime.now()
    earliest_start_time = current_time
    duration_minutes = 480 if not request.timeDuartion else request.timeDuartion

    # Sort existing meetings by start time
    sorted_meetings = sorted(existing_meetings, key=lambda m: m.scheduled_at)

    # If no meetings, use the initial proposed time
    if not sorted_meetings:
        proposed_time = earliest_start_time
    else:
        # Initialize variables for finding gaps
        proposed_time = None
        
        # Check if there's space before the first meeting
        first_meeting_start = sorted_meetings[0].scheduled_at
        if (first_meeting_start - earliest_start_time).total_seconds() / 60 >= duration_minutes:
            proposed_time = earliest_start_time
        
        # If no space before first meeting, check for gaps between meetings
        if proposed_time is None:
            for i in range(len(sorted_meetings) - 1):
                current_meeting_end = sorted_meetings[i].scheduled_at + timedelta(minutes=sorted_meetings[i].duration_minutes)
                next_meeting_start = sorted_meetings[i + 1].scheduled_at
                
                # If current meeting ends after our earliest possible start time
                # and there's enough gap before the next meeting
                if current_meeting_end >= earliest_start_time and \
                (next_meeting_start - current_meeting_end).total_seconds() / 60 >= duration_minutes:
                    proposed_time = max(current_meeting_end, earliest_start_time)
                    break
        
        # If still no time found, schedule after the last meeting
        if proposed_time is None:
            last_meeting = sorted_meetings[-1]
            last_meeting_end = last_meeting.scheduled_at + timedelta(minutes=last_meeting.duration_minutes)
            proposed_time = max(last_meeting_end, earliest_start_time)
    
    new_meet = Meet(
        user_id=user.employee_id,
        with_user_id=user.manager_id,
        scheduled_at=proposed_time,
        duration_minutes=duration_minutes,
        status=MeetStatus.SCHEDULED
    )
    
    await new_meet.save()
    
    return {"message": "Chat flagged for HR review due to detected distress."}

@router.get("/chat/history/{chatId}")
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