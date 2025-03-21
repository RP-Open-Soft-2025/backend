from fastapi import APIRouter, Body, HTTPException
from passlib.context import CryptContext
from auth.jwt_handler import sign_jwt
from models.employee import Employee
from schemas.user import EmployeeSignIn


router = APIRouter()

hash_helper = CryptContext(schemes=["bcrypt"])


@router.post("/")
async def user_login(user_credentials: EmployeeSignIn = Body(...)):
    user_exists = await Employee.find_one(Employee.employee_id == user_credentials.employee_id)
    if user_exists:
        password = hash_helper.verify(user_credentials.password, user_exists.password)
        if password:
            return sign_jwt(user_credentials.employee_id, user_exists.role)

        raise HTTPException(status_code=403, detail="Incorrect employee ID or password")

    raise HTTPException(status_code=403, detail="Incorrect employee ID or password")