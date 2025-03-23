from fastapi import Depends, HTTPException
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt

token_listener = JWTBearer()

async def get_current_user(token: str = Depends(token_listener)) -> dict:
    """
    Get the current user from the JWT token.
    Returns a dictionary containing the user's employee_id and role.
    Raises HTTPException if the token is invalid or expired.
    """
    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return {
        "employee_id": payload.get("employee_id"),
        "role": payload.get("role")
    } 