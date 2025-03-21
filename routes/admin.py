# routes only for admins

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from models.session import Session, SessionStatus
from models.employee import Employee, Role
from models.chat import Chat
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
from passlib.context import CryptContext

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class CreateUserRequest(BaseModel):
    employee_id: str = Field(..., description="Unique identifier for the employee")
    name: str = Field(..., description="Full name of the employee")
    email: EmailStr = Field(..., description="Employee email address")
    password: str = Field(..., min_length=8, description="Employee password")
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


async def verify_admin(token: str = Depends(JWTBearer())):
    """Verify that the user is an admin."""
    payload = decode_jwt(token)
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
    hashed_password = pwd_context.hash(user_data.password)

    # Create new employee
    new_employee = Employee(
        employee_id=user_data.employee_id,
        name=user_data.name,
        email=user_data.email,
        password=hashed_password,
        role=user_data.role,
        manager_id=user_data.manager_id
    )

    try:
        await new_employee.insert()
        return {
            "message": "User created successfully",
            "employee_id": new_employee.employee_id,
            "email": new_employee.email,
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


@router.get("/sessions", response_model=List[SessionResponse], tags=["Admin"])
async def get_all_sessions(admin: dict = Depends(verify_admin)):
    """
    Get all sessions in the system.
    Only administrators can access this endpoint.
    Returns a list of all sessions with their details.
    """
    try:
        # Get all sessions
        sessions = await Session.get_all()
        
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
    


