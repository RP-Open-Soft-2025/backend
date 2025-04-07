from fastapi import HTTPException, Depends
from models.employee import Employee
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt

async def verify_employee(token: str = Depends(JWTBearer())):
    """Verify that the user exists in the database."""
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    payload = decode_jwt(token)
    employee = await Employee.find_one({"employee_id": payload["employee_id"]})
    
    if not employee:
        raise HTTPException(status_code=403, detail="Only authenticated users can access this endpoint")
    
    return employee