from fastapi import APIRouter, Body, HTTPException, Depends
from passlib.context import CryptContext
from models.employee import Employee
from schemas.user import EmployeeSignIn, ResetPasswordRequest, ForgotPasswordRequest, ForgotPasswordResponse
from utils.utils import send_email
import uuid
from config.config import Settings
from fastapi.responses import JSONResponse
from async_fastapi_jwt_auth import AuthJWT
from async_fastapi_jwt_auth.exceptions import AuthJWTException
from pydantic import BaseModel
from async_fastapi_jwt_auth.auth_jwt import AuthJWTBearer
# Define a Pydantic model for the login response
class LoginResponse(BaseModel):
    success: bool
    message: str
    role: str

secret_key = Settings().secret_key
router = APIRouter()
hash_helper = CryptContext(schemes=["bcrypt"])
reset_tokens = {}

# Add auth dependency
auth_dep = AuthJWTBearer()

@router.post("/login", response_model=LoginResponse)
async def user_login(user_credentials: EmployeeSignIn = Body(...), Authorize: AuthJWT = Depends(auth_dep)):
    user_exists = await Employee.find_one(Employee.employee_id == user_credentials.employee_id)
    if user_exists:
        password = hash_helper.verify(user_credentials.password, user_exists.password)
        if password:
            # Create the tokens asynchronously
            access_token = await Authorize.create_access_token(subject=user_credentials.employee_id, user_claims={
                "role": user_exists.role,
                "email": user_exists.email
            })
            refresh_token = await Authorize.create_refresh_token(subject=user_credentials.employee_id, user_claims={
                "email": user_exists.email
            })

            # Set the JWT cookies in the response
            response = JSONResponse(content={
                "success": True,
                "message": "Successful login",
                "role": user_exists.role
            })
            
            await Authorize.set_access_cookies(access_token, response)
            await Authorize.set_refresh_cookies(refresh_token, response)

            return response

    raise HTTPException(status_code=403, detail="Incorrect credentials")

@router.post('/refresh')
async def refresh(Authorize: AuthJWT = Depends(auth_dep)):
    """
    Endpoint to refresh the access token using a valid refresh token.
    """
    await Authorize.jwt_refresh_token_required()
    
    current_user = await Authorize.get_jwt_subject()
    user = await Employee.find_one(Employee.employee_id == current_user)
    
    new_access_token = await Authorize.create_access_token(subject=current_user, user_claims={
        "role": user.role,
        "email": user.email
    })
    
    response = JSONResponse(content={"message": "Token refreshed successfully"})
    await Authorize.set_access_cookies(new_access_token, response)
    return response

@router.get('/protected')
async def protected(Authorize: AuthJWT = Depends(auth_dep)):
    await Authorize.jwt_required()
    
    current_user = await Authorize.get_jwt_subject()
    return {"user": current_user}


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

