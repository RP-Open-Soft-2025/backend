# routes only for admins

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
import datetime
from pydantic import BaseModel, EmailStr, Field
from models.session import Session, SessionStatus
from models.employee import Employee, Role
from models.chat import Chat
from models.meet import Meet
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
from passlib.context import CryptContext
from models.notification import Notification, NotificationStatus
import random
from utils.utils import send_new_employee_email

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class CreateUserRequest(BaseModel):
    employee_id: str = Field(..., description="Unique identifier for the employee")
    name: str = Field(..., description="Full name of the employee")
    email: EmailStr = Field(..., description="Employee email address")
    # password: str = Field(..., min_length=8, description="Employee password")
    role: Role = Field(..., description="User role in the system")
    manager_id: Optional[str] = Field(default=None, description="ID of the employee's manager")

class DeleteUserRequest(BaseModel):
    employee_id: str = Field(..., description="ID of the employee to delete")
    reason: Optional[str] = Field(default=None, description="Reason for deleting the user")

class CreateSessionRequest(BaseModel):
    scheduled_at: datetime.datetime = Field(..., description="When the session is scheduled for")
    notes: Optional[str] = Field(default=None, description="Any additional notes about the session")

class SessionResponse(BaseModel):
    session_id: str
    employee_id: str
    chat_id: str
    status: str
    scheduled_at: datetime.datetime

class ReassignHrRequest(BaseModel):
    newHrId: str = Field(..., description="ID of the new HR to assign")

class NotificationCreate(BaseModel):
    employee_id: str
    title: str
    description: str

class NotificationResponse(BaseModel):
    id: str
    employee_id: str
    title: str
    description: str
    created_at: datetime.datetime
    status: NotificationStatus

async def verify_admin(token: str = Depends(JWTBearer())):
    """Verify that the user is an admin."""
    payload = decode_jwt(token)
    # print(payload)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access this endpoint"
        )
    return payload


@router.post("/create-user", tags=["Admin"])
async def create_user(
    user_data: CreateUserRequest,
    admin: dict = Depends(verify_admin)
):
    """
    Create a new user with the specified role.
    Only administrators can access this endpoint.
    """
    # Check if employee_id already exists
    existing_employee = await Employee.get_by_id(user_data.employee_id)
    if existing_employee:
        raise HTTPException(
            status_code=400,
            detail=f"Employee with ID {user_data.employee_id} already exists"
        )

    # Check if email already exists
    existing_email = await Employee.get_by_email(user_data.email)
    if existing_email:
        raise HTTPException(
            status_code=400,
            detail=f"Email {user_data.email} is already registered"
        )

    # If manager_id is provided, verify it exists
    if user_data.manager_id:
        manager = await Employee.get_by_id(user_data.manager_id)
        if not manager:
            raise HTTPException(
                status_code=400,
                detail=f"Manager with ID {user_data.manager_id} does not exist"
            )
    
    # Hash the password
    random_number=random.randint(10000,99999)
    new_password=f"password{random_number}"
    hashed_password = pwd_context.hash(new_password)
    


    # Create new employee
    new_employee = Employee(
        employee_id=user_data.employee_id,
        name=user_data.name,
        email=user_data.email,
        password=hashed_password,
        role=user_data.role,
        manager_id=user_data.manager_id
    )
    send_new_employee_email(user_data.email, user_data.employee_id, new_password)
    
    try:
        await new_employee.insert()
        return {
            "message": "User created successfully",
            "employee_id": new_employee.employee_id,
            "email": new_employee.email,
            # "password":new_employee.password,
            "role": new_employee.role
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating user: {str(e)}"
        )

@router.delete("/delete-user", tags=["Admin"])
async def delete_user(
    delete_data: DeleteUserRequest,
    admin: dict = Depends(verify_admin)
):
    """
    Delete a user from the system.
    Only administrators can access this endpoint.
    This operation is permanent and cannot be undone.
    """
    # Get the employee to delete
    employee = await Employee.get_by_id(delete_data.employee_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {delete_data.employee_id} not found"
        )

    # Prevent deleting another admin
    if employee.role == Role.ADMIN:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete another administrator"
        )

    # Prevent deleting the current admin
    if employee.employee_id == admin["employee_id"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account"
        )

    try:
        # Delete the employee
        await employee.delete()
        return {
            "message": f"Employee {delete_data.employee_id} deleted successfully",
            "deleted_by": admin["employee_id"],
            "reason": delete_data.reason
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting user: {str(e)}"
        )

