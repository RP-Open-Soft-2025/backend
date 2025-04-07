# routes only for admins

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import timezone, datetime, timedelta
from pydantic import BaseModel, EmailStr, Field
from models.session import Session, SessionStatus
from models.employee import Employee, Role
from models.meet import Meet, MeetStatus
from models.chain import Chain, ChainStatus
from passlib.context import CryptContext
import random
from utils.utils import send_new_employee_email
import logging
from config.config import Settings
from utils.verify_admin import verify_admin
from utils.verify_hr import verify_hr
from utils.chain_creation import create_chain

import requests

router = APIRouter()
llm_add = Settings().LLM_ADDR
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)

class CreateUserRequest(BaseModel):
    employee_id: str = Field(..., description="Unique identifier for the employee")
    name: str = Field(..., description="Full name of the employee")
    email: EmailStr = Field(..., description="Employee email address")
    role: Role = Field(..., description="User role in the system")
    manager_id: Optional[str] = Field(default=None, description="ID of the employee's manager")
    meeting_link: Optional[str] = Field(default="", description="Meeting link for HR users")

class DeleteUserRequest(BaseModel):
    employee_id: str = Field(..., description="ID of the employee to delete")
    reason: Optional[str] = Field(default=None, description="Reason for deleting the user")

class SessionResponse(BaseModel):
    session_id: str
    employee_id: str
    chat_id: str
    status: str
    scheduled_at: datetime

class ReassignHrRequest(BaseModel):
    newHrId: str = Field(..., description="ID of the new HR to assign")

class ChainResponse(BaseModel):
    chain_id: str
    employee_id: str
    session_ids: List[str]
    sessions: Optional[List[SessionResponse]] = None
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

class MeetResponse(BaseModel):
    meet_id: str
    user_id: str
    with_user_id: str
    scheduled_at: datetime
    duration_minutes: int
    status: MeetStatus
    meeting_link: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None

class EscalatedChainResponse(BaseModel):
    chain_id: str
    session_ids: List[str]
    meet: Optional[MeetResponse] = None
    employee_id: str
    escalation_reason: str
    escalated_at: datetime

# add an endpoint that returns, just the number of total employees, active employees, total admins, totals hrs, total employees, total sessions, completed sessions, active sessions, pendign sessions, total meetings
@router.get("/stats", tags=["Admin Only"])
async def get_system_stats(admin: Employee = Depends(verify_admin)):
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

@router.get("/missing/{role}", tags=["Admin Only"])
async def get_missing_users(role: Role, admin: Employee = Depends(verify_admin)):
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

@router.post("/create-user", tags=["Admin Only"])
async def create_user(
    user_data: CreateUserRequest,
    admin: Employee = Depends(verify_admin)
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
        meeting_link=user_data.meeting_link if user_data.role == Role.HR else "",
        last_ping=datetime.now(timezone.utc)
    )
    
    try:
        await new_employee.insert()
        await send_new_employee_email(user_data.email, user_data.employee_id, new_password)
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

@router.delete("/delete-user", tags=["Admin Only"])
async def delete_user(
    delete_data: DeleteUserRequest,
    admin: Employee = Depends(verify_admin)
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

@router.patch("/reassign-hr/{userId}", tags=["Admin Only"])
async def reassign_hr(
    userId: str,
    reassign_data: ReassignHrRequest,
    admin: Employee = Depends(verify_admin)
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

@router.get("/list-hr", tags=["Admin Only"])
async def list_hr(admin: Employee = Depends(verify_admin)):
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
        user_dict = user_det.model_dump(exclude={'password'})
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
    Only Admin / HR personnel can access this endpoint.
    """
    if hr.role != Role.HR:
        raise HTTPException(status_code=403, detail="Only Admin / HR personnel can access this endpoint")
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

@router.get("/meets" , tags=["HR"])
async def get_meets(hr: Employee = Depends(verify_hr)):
    """
    Get a list of all meets with their details.
    Only Admin / HR personnel can access this endpoint.
    """
    try:
        # Get all meets for a given HR
        if hr.role == Role.HR:
            # Find meets where HR is either the organizer or the participant
            meets = await Meet.find({
                "$or": [
                    {"user_id": hr.employee_id},
                    {"with_user_id": hr.employee_id}
                ]
            }).to_list()
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
                # "meeting_link": meet.meeting_link,
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

@router.post("/chains/create", response_model=ChainResponse, tags=["HR"])
async def create_chains(
    request: CreateChainRequest,
    hr: Employee = Depends(verify_hr)
):
    """
    Create a new chain for an employee and schedule their first session.
    Only Admin / HR personnel can access this endpoint.
    """
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
        
        chain = await create_chain(request)
        return chain
        
    except Exception as e:        
        raise HTTPException(
            status_code=500,
            detail=f"Error creating chain: {str(e)}"
        )

@router.get("/escalated-chains", response_model=List[EscalatedChainResponse], tags=["HR"])
async def get_escalated_chains(hr: Employee = Depends(verify_hr)):
    """
    Get all escalated chains in the system.
    For Admin: Returns all escalated chains
    For HR: Returns only escalated chains of employees under them
    """
    try:
        if hr.role == Role.HR:
            employees = await Employee.get_employees_by_manager(hr.employee_id)
            employee_ids = [emp.employee_id for emp in employees]
            chains = await Chain.find({"employee_id": {"$in": employee_ids},
                                       "status": ChainStatus.ESCALATED}).to_list()
        else:
            chains = await Chain.find({"status": ChainStatus.ESCALATED}).to_list()

        result = []
        for chain in chains:
            chain_dict = chain.model_dump()
            if chain.meet_id:
                meet = await Meet.find_one({"meet_id": chain.meet_id})
                print(meet)
                if meet:
                    chain_dict["meet"] = meet
            result.append(chain_dict)

        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving escalated chains: {str(e)}"
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
        
        result = []
        for chain in chains[1:2]:
            chain_dict = chain.model_dump()
            sessions = await Session.find({"session_id": {"$in": chain.session_ids}}).to_list()
            session_responses = []
            
            for session in sessions:
                session_data = session.model_dump()
                # Map user_id to employee_id to match SessionResponse model
                session_data["employee_id"] = session_data.pop("user_id")
                session_responses.append(session_data)
                
            chain_dict["sessions"] = session_responses
            result.append(chain_dict)
            
        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving employee chains: {str(e)}"
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
        
        await chain.escalate_chain(reason=f"Chain escalated by HR {hr.employee_id}")
        return {"message": "Chain escalated to HR"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error escalating chain: {str(e)}"
        )