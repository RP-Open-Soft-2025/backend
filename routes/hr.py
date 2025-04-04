# routes only for hr
from fastapi import APIRouter, HTTPException, Depends
from auth.jwt_handler import decode_jwt
from auth.jwt_bearer import JWTBearer
from models.session import Session, SessionStatus
from models.employee import Employee, Role
from models.chat import Chat
from models.meet import Meet
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()
# security = OAuth2PasswordBearer(tokenUrl="token")

class CreateSessionRequest(BaseModel):
    scheduled_at: datetime = Field(..., description="When the session is scheduled for")
    notes: Optional[str] = Field(default=None, description="Any additional notes about the session")

class UpdateMeetingLinkRequest(BaseModel):
    meeting_link: str = Field(..., description="HR's meeting link for virtual meetings")

async def verify_hr(token: str = Depends(JWTBearer())):
    """Verify that the user is an HR."""
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    claims_jwt = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": claims_jwt["employee_id"], "role": Role.HR})
    
    if not hr_user:
        raise HTTPException(status_code=403, detail="Only HR personnel can access this endpoint")
    
    return claims_jwt

@router.get("/list-assigned-users", tags=["HR"])
async def list_assigned_users(hr: dict = Depends(verify_hr)):
    """
    Get a list of users assigned to the HR.
    Only HR personnel can access this endpoint.
    """
    try:
        # Get all employees assigned to this HR
        employees = await Employee.find({"manager_id": hr["employee_id"]}).to_list()
        # Format the response
        users = []
        for employee in employees:
            latest_vibe = None
            if hasattr(employee, 'company_data') and hasattr(employee.company_data, 'vibemeter') and employee.company_data.vibemeter:
                latest_vibe = employee.company_data.vibemeter[-1]
            
            # Format mood scores with null checks
            mood_scores = []
            if hasattr(employee, 'company_data') and hasattr(employee.company_data, 'vibemeter'):
                for vibe in employee.company_data.vibemeter:
                    mood_score = {
                        "timestamp": vibe.Response_Date.isoformat() if hasattr(vibe, 'Response_Date') and vibe.Response_Date else None,
                        "Vibe_Score": vibe.Vibe_Score if hasattr(vibe, 'Vibe_Score') else None
                    }
                    mood_scores.append(mood_score)

            user_data = {
                "userId": employee.employee_id,
                "name": employee.name,
                "email": employee.email,
                "status": "active" if not employee.is_blocked else "blocked",
                "latestVibe": latest_vibe,
                "sessionData": {
                    "moodScores": mood_scores
                },
                "lastPing": employee.last_ping.isoformat() if employee.last_ping else None
            }
            users.append(user_data)
        
        return {"users": users}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching assigned users: {str(e)}"
        )

@router.get("/sessions/pending")
async def get_hr_sessions(hr = Depends(verify_hr)):
    hr_user = await Employee.find_one({"employee_id": hr["employee_id"], "role": Role.HR})

    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    # Get all employees managed by this HR
    employees = await Employee.get_employees_by_manager(hr["employee_id"])
    employee_ids = [emp.employee_id for emp in employees]
    
    # Get active sessions for all employees under this HR
    active_sessions = await Session.find({
        "user_id": {"$in": employee_ids},
        "status": SessionStatus.PENDING
    }).to_list()
    
    # Format response
    session_responses = [
        {
            "session_id": session.session_id,
            "employee_id": session.user_id,
            "chat_id": session.chat_id,
            "status": session.status.value,
            "scheduled_at": session.scheduled_at
        }
        for session in active_sessions
    ]
    
    return session_responses

@router.get("/sessions/completed")
async def get_hr_sessions(hr = Depends(verify_hr)):
    hr_user = await Employee.find_one({"employee_id": hr["employee_id"], "role": Role.HR})

    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    # Get all employees managed by this HR
    employees = await Employee.get_employees_by_manager(hr["employee_id"])
    employee_ids = [emp.employee_id for emp in employees]
    
    # Get active sessions for all employees under this HR
    active_sessions = await Session.find({
        "user_id": {"$in": employee_ids},
        "status": SessionStatus.COMPLETED
    }).to_list()
    
    # Format response
    session_responses = [
        {
            "session_id": session.session_id,
            "employee_id": session.user_id,
            "chat_id": session.chat_id,
            "status": session.status.value,
            "scheduled_at": session.scheduled_at
        }
        for session in active_sessions
    ]
    
    return session_responses

