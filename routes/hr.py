# routes only for hr
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, HTTPAuthorizationCredentials
from auth.jwt_handler import decode_jwt
from models.session import Session, SessionStatus
from models.employee import Employee, Role
import datetime
import uuid

router = APIRouter()
security = OAuth2PasswordBearer(tokenUrl="token")

@router.patch("/block-user/{userId}")
async def block_user_hr(userId: str, token: HTTPAuthorizationCredentials = Depends(security)):
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorised")
    
    claims_jwt = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": claims_jwt["employee_id"], "role": Role.HR})

    if not hr_user:
        return HTTPException(403, "Error HR not found")
    
    emp_user = await Employee.find_one({"employee_id": userId})
    if not emp_user:
        raise HTTPException(status_code=404, detail="Employee not found")

    if emp_user.manager_id == claims_jwt["employee_id"]:
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
    hr_user = await Employee.find_one({"employee_id": claims_jwt["employee_id"], "role": Role.HR})

    if not hr_user:
        return HTTPException(403, "Error HR not found")
    
    emp_user = await Employee.find_one({"employee_id": userId})
    if not emp_user:
        raise HTTPException(status_code=404, detail="Employee not found")

    if emp_user.manager_id == claims_jwt["employee_id"]:
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
    hr_user = await Employee.find_one({"employee_id": claims_jwt["employee_id"], "role": Role.HR})
    
    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    emp_user = await Employee.find_one({"employee_id": userId})
    if not emp_user:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if emp_user.manager_id == claims_jwt["employee_id"]:
        await emp_user.delete()
        return {"msg": f"{emp_user.employee_id} is deleted from database"}
    else:
        raise HTTPException(status_code=403, detail="Error not authorized to delete this employee")

@router.get("/sessions")
async def get_hr_sessions(token: HTTPAuthorizationCredentials = Depends(security)):
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorised")
    
    claims_jwt = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": claims_jwt["employee_id"], "role": Role.HR})

    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    # Get all employees managed by this HR
    employees = await Employee.get_employees_by_manager(claims_jwt["employee_id"])
    employee_ids = [emp.employee_id for emp in employees]
    
    # Get active sessions for all employees under this HR
    active_sessions = await Session.find({
        "user_id": {"$in": employee_ids},
        "status": SessionStatus.ACTIVE
    }).to_list()
    
    # Format response
    session_responses = [
        {
            "session_id": session.session_id,
            "employee_id": session.user_id,
            "chat_id": session.chat_id,
            "status": session.status.value,
            "scheduled_at": session.scheduled_at
        }
        for session in active_sessions
    ]
    
    return session_responses

   

@router.post("/session/{userId}")
async def create_session_hr(userId: str, token: HTTPAuthorizationCredentials = Depends(security)):
    if not token or token.lower() == "not authenticated":
        raise HTTPException(status_code=401, detail="Unauthorised")
    
    claims_jwt = decode_jwt(token)
    hr_user = await Employee.find_one({"employee_id": claims_jwt["employee_id"], "role": Role.HR})

    if not hr_user:
        raise HTTPException(status_code=403, detail="Error HR not found")
    
    emp_user = await Employee.find_one({"employee_id": userId})
    if not emp_user:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Verify if the employee is assigned to this HR
    if emp_user.manager_id != claims_jwt["employee_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to create session for this employee")
    
    # Generate unique session and chat IDs
    session_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    
    return {
        "session_id": session_id,
        "chat_id": chat_id,
        "message": "chat session created successfully"
    }