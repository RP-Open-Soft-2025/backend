# routes only for admins
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
import uuid
from models.session import Session, SessionStatus
from models.employee import Employee
from models.chat import Chat
from auth.jwt_bearer import JWTBearer
from pydantic import BaseModel

router = APIRouter()
token_listener = JWTBearer()


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    chat_id: str
    status: str
    scheduled_at: datetime


class CreateSessionRequest(BaseModel):
    scheduled_at: datetime
    notes: Optional[str] = None


class CreateSessionResponse(BaseModel):
    chat_id: str
    session_id: str
    message: str


# Routes
@router.get("/chats", response_model=List[SessionResponse], tags=["Admin"])
async def get_all_active_chats(token: str = Depends(token_listener)):
    """Get all active chat sessions with their session status"""
    try:
        # Get all active sessions
        active_sessions = await Session.find({"status": SessionStatus.PENDING}).to_list()
        
        return [
            SessionResponse(
                session_id=session.session_id,
                user_id=session.user_id,
                chat_id=session.chat_id,
                status=session.status.value,  # Convert enum to string
                scheduled_at=session.scheduled_at
            )
            for session in active_sessions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/{user_id}", response_model=CreateSessionResponse, tags=["Admin"])
async def create_chat_session(
    user_id: str,
    session_data: CreateSessionRequest,
    notes: Optional[str] = None,
    # token: str = Depends(token_listener)
):
    """Create a new chat session for a specific usersdf"""
    try:
        # Check if user exists
        user = await Employee.find_one({"employee_id": user_id})
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        
        print(user)

        # Check if user is blocked
        if user.is_blocked:
            raise HTTPException(status_code=400, detail=f"User {user_id} is blocked")

        # Create new chat
        chat_id = ""
        try: 
            new_chat = Chat(
                user_id=user_id,
                messages=[],
                mood_score=-1
            )

            # print the new_chat object such that is is visible, stringified
            print("chat created", new_chat)

            # chat_id = new_chat.chat_id
        except Exception as e:
            print("erroroccurs ", e)
        
        print("xchat_id: ", chat_id)

        # print(new_chat)

        # await new_chat.save()

        # Create new session
        # new_session = Session(
        #     user_id=user_id,
        #     # chat_id=new_chat.chat_id,
        #     chat_id="",
        #     status=SessionStatus.PENDING,
        #     scheduled_at=session_data.scheduled_at,
        #     notes=session_data.notes
        # )

        # print(new_session)
        
        # await new_session.save()
        
        return CreateSessionResponse(
            # chat_id=chat_id,
            chat_id="",
            # session_id=new_session.session_id,
            session_id="",
            message="Chat session created"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



