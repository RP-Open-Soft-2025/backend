# routes only for admins

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import timezone, datetime, timedelta
from pydantic import BaseModel, EmailStr, Field
from models.session import Session, SessionStatus
from models.employee import Employee, Role
from models.chat import Chat
from models.meet import Meet
from models.chain import Chain, ChainStatus
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
from passlib.context import CryptContext
from models.notification import Notification, NotificationStatus
import random
from utils.utils import send_new_employee_email
import logging
from config.config import Settings


import requests

router = APIRouter()
llm_add = Settings().LLM_ADDR
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)

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
    scheduled_at: datetime = Field(..., description="When the session is scheduled for")
    notes: Optional[str] = Field(default=None, description="Any additional notes about the session")

class SessionResponse(BaseModel):
    session_id: str
    employee_id: str
    chat_id: str
    status: str
    scheduled_at: datetime

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
    created_at: datetime
    status: NotificationStatus

class ChainResponse(BaseModel):
    chain_id: str
    employee_id: str
    session_ids: List[str]
    status: ChainStatus
    context: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    notes: Optional[str] = None

class CreateChainRequest(BaseModel):
    employee_id: str = Field(..., description="ID of the employee to create chain for")
    notes: Optional[str] = Field(default=None, description="Any additional notes about the chain")
    scheduled_time: Optional[datetime] = Field(
        default=None,
        description="When to schedule the first session. Defaults to tomorrow at 10 AM."
    )

class BlockUserRequest(BaseModel):
    employee_id: str = Field(..., description="ID of the employee to block/unblock")
    reason: Optional[str] = Field(default=None, description="Reason for blocking the user")

async def verify_admin(token: str = Depends(JWTBearer())):
    """Verify that the user is an admin."""
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    payload = decode_jwt(token)
    admin_user = await Employee.find_one({"employee_id": payload["employee_id"], "role": Role.ADMIN})
    
    if not admin_user:
        raise HTTPException(status_code=403, detail="Only administrators can access this endpoint")
    
    return admin_user

async def verify_hr(token: str = Depends(JWTBearer())):
    """Verify that the user is an HR."""
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    payload = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": payload["employee_id"], "role": {"$in": [Role.ADMIN, Role.HR]}})
    
    if not hr_user:
        raise HTTPException(status_code=403, detail="Only Admin / HR personnel can access this endpoint")
    
    return hr_user