@router.get("/sessions/active")
async def get_hr_sessions(hr = Depends(verify_hr)):
    hr_user = await Employee.find_one({"employee_id": hr["employee_id"], "role": Role.HR})

    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    # Get all employees managed by this HR
    employees = await Employee.get_employees_by_manager(hr["employee_id"])
    employee_ids = [emp.employee_id for emp in employees]

    # Get active sessions for all employees under this HR
    active_sessions = await Session.find({
        "user_id": {"$in": employee_ids},
        "status": SessionStatus.ACTIVE
    }).to_list()
    
    # Format response
    session_responses = [
        {
            "session_id": session.session_id,
            "employee_id": session.user_id,
            "chat_id": session.chat_id,
            "status": session.status.value,
            "scheduled_at": session.scheduled_at
        }
        for session in active_sessions
    ]
    
    return session_responses

@router.get("/sessions")
async def get_hr_sessions(hr = Depends(verify_hr)):
    hr_user = await Employee.find_one({"employee_id": hr["employee_id"], "role": Role.HR})

    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    # Get all employees managed by this HR
    employees = await Employee.get_employees_by_manager(hr["employee_id"])
    employee_ids = [emp.employee_id for emp in employees]

    # Get active sessions for all employees under this HR
    active_sessions = await Session.find({
        "user_id": {"$in": employee_ids},
        "status": {"$in": [SessionStatus.ACTIVE, SessionStatus.PENDING]}
    }).to_list()
    
    # Format response
    session_responses = [
        {
            "session_id": session.session_id,
            "employee_id": session.user_id,
            "chat_id": session.chat_id,
            "status": session.status.value,
            "scheduled_at": session.scheduled_at
        }
        for session in active_sessions
    ]
    
    return session_responses

@router.post("/session/{user_id}")
async def create_session_hr(
    user_id: str, 
    session_data: CreateSessionRequest,
    hr = Depends(verify_hr)
):
    hr_user = await Employee.find_one({"employee_id": hr["employee_id"], "role": Role.HR})

    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    emp_user = await Employee.find_one({"employee_id": user_id})
    if not emp_user:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Verify if the employee is assigned to this HR
    if emp_user.manager_id != hr["employee_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to create session for this employee")
    
    # Create a new chat for the session
    chat = Chat(user_id=user_id)
    await chat.save()

    # Create a new session
    session = Session(
        user_id=user_id,
        chat_id=chat.chat_id,
        scheduled_at=session_data.scheduled_at,
        notes=session_data.notes
    )
    await session.save()

    return {
        "message": "Session has created successfully",
        "chat_id": chat.chat_id,
        "session_id": session.session_id,
    }
 

@router.get("/meets")
async def get_hr_meets(hr = Depends(verify_hr)):
    try:
        hr_user = await Employee.find_one({"employee_id": hr["employee_id"], "role": Role.HR})

        if not hr_user:
            raise HTTPException(status_code=403, detail="Error HR not found")

        meets = await Meet.get_meets_with_user(hr["employee_id"])

        meets_list = []
        for meet in meets:
            meet_data = {
                "meet_id": meet.meet_id,
                "user_id": meet.user_id,
                "with_user_id": meet.with_user_id,
                "duration": meet.duration_minutes,
                "status": meet.status,
                "scheduled_at": meet.scheduled_at,
                "meeting_link": meet.meeting_link,
                "location": meet.location,
                "notes": meet.notes,
            }
            meets_list.append(meet_data)
        # Format the response
        return meets_list
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching meets: {str(e)}")

@router.patch("/update-meeting-link", tags=["HR"])
async def update_meeting_link(
    request: UpdateMeetingLinkRequest,
    hr: dict = Depends(verify_hr)
):
    """
    Update the HR's meeting link that will be used for virtual meetings.
    Only HR personnel can access this endpoint.
    """
    try:
        # Get HR user
        hr_user = await Employee.find_one({"employee_id": hr["employee_id"], "role": Role.HR})
        if not hr_user:
            raise HTTPException(status_code=403, detail="Error HR not found")
        
        # Update meeting link
        hr_user.meeting_link = request.meeting_link
        await hr_user.save()
        
        return {
            "message": "Meeting link updated successfully",
            "meeting_link": hr_user.meeting_link
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating meeting link: {str(e)}"
        )


