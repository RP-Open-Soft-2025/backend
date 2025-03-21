# routes only for hr
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, HTTPAuthorizationCredentials
from auth.jwt_handler import decode_jwt
from models.employee import Employee, Role
import datetime

router = APIRouter()
security = OAuth2PasswordBearer(tokenUrl="token")

async def verify_hr(token: HTTPAuthorizationCredentials = Depends(security)):
    """Verify that the user is an HR."""
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    claims_jwt = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": claims_jwt["user_id"], "role": Role.HR})
    
    if not hr_user:
        raise HTTPException(status_code=403, detail="Only HR personnel can access this endpoint")
    
    return claims_jwt

@router.patch("/block-user/{userId}")
async def block_user_hr(userId: str, token: HTTPAuthorizationCredentials = Depends(security)):
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorised")
    
    claims_jwt = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": claims_jwt["user_id"], "role": Role.HR})

    if not hr_user:
        return HTTPException(403, "Error HR not found")
    
    emp_user = await Employee.find_one({"employee_id": userId})
    if not emp_user:
        raise HTTPException(status_code=404, detail="Employee not found")

    if emp_user.manager_id == claims_jwt["user_id"]:
        emp_user.is_blocked = True
        emp_user.blocked_by = emp_user.employee_id
        emp_user.blocked_at = datetime.datetime.now()
        return {"msg": f"{emp_user.employee_id} is blocked"}
    else:
        return HTTPException(403, "Error not employee of HR")
        

@router.patch("/unblock-user/{userId}")
async def unblock_user_hr(userId: str, token: HTTPAuthorizationCredentials = Depends(security)):
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorised")
    
    claims_jwt = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": claims_jwt["user_id"], "role": Role.HR})

    if not hr_user:
        return HTTPException(403, "Error HR not found")
    
    emp_user = await Employee.find_one({"employee_id": userId})
    if not emp_user:
        raise HTTPException(status_code=404, detail="Employee not found")

    if emp_user.manager_id == claims_jwt["user_id"]:
        emp_user.is_blocked = False
        emp_user.blocked_by = None
        emp_user.blocked_at = None
        return {"msg": f"{emp_user.employee_id} is unblocked"}
    else:
        return HTTPException(403, "Error not employee of HR")
        
@router.delete("/delete-user/{userId}")
async def delete_user_hr(userId: str, token: HTTPAuthorizationCredentials = Depends(security)):
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorised")
    
    claims_jwt = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": claims_jwt["user_id"], "role": Role.HR})
    
    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    emp_user = await Employee.find_one({"employee_id": userId})
    if not emp_user:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if emp_user.manager_id == claims_jwt["user_id"]:
        await emp_user.delete()
        return {"msg": f"{emp_user.employee_id} is deleted from database"}
    else:
        raise HTTPException(status_code=403, detail="Error not authorized to delete this employee")

@router.get("/list-assigned-users", tags=["HR"])
async def list_assigned_users(hr: dict = Depends(verify_hr)):
    """
    Get a list of users assigned to the HR.
    Only HR personnel can access this endpoint.
    """
    try:
        # Get all employees assigned to this HR
        employees = await Employee.find({"manager_id": hr["user_id"]}).to_list()
        
        # Format the response
        users = []
        for employee in employees:
            user_data = {
                "userId": employee.employee_id,
                "name": employee.name,
                "email": employee.email,
                "status": "active" if not employee.is_blocked else "blocked",
                "sessionData": {
                    "moodScores": [
                        {
                            "timestamp": vibe.Response_Date.isoformat(),
                            "score": vibe.Vibe_Score
                        }
                        for vibe in employee.company_data.vibemeter
                    ]
                }
            }
            users.append(user_data)
        
        return {"users": users}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching assigned users: {str(e)}"
        )