# add an endpoint that returns, just the number of total employees, active employees, total admins, totals hrs, total employees, total sessions, completed sessions, active sessions, pendign sessions, total meetings
@router.get("/stats", tags=["Admin"])
async def get_system_stats(admin: dict = Depends(verify_admin)):
    """
    Get system-wide statistics including counts of employees, sessions, and meetings.
    Only administrators can access this endpoint.
    """
    try:
        # Employee stats

        total_employees = len(await Employee.find().to_list())
        active_employees = len(await Employee.find({"is_active": True}).to_list())
        total_admins = len(await Employee.find({"role": Role.ADMIN}).to_list())
        total_hrs = len(await Employee.find({"role": Role.HR}).to_list())

        # Session stats
        total_sessions = len(await Session.find().to_list())
        completed_sessions = len(await Session.find({"status": SessionStatus.COMPLETED}).to_list())
        active_sessions = len(await Session.find({"status": SessionStatus.ACTIVE}).to_list())
        pending_sessions = len(await Session.find({"status": SessionStatus.PENDING}).to_list())

        # Meeting stats
        total_meetings = len(await Meet.find().to_list())

        return {
            "employee_stats": {
                "total_employees": total_employees,
                "active_employees": active_employees,
                "total_admins": total_admins,
                "total_hrs": total_hrs
            },
            "session_stats": {
                "total_sessions": total_sessions,
                "completed_sessions": completed_sessions,
                "active_sessions": active_sessions,
                "pending_sessions": pending_sessions
            },
            "meeting_stats": {
                "total_meetings": total_meetings
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching system statistics: {str(e)}"
        )

@router.get("/missing/{role}", tags=["Admin"])
async def get_missing_users(role: Role, admin: dict = Depends(verify_admin)):
    """
        Returns missing employees based on role.
        Only administrators can access this endpoint.

        Role filtering:
        - 'employee' → IDs in range EMP0001 - EMP0999
        - 'hr'       → IDs in range EMP1001 - EMP1999
    """
    try:
        # Define ID ranges
        if role == Role.EMPLOYEE:
            all_possible_ids = {f"EMP{i:04d}" for i in range(1, 1000)}
        elif role == Role.HR:
            all_possible_ids = {f"EMP{i:04d}" for i in range(1001, 2000)}
        else:
            raise HTTPException(status_code=400, detail="Invalid role")

        # Get existing employee IDs from database
        existing_employees = await Employee.find_all()
        existing_ids = {emp.employee_id for emp in existing_employees}

        # Find missing IDs
        missing_ids = list(all_possible_ids - existing_ids)

        return {"missing_employee_ids": missing_ids}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching missing employees: {str(e)}"
        )

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
        if not manager or manager.role != Role.HR:
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
        manager_id=user_data.manager_id,
        last_ping=datetime.now(timezone.utc)
    )
    
    try:
        await new_employee.insert()
        send_new_employee_email(user_data.email, user_data.employee_id, new_password)
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
    if employee.employee_id == admin.employee_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account"
        )

    try:
        # Delete the employee
        await employee.delete()
        return {
            "message": f"Employee {delete_data.employee_id} deleted successfully",
            "deleted_by": admin.employee_id,
            "reason": delete_data.reason
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting user: {str(e)}"
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
            assigned_users = await Employee.get_employees_by_manager(hr.employee_id)
            
            total_vibe_score = 0
            valid_employees = 0
            for user in assigned_users:
                if (hasattr(user, 'company_data') and 
                    user.company_data and 
                    hasattr(user.company_data, 'vibemeter') and 
                    user.company_data.vibemeter and 
                    len(user.company_data.vibemeter) > 0):
                    total_vibe_score += user.company_data.vibemeter[-1].Vibe_Score
                    valid_employees += 1
            avg_vibe_score_for_employees = total_vibe_score / valid_employees if valid_employees > 0 else 0
            
            hr_data = {
                "hrId": hr.employee_id,
                "name": hr.name,
                "currentAssignedUsersCount": len(assigned_users),
                "avgVibeScore": avg_vibe_score_for_employees
            }
            hrs.append(hr_data)
        
        return {"hrs": hrs}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching HR list: {str(e)}"
        )

@router.get("/list-users", tags=["HR"])
async def list_users(hr: Employee = Depends(verify_hr)):
    """
    Get a list of all users with their session data.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        if hr.role == Role.HR:
            employees = await Employee.get_employees_by_manager(hr.employee_id)
        else: # Get all employees
            employees = await Employee.find_all()
        
        # Format the response
        users = []
        for employee in employees:
            try:
                # Create user data with proper error handling
                user_data = {
                    "userId": getattr(employee, 'employee_id', ''),
                    "name": getattr(employee, 'name', ''),
                    "email": getattr(employee, 'email', ''),
                    "role": getattr(employee, 'role', ''),
                    "status": "active" if not getattr(employee, 'is_blocked', False) else "blocked",
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

@router.post("/block-user", tags=["HR"])
async def block_user(
    block_data: BlockUserRequest,
    hr: Employee = Depends(verify_hr)
):
    """
    Block a user from accessing the system.
    Admins can block any user, HR can only block users assigned to them.
    """
    # Get the employee to block
    employee = await Employee.get_by_id(block_data.employee_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {block_data.employee_id} not found"
        )
    
    if hr.role == Role.HR and employee.manager_id != hr.employee_id:
        raise HTTPException(
            status_code=403,
            detail="You can only block employees assigned to you"
        )

    # Check if already blocked
    if employee.is_blocked:
        raise HTTPException(
            status_code=400,
            detail=f"Employee {block_data.employee_id} is already blocked"
        )

    # Block the employee
    employee.is_blocked = True
    employee.blocked_at = datetime.now(timezone.utc)
    employee.blocked_by = hr.employee_id
    employee.blocked_reason = block_data.reason

    try:
        await employee.save()
        return {
            "message": f"Employee {block_data.employee_id} blocked successfully",
            "blocked_at": employee.blocked_at,
            "blocked_by": employee.blocked_by,
            "reason": employee.blocked_reason
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error blocking user: {str(e)}"
        )

@router.post("/unblock-user", tags=["HR"])
async def unblock_user(
    block_data: BlockUserRequest,
    hr: Employee = Depends(verify_hr)
):
    """
    Unblock a user from accessing the system.
    Admins can unblock any user, HR can only unblock users assigned to them.
    """

    # Get the employee to unblock
    employee = await Employee.get_by_id(block_data.employee_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {block_data.employee_id} not found"
        )

    if hr.role == Role.HR and employee.manager_id != hr.employee_id:
        raise HTTPException(
            status_code=403,
            detail="You can only unblock employees assigned to you"
        )

    # Check if already unblocked
    if not employee.is_blocked:
        raise HTTPException(
            status_code=400,
            detail=f"Employee {block_data.employee_id} is not blocked"
        )

    # Unblock the employee
    employee.is_blocked = False
    employee.blocked_at = None
    employee.blocked_by = None

    try:
        await employee.save()
        return {
            "message": f"Employee {block_data.employee_id} unblocked successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error unblocking user: {str(e)}"
        )

@router.get('/user-det/{userid}', tags=["HR"])
async def get_user(userid: str, hr: Employee = Depends(verify_hr)):
    """
    Get details of a specific user.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        user_det = await Employee.get_by_id(userid)
        if not user_det:
            raise HTTPException(
                status_code=404,
                detail=f"User with ID {userid} not found"
            )
        
        if hr.role == Role.HR and user_det.manager_id != hr.employee_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this user"
            )
        
        # Convert to dict and exclude sensitive information
        user_dict = user_det.dict(exclude={'password'})
        return user_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user details: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching user details: {str(e)}"
        )

