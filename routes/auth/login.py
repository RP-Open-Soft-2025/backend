from fastapi import APIRouter, Body, HTTPException, Response, Request
from passlib.context import CryptContext
from auth.jwt_handler import sign_jwt, refresh_jwt
from models.employee import Employee
from schemas.user import EmployeeSignIn
from fastapi.responses import JSONResponse
from jose import JWTError, jwt, ExpiredSignatureError
from config.config import Settings
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

secret_key = Settings().secret_key

router = APIRouter()
hash_helper = CryptContext(schemes=["bcrypt"])

@router.post("/login")
async def user_login(user_credentials: EmployeeSignIn = Body(...)):
    user_exists = await Employee.find_one(Employee.employee_id == user_credentials.employee_id)
    if user_exists:
        password = hash_helper.verify(user_credentials.password, user_exists.password)
        if password:
            access_token = sign_jwt(user_credentials.employee_id, user_exists.role, user_exists.email)
            refresh_token = refresh_jwt(user_credentials.employee_id, user_exists.email)

            response = JSONResponse(content={"access_token": access_token, "role": user_exists.role})
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=False,  
                samesite="None",
                max_age= 60, 
            )

            print("Refresh Token set:", refresh_token) 

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



    

