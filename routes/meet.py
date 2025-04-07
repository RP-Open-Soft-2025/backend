from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
from models.employee import Employee, Role
from models.meet import Meet, MeetStatus
from utils.verify_hr import verify_hr
from utils.verify_employee import verify_employee
router = APIRouter()

class ScheduleMeetRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="Employee ID of the HR who is organizing the meeting")
    with_user_id: str = Field(..., description="Employee ID of the user to meet with")
    scheduled_date: str = Field(..., description="Date of the meeting (YYYY-MM-DD)")
    scheduled_time: str = Field(..., description="Time of the meeting (HH:MM)")
    duration_minutes: int = Field(..., ge=15, le=480, description="Duration in minutes")
    location: Optional[str] = Field(default=None, description="Physical location (if in-person)")
    notes: Optional[str] = Field(default=None, description="Additional notes about the meeting")
    meeting_link: Optional[str] = Field(default=None, description="Link to the virtual meeting")

@router.post("/schedule", tags=["Meetings"])
async def schedule_meeting(
    meeting_data: ScheduleMeetRequest,
    hr: Employee = Depends(verify_hr)
):
    """
    Schedule a meeting with a user as an admin.
    Only Admin / HR can access this endpoint.
    """

    hr_employee = None
    if(hr.role == Role.ADMIN):
        # check if the user_id is a valid employee
        hr_employee = await Employee.get_by_id(meeting_data.user_id)
        if not hr_employee:
            raise HTTPException(
                status_code=404,
                detail=f"User with ID {meeting_data.user_id} not found"
            )
    else:
        meeting_data.with_user_id = hr.employee_id
        hr_employee = hr

    # Check if the with_user_id is a valid employee
    employee = await Employee.get_by_id(meeting_data.with_user_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"User with ID {meeting_data.with_user_id} not found"
        )

    # Parse the datetime
    try:
        scheduled_datetime = datetime.strptime(
            f"{meeting_data.scheduled_date} {meeting_data.scheduled_time}", 
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=timezone.utc)
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
    
    # Create the meeting
    new_meeting = Meet(
        user_id=hr_employee.employee_id,
        with_user_id=meeting_data.with_user_id,
        scheduled_at=scheduled_datetime,
        duration_minutes=meeting_data.duration_minutes,
        status=MeetStatus.SCHEDULED,
        meeting_link=meeting_data.meeting_link if meeting_data.meeting_link else hr_employee.meeting_link,
        location=meeting_data.location,
        notes=meeting_data.notes
    )
    
    try:
        await new_meeting.create()
        return new_meeting
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error scheduling meeting: {str(e)}"
        )

@router.get("/meetings-to-organize", tags=["Meetings"])
async def get_meetings_to_organize(user: Employee = Depends(verify_hr)):
    """
    Get all meetings to organize for the authenticated user.
    """
    try:
        employee_id = user.employee_id
        
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
async def get_meetings_to_attend(user: Employee = Depends(verify_employee)):
    """
    Get all meetings where the authenticated user is a participant.
    """
    try:
        employee_id = user.employee_id
        
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