class UpdateMeetingLinkRequest(BaseModel):
    meeting_link: str = Field(..., description="HR's meeting link for virtual meetings")

@router.patch("/update-meeting-link", tags=["HR"])
async def update_meeting_link(
    request: UpdateMeetingLinkRequest,
    hr: Employee = Depends(verify_hr)
):
    """
    Update the HR's meeting link that will be used for virtual meetings.
    Only HR personnel can access this endpoint.
    """
    try:
        # Update meeting link
        hr.meeting_link = request.meeting_link
        await hr.save()
        
        return {
            "message": "Meeting link updated successfully",
            "meeting_link": hr.meeting_link
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating meeting link: {str(e)}"
        )

@router.post("/session/{user_id}", tags=["HR"])
async def create_session(
    user_id: str,
    session_data: CreateSessionRequest,
    hr: Employee = Depends(verify_hr)
):
    """
    Create a new session for an employee.
    Only Admin / HR personnel can access this endpoint.
    """
    # Verify the employee exists
    employee = await Employee.get_by_id(user_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {user_id} not found"
        )
    
    # Verify if the employee is assigned to this HR
    if hr.role == Role.HR and employee.manager_id != hr.employee_id:
        raise HTTPException(status_code=403, detail="Not authorized to create session for this employee")
    
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
        "message": "Session has created successfully",
        "chat_id": chat.chat_id,
        "session_id": session.session_id,
    }

@router.get("/sessions/pending", response_model=List[SessionResponse], tags=["HR"])
async def get_all_active_sessions(hr: Employee = Depends(verify_hr)):
    """
    Get all pending sessions in the system or for a given HR.
    Only Admin / HR personnel can access this endpoint.
    Returns a list of all pending sessions with their details.
    """
    try:
        # Get all pending sessions for a given HR
        if hr.role == Role.HR:
            employees = await Employee.get_employees_by_manager(hr.employee_id)
            employee_ids = [emp.employee_id for emp in employees]
            sessions = await Session.find({"user_id": {"$in": employee_ids}, "status": SessionStatus.PENDING}).to_list()
        else: # Get all pending sessions
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
    
@router.get("/sessions/completed", response_model=List[SessionResponse], tags=["HR"])
async def get_all_active_sessions(hr: Employee = Depends(verify_hr)):
    """
    Get all completed sessions in the system or for a given HR.
    Only Admin / HR personnel can access this endpoint.
    Returns a list of all completed sessions with their details.
    """
    try:
        # Get all completed sessions for a given HR
        if hr.role == Role.HR:
            employees = await Employee.get_employees_by_manager(hr.employee_id)
            employee_ids = [emp.employee_id for emp in employees]
            sessions = await Session.find({"user_id": {"$in": employee_ids}, "status": SessionStatus.COMPLETED}).to_list()
        else: # Get all sessions
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

