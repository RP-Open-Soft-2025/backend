from fastapi import HTTPException, Depends
from models.employee import Employee, Role
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt

async def verify_admin(token: str = Depends(JWTBearer())):
    """Verify that the user is an admin."""
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    payload = decode_jwt(token)
    admin_user = await Employee.find_one({"employee_id": payload["employee_id"], "role": Role.ADMIN})
    
    if not admin_user:
        raise HTTPException(status_code=403, detail="Only administrators can access this endpoint")
    
    return admin_user