@router.post("/session/{user_id}", tags=["Admin"])
async def create_session(
    user_id: str,
    session_data: CreateSessionRequest,
    admin: dict = Depends(verify_admin)
):
    """
    Create a new session for an employee.
    Only administrators can access this endpoint.
    """
    # Verify the employee exists
    employee = await Employee.get_by_id(user_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {user_id} not found"
        )
    
    # check if there is an active or pending session for the employee
    active_session = await Session.find_one({"user_id": user_id, "status": SessionStatus.ACTIVE})
    if active_session:
        raise HTTPException(
            status_code=400,
            detail="Employee already has an active session"
        )

    pending_session = await Session.find_one({"user_id": user_id, "status": SessionStatus.PENDING})
    if pending_session:
        raise HTTPException(
            status_code=400,
            detail="Employee already has a pending session"
        )
    
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
        "message": "Chat has created successfully",
        "chat_id": chat.chat_id,
        "session_id": session.session_id
    }

@router.get("/sessions/pending", response_model=List[SessionResponse], tags=["Admin"])
async def get_all_active_sessions(admin: dict = Depends(verify_admin)):
    """
    Get all sessions in the system.
    Only administrators can access this endpoint.
    Returns a list of all sessions with their details.
    """
    try:
        # Get all sessions
        sessions = await Session.find({"status": SessionStatus.PENDING}).to_list()
        
        # Convert sessions to response format
        session_responses = [
            SessionResponse(
                session_id=session.session_id,
                employee_id=session.user_id,
                chat_id=session.chat_id,
                status=session.status.value,
                scheduled_at=session.scheduled_at
            )
            for session in sessions
        ]
        
        return session_responses
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching sessions: {str(e)}"
        )
    
@router.get("/sessions/completed", response_model=List[SessionResponse], tags=["Admin"])
async def get_all_active_sessions(admin: dict = Depends(verify_admin)):
    """
    Get all sessions in the system.
    Only administrators can access this endpoint.
    Returns a list of all sessions with their details.
    """
    try:
        # Get all sessions
        sessions = await Session.find({"status": SessionStatus.COMPLETED}).to_list()
        
        # Convert sessions to response format
        session_responses = [
            SessionResponse(
                session_id=session.session_id,
                employee_id=session.user_id,
                chat_id=session.chat_id,
                status=session.status.value,
                scheduled_at=session.scheduled_at
            )
            for session in sessions
        ]
        
        return session_responses
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching sessions: {str(e)}"
        )
    
@router.get("/sessions/active", response_model=List[SessionResponse], tags=["Admin"])
async def get_all_active_sessions(admin: dict = Depends(verify_admin)):
    """
    Get all sessions in the system.
    Only administrators can access this endpoint.
    Returns a list of all sessions with their details.
    """
    try:
        # Get all sessions
        sessions = await Session.find({"status": SessionStatus.ACTIVE}).to_list()
        
        # Convert sessions to response format
        session_responses = [
            SessionResponse(
                session_id=session.session_id,
                employee_id=session.user_id,
                chat_id=session.chat_id,
                status=session.status.value,
                scheduled_at=session.scheduled_at
            )
            for session in sessions
        ]
        
        return session_responses
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching sessions: {str(e)}"
        )


@router.get("/sessions", response_model=List[SessionResponse], tags=["Admin"])
async def get_active_and_pending_sessions(admin: dict = Depends(verify_admin)):
    """
    Get all active and pending sessions in the system.
    Only administrators can access this endpoint.
    Returns a list of all active and pending sessions with their details.
    """
    try:
        # Get all active and pending sessions
        sessions = await Session.find(
            {"status": {"$in": [SessionStatus.ACTIVE, SessionStatus.PENDING]}}
        ).to_list()
        
        # Convert sessions to response format
        session_responses = [
            SessionResponse(
                session_id=session.session_id,
                employee_id=session.user_id,
                chat_id=session.chat_id,
                status=session.status.value,
                scheduled_at=session.scheduled_at
            )
            for session in sessions
        ]
        
        return session_responses
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching sessions: {str(e)}"
        )
 