@router.get("/sessions/active", response_model=List[SessionResponse], tags=["HR"])
async def get_all_active_sessions(hr: Employee = Depends(verify_hr)):
    """
    Get all active sessions in the system or for a given HR.
    Only Admin / HR personnel can access this endpoint.
    Returns a list of all active sessions with their details.
    """
    try:
        # Get all active sessions for a given HR
        if hr.role == Role.HR:
            employees = await Employee.get_employees_by_manager(hr.employee_id)
            employee_ids = [emp.employee_id for emp in employees]
            sessions = await Session.find({"user_id": {"$in": employee_ids}, "status": SessionStatus.ACTIVE}).to_list()
        else: # Get all active sessions
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

@router.get("/sessions", response_model=List[SessionResponse], tags=["HR"])
async def get_active_and_pending_sessions(hr: Employee = Depends(verify_hr)):
    """
    Get all active and pending sessions in the system.
    Only Admin / HR personnel can access this endpoint.
    Returns a list of all active and pending sessions with their details.
    """
    try:
        # Get all active and pending sessions for a given HR
        if hr.role == Role.HR:
            employees = await Employee.get_employees_by_manager(hr.employee_id)
            employee_ids = [emp.employee_id for emp in employees]
            sessions = await Session.find(
                {"user_id": {"$in": employee_ids}, "status": {"$in": [SessionStatus.ACTIVE, SessionStatus.PENDING]}}
            ).to_list()
        else: # Get all active and pending sessions
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

class SessionStatusUpdate(BaseModel):
    session_id: str = Field(..., description="ID of the session to update")
    notes: Optional[str] = Field(default=None, description="Optional notes about the status change")

@router.patch("/session/complete", tags=["HR"])
async def complete_session(
    session_data: SessionStatusUpdate,
    hr: Employee = Depends(verify_hr)
):
    """
    Mark a session as completed.
    Only administrators and HR can access this endpoint.
    HR can only complete sessions for employees assigned to them.
    """
    # Get the session
    session = await Session.get(session_data.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session with ID {session_data.session_id} not found"
        )
    
    employee = await Employee.get_by_id(session.user_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {session.user_id} not found"
        )

    if hr.role == Role.HR and employee.manager_id != hr.employee_id:
        raise HTTPException(
            status_code=403,
            detail="You can only complete sessions for employees assigned to you"
        )

    # Check if session is already completed
    if session.status == SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_data.session_id} is already completed"
        )

    # Check if session is active
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_data.session_id} must be active to be completed"
        )

    try:
        # Update session status
        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc)
        session.notes = session_data.notes
        await session.save()

        return {
            "message": f"Session {session_data.session_id} marked as completed",
            "completed_at": session.completed_at,
            "notes": session.notes
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error completing session: {str(e)}"
        )

@router.patch("/session/activate", tags=["HR"])
async def activate_session(
    session_data: SessionStatusUpdate,
    hr: Employee = Depends(verify_hr)
):
    """
    Mark a session as active.
    Only administrators and HR can access this endpoint.
    HR can only activate sessions for employees assigned to them.
    """

    # Get the session
    session = await Session.get(session_data.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session with ID {session_data.session_id} not found"
        )

    employee = await Employee.get_by_id(session.user_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {session.user_id} not found"
        )
    
    if hr.role == Role.HR and employee.manager_id != hr.employee_id:
        raise HTTPException(
            status_code=403,
            detail="You can only activate sessions for employees assigned to you"
        )
    # Check if session is already active
    if session.status == SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_data.session_id} is already active"
        )

    # Check if session is completed
    if session.status == SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_data.session_id} cannot be reactivated after completion"
        )

    try:
        # Update session status
        session.status = SessionStatus.ACTIVE
        session.notes = session_data.notes
        await session.save()

        return {
            "message": f"Session {session_data.session_id} marked as active",
            "notes": session.notes
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error activating session: {str(e)}"
        )

