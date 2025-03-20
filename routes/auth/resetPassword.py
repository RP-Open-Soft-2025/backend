from fastapi import APIRouter, HTTPException
from passlib.context import CryptContext
from models.employee import Employee
from schemas.user import ResetPasswordRequest
from .forgotPassword import reset_tokens
router = APIRouter()

hash_helper = CryptContext(schemes=["bcrypt"])

# reset_tokens = {}

@router.post("/{reset_token}")
async def reset_password(reset_token: str, request_data: ResetPasswordRequest):
    if reset_token not in reset_tokens:
        raise HTTPException(status_code=400, detail=f"Invalid or expired token")
    
    email = reset_tokens[reset_token]
    user = await Employee.find_one(Employee.email == email)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    while hash_helper.verify(request_data.new_password, user.password):
        raise HTTPException(status_code=400, detail="New password cannot be the same as the old password. Please try again with a different password.")
    
    hashed_password = hash_helper.hash(request_data.new_password)
    user.password = hashed_password

    await user.save()

    del reset_tokens[reset_token]

    return {"message": "Password reset successful "}
