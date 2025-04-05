# create sample route to send a test email
from fastapi import APIRouter
from utils.utils import send_new_session_email, send_email

router = APIRouter()

@router.post("/send-test-email")
async def send_test_email(email: str):
    await send_email(email=email, reset_link="Test Email address")
    return {"message": "Email sent successfully"}