@router.get("/meets" , tags=["HR"])
async def get_meets(hr: Employee = Depends(verify_hr)):
    """
    Get a list of all meets with their details.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        # Get all meets for a given HR
        if hr.role == Role.HR:
            meets = await Meet.get_meets_with_user(hr.employee_id)
        else: # Get all meets
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

@router.get("/chains", response_model=List[ChainResponse], tags=["HR"])
async def get_all_chains(hr: Employee = Depends(verify_hr)):
    """
    Get all chains in the system.
    Only Admin / HR personnel can access this endpoint.
    Returns a list of all chains of all employees under the HR.
    """
    try:
        if hr.role == Role.HR:
            employees = await Employee.get_employees_by_manager(hr.employee_id)
            employee_ids = [emp.employee_id for emp in employees]
            chains = await Chain.find({"employee_id": {"$in": employee_ids}}).to_list()
        else:
            chains = await Chain.find().to_list()
        return chains
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving chains: {str(e)}"
        )

@router.get("/chains/{chain_id}", response_model=ChainResponse, tags=["HR"])
async def get_chain_details(chain_id: str, hr: Employee = Depends(verify_hr)):
    """
    Get details of a specific chain.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        chain = await Chain.get_by_id(chain_id)
        if not chain:
            raise HTTPException(
                status_code=404,
                detail=f"Chain with ID {chain_id} not found"
            )
        
        employee = await Employee.get_by_id(chain.employee_id)
        if not employee:
            raise HTTPException(
                status_code=404,
                detail=f"Employee with ID {chain.employee_id} not found"
            )

        if hr.role == Role.HR and employee.manager_id != hr.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only access chains for employees assigned to you"
            )
        
        return chain
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving chain details: {str(e)}"
        )

@router.get("/chains/employee/{employee_id}", response_model=List[ChainResponse], tags=["HR"])
async def get_employee_chains(employee_id: str, hr: Employee = Depends(verify_hr)):
    """
    Get all chains for a specific employee.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        employee = await Employee.get_by_id(employee_id)
        if not employee:
            raise HTTPException(
                status_code=404,
                detail=f"Employee with ID {employee_id} not found"
            )
        
        if hr.role == Role.HR and employee.manager_id != hr.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only access chains for employees assigned to you"
            )
        
        chains = await Chain.find({"employee_id": employee_id}).to_list()
        return chains
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving employee chains: {str(e)}"
        )

@router.post("/chains/{chain_id}/complete", tags=["HR"])
async def complete_chain(chain_id: str, hr: Employee = Depends(verify_hr)):
    """
    Mark a chain as completed.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        chain = await Chain.get_by_id(chain_id)
        if not chain:
            raise HTTPException(
                status_code=404,
                detail=f"Chain with ID {chain_id} not found"
            )
        
        employee = await Employee.get_by_id(chain.employee_id)
        if not employee:
            raise HTTPException(
                status_code=404,
                detail=f"Employee with ID {chain.employee_id} not found"
            )
        
        if hr.role == Role.HR and employee.manager_id != hr.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only complete chains for employees assigned to you"
            )

        if chain.status != ChainStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail="Chain is not active"
            )
        
        await chain.complete_chain()
        return {"message": "Chain completed successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error completing chain: {str(e)}"
        )

@router.post("/chains/{chain_id}/escalate", tags=["HR"])
async def escalate_chain(chain_id: str, hr: Employee = Depends(verify_hr)):
    """
    Mark a chain as escalated to HR.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        chain = await Chain.get_by_id(chain_id)
        if not chain:
            raise HTTPException(
                status_code=404,
                detail=f"Chain with ID {chain_id} not found"
            )
        
        employee = await Employee.get_by_id(chain.employee_id)
        if not employee:
            raise HTTPException(
                status_code=404,
                detail=f"Employee with ID {chain.employee_id} not found"
            )
        
        if hr.role == Role.HR and employee.manager_id != hr.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only escalate chains for employees assigned to you"
            )
        
        if chain.status != ChainStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail="Chain is not active"
            )
        
        await chain.escalate_chain()
        return {"message": "Chain escalated to HR"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error escalating chain: {str(e)}"
        )

@router.post("/chains/{chain_id}/cancel", tags=["HR"])
async def cancel_chain(chain_id: str, hr: Employee = Depends(verify_hr)):
    """
    Cancel a chain.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        chain = await Chain.get_by_id(chain_id)
        if not chain:
            raise HTTPException(
                status_code=404,
                detail=f"Chain with ID {chain_id} not found"
            )
        
        employee = await Employee.get_by_id(chain.employee_id)
        if not employee:
            raise HTTPException(
                status_code=404,
                detail=f"Employee with ID {chain.employee_id} not found"
            )
        
        if hr.role == Role.HR and employee.manager_id != hr.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only cancel chains for employees assigned to you"
            )
        
        if chain.status not in [ChainStatus.ACTIVE, ChainStatus.ESCALATED]:
            raise HTTPException(
                status_code=400,
                detail="Chain cannot be cancelled in its current state"
            )
        
        await chain.cancel_chain()
        return {"message": "Chain cancelled successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error cancelling chain: {str(e)}"
        )

