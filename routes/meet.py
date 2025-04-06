from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
from models.employee import Employee, Role
from models.meet import Meet, MeetStatus
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt

router = APIRouter()

class ScheduleMeetRequest(BaseModel):
    user_id: str = Field(..., description="Employee ID of the user to meet with")
    scheduled_date: str = Field(..., description="Date of the meeting (YYYY-MM-DD)")
    scheduled_time: str = Field(..., description="Time of the meeting (HH:MM)")
    duration_minutes: int = Field(..., ge=15, le=480, description="Duration in minutes")
    location: Optional[str] = Field(default=None, description="Physical location (if in-person)")
    notes: Optional[str] = Field(default=None, description="Additional notes about the meeting")

async def verify_admin(token: str = Depends(JWTBearer())):
    """Verify that the user is an admin."""
    payload = decode_jwt(token)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access this endpoint"
        )
    return payload

@router.post("/admin-schedule", tags=["Meetings"])
async def admin_schedule_meeting(
    meeting_data: ScheduleMeetRequest,
    admin: dict = Depends(verify_admin)
):
    """
    Schedule a meeting with a user as an admin.
    Only administrators can access this endpoint.
    """
    # Check if the user exists
    user = await Employee.get_by_id(meeting_data.user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with ID {meeting_data.user_id} not found"
        )
    
    # Parse the datetime
    try:
        scheduled_datetime = datetime.strptime(
            f"{meeting_data.scheduled_date} {meeting_data.scheduled_time}", 
            "%Y-%m-%d %H:%M"
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date or time format. Use YYYY-MM-DD for date and HH:MM for time."
        )
    
    # Check if the meeting is in the past
    if scheduled_datetime < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="Cannot schedule meetings in the past"
        )
    
    # Generate Zoom meeting link
    # meeting_details = await generate_meet_link()
    # if not meeting_details:
    #     raise HTTPException(
    #         status_code=500,
    #         detail="Failed to generate meeting link"
    #     )
    
    # Create the meeting
    new_meeting = Meet(
        user_id=admin["employee_id"],
        with_user_id=meeting_data.user_id,
        scheduled_at=scheduled_datetime,
        duration_minutes=meeting_data.duration_minutes,
        status=MeetStatus.SCHEDULED,
        meeting_link=meeting_data.meeting_link,
        location=meeting_data.location,
        notes=meeting_data.notes
    )
    
    try:
        await new_meeting.create()
        return {
            "message": "Meeting scheduled successfully",
            "meet_id": new_meeting.meet_id,
            "with_user": {
                "id": user.employee_id,
                "name": user.name
            },
            "meeting_link": new_meeting.meeting_link,
            "meeting_id": new_meeting.meeting_id,
            "meeting_password": new_meeting.meeting_password,
            "scheduled_at": new_meeting.scheduled_at.isoformat(),
            "duration_minutes": new_meeting.duration_minutes,
            "notes": new_meeting.notes
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error scheduling meeting: {str(e)}"
        )

async def verify_hr(token: str = Depends(JWTBearer())):
    """Verify that the user is an HR."""
    payload = decode_jwt(token)
    if not payload or payload.get("role") != "hr":
        raise HTTPException(
            status_code=403,
            detail="Only HR personnel can access this endpoint"
        )
    return payload

