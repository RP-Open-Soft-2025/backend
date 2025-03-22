# routes common to admin and hr

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel, Field
from models.employee import Employee, Role
from models.session import Session, SessionStatus
# from auth.jwt_bearer import JWTBearer
# from auth.jwt_handler import decode_jwt
from fastapi_jwt_auth import AuthJWT
import datetime

router = APIRouter()


class BlockUserRequest(BaseModel):
    employee_id: str = Field(..., description="ID of the employee to block/unblock")
    reason: Optional[str] = Field(default=None, description="Reason for blocking the user")


async def verify_admin_or_hr(Authorize: AuthJWT = Depends()):
    Authorize.jwt_required()
    claims = Authorize.get_raw_jwt()
    if claims.get("role") not in ["admin", "hr"]:
        raise HTTPException(status_code=403, detail="Only administrators and HR can access this endpoint")
    return claims


async def verify_access_rights(admin_hr_id: str, target_employee_id: str, role: str):
    """Verify that the user has rights to block the target employee."""
    if role == "admin":
        return True
    
    # For HR, check if the target employee is assigned to them
    target_employee = await Employee.get_by_id(target_employee_id)
    if not target_employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {target_employee_id} not found"
        )
    
    # HR can only block employees assigned to them
    if target_employee.manager_id != admin_hr_id:
        raise HTTPException(
            status_code=403,
            detail="You can only block employees assigned to you"
        )
    
    return True


@router.post("/block-user", tags=["Admin-HR"])
async def block_user(
    block_data: BlockUserRequest,
    admin_hr: dict = Depends(verify_admin_or_hr)
):
    """
    Block a user from accessing the system.
    Admins can block any user, HR can only block users assigned to them.
    """
    # Verify access rights
    await verify_access_rights(admin_hr["employee_id"], block_data.employee_id, admin_hr["role"])

    # Get the employee to block
    employee = await Employee.get_by_id(block_data.employee_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {block_data.employee_id} not found"
        )

    # Check if already blocked
    if employee.is_blocked:
        raise HTTPException(
            status_code=400,
            detail=f"Employee {block_data.employee_id} is already blocked"
        )

    # Block the employee
    employee.is_blocked = True
    employee.blocked_at = datetime.datetime.utcnow()
    employee.blocked_by = admin_hr["employee_id"]
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


@router.post("/unblock-user", tags=["Admin-HR"])
async def unblock_user(
    block_data: BlockUserRequest,
    admin_hr: dict = Depends(verify_admin_or_hr)
):
    """
    Unblock a user from accessing the system.
    Admins can unblock any user, HR can only unblock users assigned to them.
    """
    # Verify access rights
    await verify_access_rights(admin_hr["employee_id"], block_data.employee_id, admin_hr["role"])

    # Get the employee to unblock
    employee = await Employee.get_by_id(block_data.employee_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {block_data.employee_id} not found"
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


class SessionStatusUpdate(BaseModel):
    session_id: str = Field(..., description="ID of the session to update")
    notes: Optional[str] = Field(default=None, description="Optional notes about the status change")


async def verify_session_access_rights(admin_hr_id: str, session_id: str, role: str):
    """Verify that the user has rights to update the session status."""
    if role == "admin":
        return True
    
    # Get the session
    session = await Session.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session with ID {session_id} not found"
        )
    
    # Get the employee associated with the session
    employee = await Employee.get_by_id(session.user_id)
    if not employee:
        raise HTTPException(
            status_code=404,
            detail=f"Employee associated with session {session_id} not found"
        )
    
    # HR can only update sessions for employees assigned to them
    if employee.manager_id != admin_hr_id:
        raise HTTPException(
            status_code=403,
            detail="You can only update sessions for employees assigned to you"
        )
    
    return True


@router.patch("/session/complete", tags=["Admin-HR"])
async def complete_session(
    session_data: SessionStatusUpdate,
    admin_hr: dict = Depends(verify_admin_or_hr)
):
    """
    Mark a session as completed.
    Only administrators and HR can access this endpoint.
    HR can only complete sessions for employees assigned to them.
    """
    # Verify access rights
    await verify_session_access_rights(admin_hr["employee_id"], session_data.session_id, admin_hr["role"])

    # Get the session
    session = await Session.get(session_data.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session with ID {session_data.session_id} not found"
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
        session.completed_at = datetime.datetime.utcnow()
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


@router.patch("/session/activate", tags=["Admin-HR"])
async def activate_session(
    session_data: SessionStatusUpdate,
    admin_hr: dict = Depends(verify_admin_or_hr)
):
    """
    Mark a session as active.
    Only administrators and HR can access this endpoint.
    HR can only activate sessions for employees assigned to them.
    """
    # Verify access rights
    await verify_session_access_rights(admin_hr["employee_id"], session_data.session_id, admin_hr["role"])

    # Get the session
    session = await Session.get(session_data.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session with ID {session_data.session_id} not found"
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


@router.patch("/session/pending", tags=["Admin-HR"])
async def mark_session_pending(
    session_data: SessionStatusUpdate,
    admin_hr: dict = Depends(verify_admin_or_hr)
):
    """
    Mark a session as pending.
    Only administrators and HR can access this endpoint.
    HR can only mark sessions as pending for employees assigned to them.
    """
    # Verify access rights
    await verify_session_access_rights(admin_hr["employee_id"], session_data.session_id, admin_hr["role"])

    # Get the session
    session = await Session.get(session_data.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session with ID {session_data.session_id} not found"
        )

    # Check if session is already pending
    if session.status == SessionStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_data.session_id} is already pending"
        )

    # Check if session is completed
    if session.status == SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_data.session_id} cannot be marked as pending after completion"
        )

    try:
        # Update session status
        session.status = SessionStatus.PENDING
        session.notes = session_data.notes
        await session.save()

        return {
            "message": f"Session {session_data.session_id} marked as pending",
            "notes": session.notes
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error marking session as pending: {str(e)}"
        )