@router.post("/chains/create", response_model=ChainResponse, tags=["HR"])
async def create_chain(
    request: CreateChainRequest,
    hr: Employee = Depends(verify_hr)
):
    """
    Create a new chain for an employee and schedule their first session.
    Only Admin / HR personnel can access this endpoint.
    """
    chain = ""
    session = ""
    chat = ""
    notification = ""
    try:
        # Verify the employee exists
        employee = await Employee.get_by_id(request.employee_id)
        if not employee:
            raise HTTPException(
                status_code=404,
                detail=f"Employee with ID {request.employee_id} not found"
            )
        
        if hr.role == Role.HR and employee.manager_id != hr.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You can only create chains for employees assigned to you"
            )
        
        # Check if employee already has an active chain
        active_chain = await Chain.find_one({
            "employee_id": request.employee_id,
            "status": ChainStatus.ACTIVE
        })
        if active_chain:
            raise HTTPException(
                status_code=400,
                detail="Employee already has an active chain"
            )
        
        # Set default scheduled time to tomorrow at 10 AM if not provided
        if not request.scheduled_time:
            tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
            request.scheduled_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Create a new chat for the session
        chat = Chat(user_id=request.employee_id)
        await chat.save()
        
        # Create a new session
        session = Session(
            user_id=request.employee_id,
            chat_id=chat.chat_id,
            scheduled_at=request.scheduled_time,
            notes=request.notes
        )
        await session.save()
        
        # Create a new chain
        chain = Chain(
            employee_id=request.employee_id,
            session_ids=[session.session_id],
            status=ChainStatus.ACTIVE,
            notes=request.notes
        )
        await chain.save()
        
        # Create notification for the employee
        notification = Notification(
            employee_id=request.employee_id,
            title="New Support Session Scheduled",
            description=f"A new support session has been scheduled for you on {request.scheduled_time.strftime('%Y-%m-%d %H:%M')} UTC."
        )
        await notification.save()

        report_data = {
            "employee_data": {
                "employee_id": employee.employee_id,
                "company_data": employee.company_data.model_dump(mode='json')
            }
        }

        # call the api, LLM_ADDR/report/analyze
        response = requests.post(f"{llm_add}/report/analyze", json=report_data)
        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate employee report"
            )
        
        report = response.json()
        print(report)

        return chain
        
    except Exception as e:
        # delete the chain if it is created
        if chain:
            await chain.delete()
        # delete the session if it is created
        if session:
            await session.delete()
        # delete the chat if it is created
        if chat:
            await chat.delete()
        # delete the notification if it is created
        if notification:
            await notification.delete()
        
        raise HTTPException(
            status_code=500,
            detail=f"Error creating chain: {str(e)}"
        )

@router.post("/notification/create", response_model=NotificationResponse, tags=["HR"])
async def create_notification(
    notification: NotificationCreate,
    hr: Employee = Depends(verify_hr)
):
    """
    Create a new notification for an employee 
    Only Admin / HR personnel can access this endpoint.
    """
    # Verify employee exists
    employee = await Employee.get_by_id(notification.employee_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )
    
    if hr.role == Role.HR and employee.manager_id != hr.employee_id:
        raise HTTPException(
            status_code=403,
            detail="You can only create notifications for employees assigned to you"
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
