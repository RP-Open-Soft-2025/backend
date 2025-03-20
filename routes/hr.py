# routes only for hr
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, HTTPAuthorizationCredentials
from auth.jwt_handler import decode_jwt
from models.employee import Employee, Role

router = APIRouter()
security = OAuth2PasswordBearer(tokenUrl="token")

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
        # TODO: After block added to model, add blocked set to true
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
        # TODO: After block added to model, add blocked set to false
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