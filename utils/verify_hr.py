from fastapi import HTTPException, Depends
from models.employee import Employee, Role
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt

async def verify_hr(token: str = Depends(JWTBearer())):
    """Verify that the user is an HR."""
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    payload = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": payload["employee_id"], "role": {"$in": [Role.ADMIN, Role.HR]}})
    
    if not hr_user:
        raise HTTPException(status_code=403, detail="Only Admin / HR personnel can access this endpoint")
    
    return hr_user