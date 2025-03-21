from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from models.session import Session, SessionStatus
from models.employee import Employee
from models.chat import Chat
from auth.jwt_bearer import JWTBearer
from auth.jwt_handler import decode_jwt

router = APIRouter()

class SessionResponse(BaseModel):
    session_id: str
    employee_id: str
    chat_id: str
    status: str
    scheduled_at: datetime

@router.get("/", response_model=List[SessionResponse])
async def get_user_sessions(token: str = Depends(JWTBearer())):
    """
    Get sessions for the authenticated user.
    Returns a list of sessions associated with the user.
    """
    try:
        # Decode the JWT token to get user info
        payload = decode_jwt(token)
        user_id = payload.get("employee_id")
        user_role = payload.get("role")
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="Invalid token: employee_id not found"
            )

        # Get sessions based on role
        if user_role == "admin":
            # Admins can see all sessions
            sessions = await Session.get_all()
        else:
            # Regular users can only see their sessions
            sessions = await Session.get_by_user_id(user_id)
        
        # Convert sessions to response format
        session_responses = [
            SessionResponse(
                session_id=session.session_id,
                employee_id=session.user_id,
                chat_id=session.chat_id,
                status=session.status.value,
                scheduled_at=session.scheduled_at
            )
            for session in sessions
        ]
        
        return session_responses
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching sessions: {str(e)}"
        )

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, token: str = Depends(JWTBearer())):
    """
    Get a specific session by ID.
    Users can only access their own sessions unless they are admins.
    """
    try:
        # Decode the JWT token to get user info
        payload = decode_jwt(token)
        user_id = payload.get("employee_id")
        user_role = payload.get("role")
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="Invalid token: employee_id not found"
            )

        # Get the session
        session = await Session.get_by_id(session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session with ID {session_id} not found"
            )

        # Check if user has access to this session
        if session.user_id != user_id and user_role not in ["admin", "hr"]:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to access this session"
            )
        
        return SessionResponse(
            session_id=session.session_id,
            employee_id=session.user_id,
            chat_id=session.chat_id,
            status=session.status.value,
            scheduled_at=session.scheduled_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching session: {str(e)}"
        ) 