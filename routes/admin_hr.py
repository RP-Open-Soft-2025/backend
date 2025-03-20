# routes common to admin and hr

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel, Field
from models.employee import Employee, Role
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt
import datetime

router = APIRouter()


class BlockUserRequest(BaseModel):
    employee_id: str = Field(..., description="ID of the employee to block/unblock")
    reason: Optional[str] = Field(default=None, description="Reason for blocking the user")


async def verify_admin_or_hr(token: str = Depends(JWTBearer())):
    """Verify that the user is either an admin or HR."""
    payload = decode_jwt(token)
    if not payload or payload.get("role") not in ["admin", "hr"]:
        raise HTTPException(
            status_code=403,
            detail="Only administrators and HR can access this endpoint"
        )
    return payload


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

    try:
        await employee.save()
        return {
            "message": f"Employee {block_data.employee_id} blocked successfully",
            "blocked_at": employee.blocked_at,
            "blocked_by": employee.blocked_by,
            "reason": block_data.reason
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