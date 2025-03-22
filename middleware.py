from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from jose import jwt, JWTError, ExpiredSignatureError
from models import Employee  # Adjust based on your ORM
from auth.jwt_handler import sign_jwt  # Function to generate a new token

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """Middleware to refresh JWT access token when expired."""
        print("Cookies received:", request.cookies) 

        response = await call_next(request)  # Get the response early

        access_token = request.cookies.get("access_token")
        refresh_token = request.cookies.get("refresh_token")

        if not access_token:
            return response  # No access token, skip refresh

        try:
            jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        except ExpiredSignatureError:  # Only refresh if access token expired
            if refresh_token:
                try:
                    payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
                    employee_id = payload.get("sub")  

                    # Fetch user from DB (Use the correct ORM method)
                    user_exists = await Employee.get(employee_id=employee_id)  # Adjust based on your ORM
                    if not user_exists:
                        return response  # User not found, don't refresh

                    # Generate new access token
                    new_access_token = sign_jwt(user_exists.employee_id, user_exists.role, user_exists.email)
                    print("New access token generated")
                    # Set new access token in cookies
                    response.set_cookie(
                        key="new_access_token",
                        value=new_access_token,
                        httponly=True,
                        secure=False,
                        samesite="None",
                        max_age=15,  
                    )
                except JWTError:
                    print("logout")  # Invalid refresh token, do nothing

        return response




