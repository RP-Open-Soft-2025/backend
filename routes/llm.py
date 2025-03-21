from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from models.session import Session
from models.employee import Employee
from models.meet import Meet, MeetStatus
from datetime import timedelta,datetime
from typing import Optional
import random

router = APIRouter()

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
    hours_delay = random.uniform(2, 3)  # Random value between 2-3 hours
    proposed_time = current_time + timedelta(hours=hours_delay)
    duration_minutes = 480 if not request.timeDuartion else request.timeDuartion
    
    for meeting in existing_meetings:
        meeting_start = meeting.scheduled_at
        meeting_end = meeting_start + timedelta(minutes=meeting.duration_minutes)
        
        proposed_end = proposed_time + timedelta(minutes=duration_minutes)
        
        if (meeting_start <= proposed_time < meeting_end) or \
           (meeting_start < proposed_end <= meeting_end) or \
           (proposed_time <= meeting_start and proposed_end >= meeting_end):
            proposed_time = meeting_end
    
    new_meet = Meet(
        user_id=user.employee_id,
        with_user_id=user.manager_id,
        scheduled_at=proposed_time,
        duration_minutes=duration_minutes,
        status=MeetStatus.SCHEDULED
    )
    
    await new_meet.save()
    
    return {"message": "Chat flagged for HR review due to detected distress."}