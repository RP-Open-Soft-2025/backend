from fastapi import APIRouter, Body, HTTPException, Response, Request
from passlib.context import CryptContext
from auth.jwt_handler import sign_jwt, refresh_jwt
from auth.jwt_bearer import JWTBearer
from models.employee import Employee, Role
from models.reset_token import ResetToken
from schemas.user import EmployeeSignIn, ResetPasswordRequest, ForgotPasswordRequest, ForgotPasswordResponse
from utils.utils import send_email
import uuid
from config.config import Settings
from fastapi.responses import JSONResponse
from jose import JWTError, jwt, ExpiredSignatureError
from fastapi import Depends
from datetime import datetime, timedelta, timezone

secret_key = Settings().secret_key
email_template = Settings().email_template
admin_email_template = Settings().admin_email_template
router = APIRouter()
hash_helper = CryptContext(schemes=["bcrypt"])

# Regular user routes
@router.post("/login")
async def user_login(user_credentials: EmployeeSignIn = Body(...)):
    user_exists = await Employee.find_one(Employee.employee_id == user_credentials.employee_id)
    if user_exists:
        # if user_exists.role == "admin" or user_exists.role == "hr":
        #     raise HTTPException(status_code=403, detail="Please use admin login endpoint")

        if user_exists.is_blocked:
            raise HTTPException(status_code=403, detail="Your account has been blocked. Please contact your administrator.")
            
        password = hash_helper.verify(user_credentials.password, user_exists.password)
        if password:
            # Check if this is first login
            if user_exists.is_first_login:
                # Generate a reset token for first-time password reset
                reset_token = await ResetToken.create_token(
                    email=user_exists.email,
                    is_first_login=True
                )
                reset_link = f"{email_template}{reset_token.token}"
                await send_email(user_exists.email, reset_link)
                
                return JSONResponse(
                    status_code=307,
                    content={
                        # "message": "A password reset link has been sent to your email. Please check your email and reset your password.",
                        "redirect_url": f"/reset-password/{reset_token.token}",
                        "expires_in": "5 minutes"
                    }
                )

            access_token = sign_jwt(user_credentials.employee_id, user_exists.role, user_exists.email)
            refresh_token = refresh_jwt(user_credentials.employee_id, user_exists.email)

            response = JSONResponse(content={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "role": user_exists.role,
                "is_first_login": user_exists.is_first_login
            })

            return response

    raise HTTPException(status_code=403, detail="Incorrect credentials")

# Admin-specific routes
@router.post("/admin/login")
async def admin_login(user_credentials: EmployeeSignIn = Body(...)):
    user_exists = await Employee.find_one(Employee.employee_id == user_credentials.employee_id)
    if user_exists and (user_exists.role == "admin" or user_exists.role == "hr"):
        password = hash_helper.verify(user_credentials.password, user_exists.password)
        if password:
            if user_exists.is_first_login:
                reset_token = await ResetToken.create_token(
                    email=user_exists.email,
                    is_first_login=True,
                    is_admin=True
                )
                reset_link = f"{admin_email_template}{reset_token.token}"
                await send_email(user_exists.email, reset_link)
                
                return JSONResponse(
                    status_code=307,
                    content={
                        # "message": "A password reset link has been sent to your email. Please check your email and reset your password.",
                        "redirect_url": f"/admin/reset-password/{reset_token.token}",
                        "expires_in": "5 minutes"
                    }
                )

            access_token = sign_jwt(user_credentials.employee_id, user_exists.role, user_exists.email)
            refresh_token = refresh_jwt(user_credentials.employee_id, user_exists.email)

            return JSONResponse(content={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "role": user_exists.role,
                "is_first_login": user_exists.is_first_login
            })

    raise HTTPException(status_code=403, detail="Invalid credentials!")

@router.post("/admin/forgot-password")
async def admin_forgot_password(forgot_password_request: ForgotPasswordRequest = Body(...)):
    email = forgot_password_request.email.lower()
    current_time = datetime.now(timezone.utc)
    
    # Check if user exists and is admin or HR
    user_exists = await Employee.find_one({
        "email": {"$regex": f"^{email}$", "$options": "i"},
        "role": {"$in": ["admin", "hr"]}
    })
    
    if not user_exists:
        raise HTTPException(status_code=404, detail="Admin/HR user not found")
    
    # Check for recent reset requests using the database
    if await ResetToken.has_recent_request(email):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait 2 minutes before trying again.")
    
    reset_token = await ResetToken.create_token(
        email=user_exists.email,
        is_admin=True
    )
    reset_link = f"{admin_email_template}{reset_token.token}"
    await send_email(user_exists.email, reset_link)
    
    return ForgotPasswordResponse(message="Admin/HR password reset link sent to your email.")