@router.post("/hr-schedule", tags=["Meetings"])
async def hr_schedule_meeting(
    meeting_data: ScheduleMeetRequest,
    hr: dict = Depends(verify_hr)
):
    """
    Schedule a meeting with a user as an HR.
    Only HR personnel can access this endpoint.
    """
    # Check if the user exists
    user = await Employee.get_by_id(meeting_data.user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with ID {meeting_data.user_id} not found"
        )
    
    # Verify that the user is assigned to this HR
    if user.manager_id != hr["employee_id"]:
        raise HTTPException(
            status_code=403,
            detail=f"User {meeting_data.user_id} is not assigned to you as HR"
        )
    
    # Parse the datetime
    try:
        scheduled_datetime = datetime.strptime(
            f"{meeting_data.scheduled_date} {meeting_data.scheduled_time}", 
            "%Y-%m-%d %H:%M"
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date or time format. Use YYYY-MM-DD for date and HH:MM for time."
        )
    
    # Check if the meeting is in the past
    if scheduled_datetime < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="Cannot schedule meetings in the past"
        )
    
    # Get HR's meeting link
    hr_user = await Employee.get_by_id(hr["employee_id"])
    if not hr_user or not hr_user.meeting_link:
        raise HTTPException(
            status_code=400,
            detail="Please set up your meeting link first before scheduling meetings"
        )
    
    # Create the meeting
    new_meeting = Meet(
        user_id=hr["employee_id"],
        with_user_id=meeting_data.user_id,
        scheduled_at=scheduled_datetime,
        duration_minutes=meeting_data.duration_minutes,
        status=MeetStatus.SCHEDULED,
        meeting_link=hr_user.meeting_link,
        location=meeting_data.location,
        notes=meeting_data.notes
    )
    
    try:
        await new_meeting.create()
        return {
            "message": "Meeting scheduled successfully",
            "meet_id": new_meeting.meet_id,
            "with_user": {
                "id": user.employee_id,
                "name": user.name
            },
            "meeting_link": new_meeting.meeting_link,
            "scheduled_at": new_meeting.scheduled_at.isoformat(),
            "duration_minutes": new_meeting.duration_minutes,
            "notes": new_meeting.notes
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error scheduling meeting: {str(e)}"
        )

async def verify_user(token: str = Depends(JWTBearer())):
    """Verify any authenticated user."""
    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials"
        )
    return payload

@router.get("/organized-meetings", tags=["Meetings"])
async def get_organized_meetings(user: dict = Depends(verify_user)):
    """
    Get all meetings organized by the authenticated user.
    """
    try:
        employee_id = user["employee_id"]
        
        # Get meetings where user is the organizer
        organized_meetings = await Meet.find({"user_id": employee_id}).to_list()
        
        # Sort by scheduled time
        organized_meetings.sort(key=lambda x: x.scheduled_at)
        
        # Format the response
        formatted_meetings = []
        for meeting in organized_meetings:
            # Get information about the participant
            participant = await Employee.get_by_id(meeting.with_user_id)
            
            meeting_data = {
                "meetId": meeting.meet_id,
                "participant": {
                    "id": participant.employee_id,
                    "name": participant.name,
                    "role": participant.role
                },
                "scheduledAt": meeting.scheduled_at.isoformat(),
                "duration": meeting.duration_minutes,
                "status": meeting.status,
                "location": meeting.location,
                "meetingLink": meeting.meeting_link,
                "notes": meeting.notes
            }
            formatted_meetings.append(meeting_data)
        
        return {"organizedMeetings": formatted_meetings}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching organized meetings: {str(e)}"
        )

@router.get("/meetings-to-attend", tags=["Meetings"])
async def get_meetings_to_attend(user: dict = Depends(verify_user)):
    """
    Get all meetings where the authenticated user is a participant.
    """
    try:
        employee_id = user["employee_id"]
        
        # Get meetings where user is the participant
        participating_meetings = await Meet.find({"with_user_id": employee_id}).to_list()
        
        # Sort by scheduled time
        participating_meetings.sort(key=lambda x: x.scheduled_at)
        
        # Format the response
        formatted_meetings = []
        for meeting in participating_meetings:
            # Get information about the organizer
            organizer = await Employee.get_by_id(meeting.user_id)
            
            meeting_data = {
                "meetId": meeting.meet_id,
                "organizer": {
                    "id": organizer.employee_id,
                    "name": organizer.name,
                    "role": organizer.role
                },
                "scheduledAt": meeting.scheduled_at.isoformat(),
                "duration": meeting.duration_minutes,
                "status": meeting.status,
                "location": meeting.location,
                "meetingLink": meeting.meeting_link,
                "notes": meeting.notes
            }
            formatted_meetings.append(meeting_data)
        
        return {"meetingsToAttend": formatted_meetings}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching meetings to attend: {str(e)}"
        )