from fastapi import APIRouter, Body, HTTPException
from passlib.context import CryptContext
from auth.jwt_handler import sign_jwt
from models.employee import Employee
from schemas.user import EmployeeSignIn, ResetPasswordRequest, ForgotPasswordRequest, ForgotPasswordResponse
from utils.utils import send_email
import uuid

router = APIRouter()
hash_helper = CryptContext(schemes=["bcrypt"])
reset_tokens = {}

# Login Route
@router.post("/login")
async def user_login(user_credentials: EmployeeSignIn = Body(...)):
    user_exists = await Employee.find_one(Employee.employee_id == user_credentials.employee_id)
    if not user_exists or not hash_helper.verify(user_credentials.password, user_exists.password):
        raise HTTPException(status_code=403, detail="Incorrect employee ID or password")
    return sign_jwt(user_credentials.employee_id, user_exists.role)

# Forgot Password Route
@router.post("/forgot-password")
async def forgot_password(forgot_password_request: ForgotPasswordRequest = Body(...)):
    user_exists = await Employee.find_one(Employee.email == forgot_password_request.email)
    if not user_exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    reset_token = str(uuid.uuid4())
    reset_tokens[reset_token] = user_exists.email
    reset_link = f"http://127.0.0.1:8080/auth/reset-password/{reset_token}"
    await send_email(user_exists.email, reset_link)
    return ForgotPasswordResponse(message="Password reset link sent to your email.")

# Reset Password Route
@router.post("/reset-password/{reset_token}")
async def reset_password(reset_token: str, request_data: ResetPasswordRequest):
    email = reset_tokens.get(reset_token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    user = await Employee.find_one(Employee.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if hash_helper.verify(request_data.new_password, user.password):
        raise HTTPException(status_code=400, detail="New password cannot be the same as the old password.")
    
    user.password = hash_helper.hash(request_data.new_password)
    await user.save()

    del reset_tokens[reset_token]
    return {"message": "Password reset successful"}
