from fastapi import APIRouter, Body, HTTPException, Response, Request
from passlib.context import CryptContext
from auth.jwt_handler import sign_jwt, refresh_jwt
from models.employee import Employee
from schemas.user import EmployeeSignIn, ResetPasswordRequest, ForgotPasswordRequest, ForgotPasswordResponse
from utils.utils import send_email
import uuid
from config.config import Settings
from fastapi.responses import JSONResponse
from jose import JWTError, jwt, ExpiredSignatureError
from fastapi import Depends
from datetime import datetime, timedelta, UTC

secret_key = Settings().secret_key
email_template = Settings().email_template
router = APIRouter()
hash_helper = CryptContext(schemes=["bcrypt"])
reset_tokens = {}

@router.post("/login")
async def user_login(user_credentials: EmployeeSignIn = Body(...)):
    user_exists = await Employee.find_one(Employee.employee_id == user_credentials.employee_id)
    if user_exists:
        password = hash_helper.verify(user_credentials.password, user_exists.password)
        if password:
            access_token = sign_jwt(user_credentials.employee_id, user_exists.role, user_exists.email)
            refresh_token = refresh_jwt(user_credentials.employee_id, user_exists.email)

            response = JSONResponse(content={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "role": user_exists.role
            })

            return response

    raise HTTPException(status_code=403, detail="Incorrect credentials")

@router.get("/refresh")
async def refresh_access_token(request: Request):
    # Get the refresh token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Refresh token missing or invalid format")
    
    refresh_token = auth_header.split(" ")[1]
    
    try:
        # Decode and validate the refresh token
        payload = jwt.decode(refresh_token, secret_key, algorithms=["HS256"])
        employee_id = payload.get("employee_id")
        email = payload.get("email")

        if not employee_id or not email:
            raise HTTPException(status_code=401, detail="Invalid refresh token payload")

        # Get user from database to ensure they still exist and get their role
        user = await Employee.find_one(Employee.employee_id == employee_id)
        if not user:
            raise HTTPException(status_code=401, detail="User no longer exists")

        # Generate new access token
        new_access_token = sign_jwt(employee_id, user.role, email)

        return {"access_token": new_access_token}

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error refreshing token: {str(e)}")


# Forgot Password Route
last_reset_request = {}
@router.post("/forgot-password")
async def forgot_password(forgot_password_request: ForgotPasswordRequest = Body(...)):
    email = forgot_password_request.email.lower()
    current_time = datetime.now(UTC)
    if email in last_reset_request:
        last_request_time = last_reset_request[email]
        if current_time - last_request_time < timedelta(minutes=2):
            raise HTTPException(status_code=429, detail="Too many requests. Please wait 2 minutes before trying again.")

    # Perform case-insensitive search
    user_exists = await Employee.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}})

    if not user_exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    reset_token = str(uuid.uuid4())
    reset_tokens[reset_token] = {
        "email": user_exists.email,
        "timestamp": datetime.now(UTC)
    }
    reset_link = f"{email_template}{reset_token}"
    await send_email(user_exists.email, reset_link)
    last_reset_request[email] = current_time
    return ForgotPasswordResponse(message="Password reset link sent to your email.")

# Reset Password Route
@router.post("/reset-password/{reset_token}")
async def reset_password(reset_token: str, request_data: ResetPasswordRequest):
    token_data = reset_tokens.get(reset_token)
    if not token_data:
        raise HTTPException(status_code=404, detail="Invalid or expired token")
        # return {
        #     "success": False,
        #     "message":"Invalid or expired token"
        # }
    email = token_data["email"]
    timestamp = token_data["timestamp"]
    
    user = await Employee.find_one(Employee.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="Invalid or expired token")
    
    while( hash_helper.verify(request_data.new_password, user.password)):
        raise HTTPException(status_code=400, detail="New password cannot be the same as the old password.")
    
    current_time = datetime.now(UTC)
    if current_time - timestamp > timedelta(minutes=5):
        del reset_tokens[reset_token]
        raise HTTPException(status_code=410, detail="Reset link has expired")
        
    user.password = hash_helper.hash(request_data.new_password)
    await user.save()

    del reset_tokens[reset_token]
    
    return {
        "success": True,
        "message": "Password reset successful"
    }

    