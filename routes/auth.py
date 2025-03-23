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

secret_key = Settings().secret_key
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
async def refresh_access_token(request: Request, response: Response):
    cookies = request.cookies
    print("Received Cookies:", cookies)
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    try:
        payload = jwt.decode(refresh_token, secret_key, algorithms=["HS256"])
        employee_id = payload.get("sub")
        email = payload.get("email")

        if not employee_id or not email:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

    
        new_access_token = sign_jwt(employee_id, payload.get("role", ""), email)

        return {"access_token": new_access_token}

    except ExpiredSignatureError:
        response.delete_cookie("refresh_token")  
        raise HTTPException(status_code=401, detail="Refresh token expired. Please log in again.")

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