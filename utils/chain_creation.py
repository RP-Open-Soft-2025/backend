import json
from models.chain import Chain, ChainStatus
from models.employee import Employee
from models.session import Session, SessionStatus
from models.notification import Notification, NotificationStatus
from models.chat import Chat

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from utils.utils import send_new_session_email
import requests
from typing import Optional

from config.config import Settings

llm_add = Settings().LLM_ADDR

class CreateChainRequest(BaseModel):
    employee_id: str = Field(..., description="ID of the employee to create chain for")
    notes: Optional[str] = Field(default=None, description="Any additional notes about the chain")
    scheduled_time: Optional[datetime] = Field(
        default=None,
        description="When to schedule the first session. Defaults to tomorrow at 10 AM."
    )


async def create_chain(request: CreateChainRequest):
    
    """
    Create a new chain for an employee and schedule their first session.
    Only Admin / HR personnel can access this endpoint.
    """
    chain = ""
    session = ""
    chat = ""
    notification = ""
    try:
        # Verify the employee exists
        employee = await Employee.get_by_id(request.employee_id)
        if not employee:
            raise HTTPException(
                status_code=404,
                detail=f"Employee with ID {request.employee_id} not found"
            )
        
        # Check if employee already has an active chain
        active_chain = await Chain.find_one({
            "employee_id": request.employee_id,
            "status": ChainStatus.ACTIVE
        })
        if active_chain:
            raise HTTPException(
                status_code=400,
                detail="Employee already has an active chain"
            )
        
        # Set default scheduled time to tomorrow at 10 AM if not provided
        if not request.scheduled_time:
            tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
            request.scheduled_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Create a new chat for the session
        chat = Chat(user_id=request.employee_id)
        await chat.save()
        
        # Create a new session
        session = Session(
            user_id=request.employee_id,
            chat_id=chat.chat_id,
            scheduled_at=request.scheduled_time,
            notes=request.notes
        )
        await session.save()
        
        # Create a new chain
        chain = Chain(
            employee_id=request.employee_id,
            session_ids=[session.session_id],
            status=ChainStatus.ACTIVE,
            notes=request.notes
        )
        await chain.save()
        
        # Create notification for the employee
        notification = Notification(
            employee_id=request.employee_id,
            title="New Support Session Scheduled",
            description=f"A new support session has been scheduled for you on {request.scheduled_time.strftime('%Y-%m-%d %H:%M')} UTC."
        )
        await notification.save()

        await analyze_employee_report(chain.chain_id, employee)

        # mail that a session has been created
        await send_new_session_email(
            to_email=employee.email,
            sub=f"A new support session has been scheduled for you on {request.scheduled_time.strftime('%Y-%m-%d %H:%M')} UTC."
        )

        return chain
        
    except Exception as e:
        # delete the chain if it is created
        if chain:
            await chain.delete()
        # delete the session if it is created
        if session:
            await session.delete()
        # delete the chat if it is created
        if chat:
            await chat.delete()
        # delete the notification if it is created
        if notification:
            await notification.delete()
        
        raise HTTPException(
            status_code=500,
            detail=f"Error creating chain: {str(e)}"
        )
    

async def analyze_employee_report(chain_id: str, employee: Employee):
    try:
        report_data = {
                "employee_data": {
                    "employee_id": employee.employee_id,
                    "company_data": employee.company_data.model_dump(mode='json')
                },
                "chain_id": chain_id
            }

        # call the api, LLM_ADDR/report/analyze
        # print(f"Request data: {json.dumps(report_data)}")
        response = requests.post(f"{llm_add}/report/analyze", json=report_data)
        # print(response)
        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate employee report"
            )
        report = response.json()
        print(report)
            
    except Exception as e:
        raise HTTPException(500, detail=f'exception occurred while analyzing employee report: {e}')
