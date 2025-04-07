# create sample route to send a test email
from fastapi import APIRouter, HTTPException, Depends
from utils.utils import send_new_session_email
from utils.scheduler import clear_notifications
from models.notification import Notification, create_notification
from models.employee import Employee, Role
from pydantic import BaseModel
from datetime import datetime
from utils.verify_hr import verify_hr
from utils.verify_admin import verify_admin
router = APIRouter()

@router.post("/send-test-email")
async def send_test_email(email: str, admin: Employee = Depends(verify_admin)):
    await send_new_session_email(email, "Test Email Trial")
    return {"message": "Email sent successfully"}

@router.post("/rem-notification")
async def rem_notification(admin: Employee = Depends(verify_admin)):
    try:
        await clear_notifications()
        return {"message": "Notifications cleared successfully"}
    except Exception as e:
        return {"message": f"Error in clearing notifications: {str(e)}"}

class NotificationCreate(BaseModel):
    employee_id: str
    title: str
    description: str

@router.post("/notification/create", response_model=Notification)
async def create_notification_test(
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
    new_notification = await create_notification(
        employee_id=notification.employee_id,
        title=notification.title,
        description=notification.description
    )

    return new_notification