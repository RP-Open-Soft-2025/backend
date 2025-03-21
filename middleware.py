from fastapi import Request, Response
from jose import JWTError, jwt, ExpiredSignatureError
from starlette.middleware.base import BaseHTTPMiddleware
from auth.jwt_handler import sign_jwt
from models import Employee  
from config.config import Settings

secret_key = Settings().secret_key

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)  

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return response 

        access_token = auth_header.split(" ")[1]

        try:
            jwt.decode(access_token, secret_key, algorithms=["HS256"])
        except ExpiredSignatureError:
            refresh_token = request.cookies.get("refresh_token")
            if refresh_token:
                try:
                    payload = jwt.decode(refresh_token, secret_key, algorithms=["HS256"])
                    employee_id = payload.get("sub") 

                    user_exists = await Employee.find_one(Employee.employee_id == employee_id)
                    if not user_exists:
                        return response  

                
                    new_access_token = sign_jwt(user_exists.employee_id, user_exists.role, user_exists.email)

        
                    response.headers["Authorization"] = f"Bearer {new_access_token}"

                except ExpiredSignatureError:
                    response.delete_cookie("refresh_token")

        return response  

