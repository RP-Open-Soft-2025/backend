from fastapi import Request, Response, HTTPException
from jose import JWTError, jwt, ExpiredSignatureError, InvalidTokenError
from starlette.middleware.base import BaseHTTPMiddleware
from auth.jwt_handler import sign_jwt
from models import Employee  
from config.config import Settings
from typing import Optional

secret_key = Settings().secret_key

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)  

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return response 

        access_token = auth_header.split(" ")[1]

        try:
            # Validate access token
            jwt.decode(access_token, secret_key, algorithms=["HS256"])
        except ExpiredSignatureError:
            # Handle expired access token
            new_access_token = await self._handle_refresh_token(request)
            if new_access_token:
                response.headers["Authorization"] = f"Bearer {new_access_token}"
            else:
                # If refresh token is invalid or expired, clear cookies and continue
                response.delete_cookie("refresh_token")
        except (JWTError, InvalidTokenError) as e:
            # Handle other JWT errors
            response.delete_cookie("refresh_token")
            response.status_code = 401
            return response

        return response

    async def _handle_refresh_token(self, request: Request) -> Optional[str]:
        """
        Handle refresh token validation and new access token generation.
        Returns new access token if successful, None otherwise.
        """
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            return None

        try:
            # Validate refresh token
            payload = jwt.decode(refresh_token, secret_key, algorithms=["HS256"])
            employee_id = payload.get("sub")
            
            if not employee_id:
                return None

            # Check if user exists
            user_exists = await Employee.find_one(Employee.employee_id == employee_id)
            if not user_exists:
                return None

            # Generate new access token
            return sign_jwt(user_exists.employee_id, user_exists.role, user_exists.email)

        except (ExpiredSignatureError, JWTError, InvalidTokenError):
            # Handle all JWT-related errors for refresh token
            return None