@router.get("/admin/validate-reset-token/{reset_token}")
async def validate_admin_reset_token(reset_token: str):
    token_data = await ResetToken.get_admin_token(reset_token)
    
    if not token_data:
        raise HTTPException(status_code=404, detail="Invalid or expired admin/HR reset token")
    
    timestamp = token_data.timestamp
    # Make sure timestamp is timezone-aware
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    
    current_time = datetime.now(timezone.utc)
    if current_time - timestamp > timedelta(minutes=5):
        await ResetToken.delete_token(reset_token)
        raise HTTPException(status_code=410, detail="Admin/HR reset link has expired")

    return {
        "message": "Admin/HR token is valid",
        # "expires_in": "5 minutes"
    }

@router.post("/admin/reset-password/{reset_token}")
async def admin_reset_password(reset_token: str, request_data: ResetPasswordRequest):
    token_data = await ResetToken.get_admin_token(reset_token)
    if not token_data:
        raise HTTPException(status_code=404, detail="Invalid or expired admin reset token")
    
    email = token_data.email
    timestamp = token_data.timestamp
    # Make sure timestamp is timezone-aware
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    
    is_first_login = token_data.is_first_login
    
    user = await Employee.find_one({
        "email": email,
        "role": {"$in": ["admin", "hr"]}
    })
    if not user:
        raise HTTPException(status_code=404, detail="Admin/HR user not found")
    
    if hash_helper.verify(request_data.new_password, user.password):
        raise HTTPException(status_code=400, detail="New password cannot be the same as the old password.")
    
    current_time = datetime.now(timezone.utc)
    if current_time - timestamp > timedelta(minutes=5):
        await ResetToken.delete_token(reset_token)
        raise HTTPException(status_code=410, detail="Reset link has expired")
        
    user.password = hash_helper.hash(request_data.new_password)
    
    if is_first_login:
        user.is_first_login = False
    
    await user.save()
    # Delete the token after successful use
    await ResetToken.delete_token(reset_token)
    
    return {
        "success": True,
        "message": "Admin/HR password reset successful",
        "is_first_login": user.is_first_login
    }

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
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error refreshing token: {str(e)}")

# Forgot Password Route
@router.post("/forgot-password")
async def forgot_password(forgot_password_request: ForgotPasswordRequest = Body(...)):
    email = forgot_password_request.email.lower()
    current_time = datetime.now(timezone.utc)
    
    # Check for recent reset requests using the database
    if await ResetToken.has_recent_request(email):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait 2 minutes before trying again.")

    # Perform case-insensitive search
    user_exists = await Employee.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}})

    if not user_exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    reset_token = await ResetToken.create_token(email=user_exists.email)
    reset_link = f"{email_template}{reset_token.token}"
    await send_email(user_exists.email, reset_link)
    
    return ForgotPasswordResponse(message="Password reset link sent to your email.")

@router.get("/validate-reset-token/{reset_token}")
async def validate_reset_token(reset_token: str):
    token_data = await ResetToken.get_employee_token(reset_token)
    
    if not token_data:
        raise HTTPException(status_code=404, detail="Invalid or expired token")
    
    timestamp = token_data.timestamp
    # Make sure timestamp is timezone-aware
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    
    current_time = datetime.now(timezone.utc)
    if current_time - timestamp > timedelta(minutes=5):
        await ResetToken.delete_token(reset_token)
        raise HTTPException(status_code=410, detail="Reset link has expired")

    return {"message": "Token is valid"}

@router.post("/reset-password/{reset_token}")
async def reset_password(reset_token: str, request_data: ResetPasswordRequest):
    token_data = await ResetToken.get_employee_token(reset_token)
    if not token_data:
        raise HTTPException(status_code=404, detail="Invalid or expired token")
    
    email = token_data.email
    timestamp = token_data.timestamp
    # Make sure timestamp is timezone-aware
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    
    is_first_login = token_data.is_first_login
    
    user = await Employee.find_one(Employee.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="Invalid or expired token")
    
    if hash_helper.verify(request_data.new_password, user.password):
        raise HTTPException(status_code=400, detail="New password cannot be the same as the old password.")
    
    current_time = datetime.now(timezone.utc)
    if current_time - timestamp > timedelta(minutes=5):
        await ResetToken.delete_token(reset_token)
        raise HTTPException(status_code=410, detail="Reset link has expired")
        
    user.password = hash_helper.hash(request_data.new_password)
    
    # If this was first login, update the flag
    if is_first_login:
        user.is_first_login = False
    
    await user.save()
    # Delete the token after successful use
    await ResetToken.delete_token(reset_token)
    
    return {
        "success": True,
        "message": "Password reset successful",
        "is_first_login": user.is_first_login
    }

    