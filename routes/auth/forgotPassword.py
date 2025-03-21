import uuid
from fastapi import APIRouter, Body, HTTPException
from models.employee import Employee
from schemas.user import ForgotPasswordRequest, ForgotPasswordResponse
from utils.utils import send_email

router = APIRouter()

reset_tokens = {}

@router.post("/")
async def forgot_password(forgot_password_request: ForgotPasswordRequest = Body(...)):
    user_exists = await Employee.find_one(Employee.email == forgot_password_request.email)
    if user_exists:
        reset_token = str(uuid.uuid4())
        reset_tokens[reset_token] = user_exists.email
        
        # print("Current reset tokens:", reset_tokens)  # ✅ Debug: Verify token storage

        reset_link = f"http://127.0.0.1:8086/auth/reset-password/{reset_token}"
        await send_email(user_exists.email, reset_link)
        
        return ForgotPasswordResponse(message="Password reset link sent to your email.")
    
    raise HTTPException(status_code=404, detail="User not found")
