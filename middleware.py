from fastapi import FastAPI, Request, Response, Depends
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from auth.jwt_handler import sign_jwt
from models import Employee
from config.config import Settings

app = FastAPI()

secret_key = Settings().secret_key

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """Middleware to automatically refresh JWT access token when expired."""
        response = await call_next(request)  

        access_token = request.cookies.get("access_token")
        if not access_token:
            return response  

        try:
            jwt.decode(access_token, secret_key, algorithms=["HS256"])
        except JWTError:
            refresh_token = request.cookies.get("refresh_token")
            if refresh_token:
                try:
                    payload = jwt.decode(refresh_token, secret_key, algorithms=["HS256"])
                    employee_id = payload.get("sub") 

                    user_exists = await Employee.find_one(Employee.employee_id == employee_id)
                    if not user_exists:
                        return response  

                    new_access_token = sign_jwt(user_exists.employee_id, user_exists.role, user_exists.email)

                    response.set_cookie(
                        key="access_token",
                        value=new_access_token,
                        httponly=True,
                        secure=True,  
                        samesite="None",
                        max_age=5,  
                    )

                except JWTError:
                    pass  

        return response  




