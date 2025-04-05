# create sample route to send a test email
from fastapi import APIRouter
from utils.utils import send_new_session_email, send_email

router = APIRouter()

@router.post("/send-test-email")
async def send_test_email(email: str):
    await send_new_session_email(email, "Test Email Trial")
    return {"message": "Email sent successfully"}