@router.get("/list-users", tags=["Admin"])
async def list_users(admin: dict = Depends(verify_admin)):
    """
    Get a list of all users with their session data.
    Only administrators can access this endpoint.
    """
    try:
        # Get all employees
        employees = await Employee.find_all()
        
        # Format the response
        users = []
        for employee in employees:
            try:
                # Get the latest vibe meter entry for session data
                latest_vibe = None
                if hasattr(employee, 'company_data') and employee.company_data and hasattr(employee.company_data, 'vibemeter') and employee.company_data.vibemeter:
                    latest_vibe = employee.company_data.vibemeter[-1]
                
                # Create user data with proper error handling
                user_data = {
                    "userId": getattr(employee, 'employee_id', ''),
                    "name": getattr(employee, 'name', ''),
                    "email": getattr(employee, 'email', ''),
                    "role": getattr(employee, 'role', ''),
                    "status": "active" if not getattr(employee, 'is_blocked', False) else "blocked",
                    "sessionData": {
                        "latestVibe": latest_vibe,
                        "moodScores": [
                            {
                                "timestamp": vibe.Response_Date.isoformat(),
                                "Vibe_Score": vibe.Vibe_Score,
                                # "Emotion_Zone": vibe.Emotion_Zone
                            }
                            for vibe in (employee.company_data.vibemeter if hasattr(employee, 'company_data') and employee.company_data and hasattr(employee.company_data, 'vibemeter') else [])
                        ]
                    },
                    "lastPing": employee.last_ping.isoformat()
                }
                users.append(user_data)
            except Exception as e:
                print(f"Error processing employee {getattr(employee, 'employee_id', 'unknown')}: {str(e)}")
                continue
        
        return {"users": users}
    except Exception as e:
        import traceback
        print(f"Error in list_users: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching users: {str(e)}"
        )

@router.patch("/reassign-hr/{userId}", tags=["Admin"])
async def reassign_hr(
    userId: str,
    reassign_data: ReassignHrRequest,
    admin: dict = Depends(verify_admin)
):
    """
    Reassign HR for an existing user.
    Only administrators can access this endpoint.
    """
    # Get the employee to reassign
    employee = await Employee.get_by_id(userId)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {userId} not found"
        )

    # Get the new HR
    new_hr = await Employee.get_by_id(reassign_data.newHrId)
    if not new_hr:
        raise HTTPException(
            status_code=404,
            detail=f"New HR with ID {reassign_data.newHrId} not found"
        )

    # Verify the new HR is actually an HR
    if new_hr.role != Role.HR:
        raise HTTPException(
            status_code=400,
            detail=f"Employee {reassign_data.newHrId} is not an HR personnel"
        )

    try:
        # Update the manager_id
        employee.manager_id = reassign_data.newHrId
        await employee.save()
        
        return {
            "message": "HR reassigned successfully",
            "userId": userId,
            "newHrId": reassign_data.newHrId
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reassigning HR: {str(e)}"
        )

@router.get("/list-hr", tags=["Admin"])
async def list_hr(admin: dict = Depends(verify_admin)):
    """
    Get a list of all HR personnel with their current workload.
    Only administrators can access this endpoint.
    """
    try:
        # Get all HR personnel
        hr_personnel = await Employee.find({"role": Role.HR}).to_list()
        
        # Format the response
        hrs = []
        for hr in hr_personnel:
            # Count assigned users
            assigned_users = await Employee.find({"manager_id": hr.employee_id}).count()
            
            hr_data = {
                "hrId": hr.employee_id,
                "name": hr.name,
                "currentAssignedUsers": assigned_users
            }
            hrs.append(hr_data)
        
        return {"hrs": hrs}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching HR list: {str(e)}"
        )


@router.get("/meets" , tags=["Admin"])
async def get_meets(admin: dict = Depends(verify_admin)):
    """
    Get a list of all meets with their details.
    Only administrators can access this endpoint.
    """
    try:
        # Get all meets
        meets = await Meet.find_all().to_list()

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
        print(f"Error fetching meets: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching meets: {str(e)}"
        )

@router.get('/user-det/{userid}', tags=["Admin"])
async def get_user(userid: str, admin: dict = Depends(verify_admin)):
    try:
        user_det = await Employee.find_one({"employee_id": userid})
        return user_det
    except Exception as e:
        print(f"Error fetching meets: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching meets: {str(e)}"
        )

@router.post("/notification/create", response_model=NotificationResponse)
async def create_notification(
    notification: NotificationCreate,
    admin: dict = Depends(verify_admin)
):
    """
    Create a new notification for an employee (admin only).
    """
    # Verify employee exists
    employee = await Employee.get_by_id(notification.employee_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )
    
    # Create notification
    new_notification = Notification(
        employee_id=notification.employee_id,
        title=notification.title,
        description=notification.description
    )
    await new_notification.save()
    
    return NotificationResponse(
        id=str(new_notification.id),
        employee_id=new_notification.employee_id,
        title=new_notification.title,
        description=new_notification.description,
        created_at=new_notification.created_at,
        status=new_notification.status
    )