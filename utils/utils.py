import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import HTTPException
import logging
from config.config import Settings

async def send_email(to_email: str, reset_link: str):
    sender_email = Settings().sender_email
    sender_password = Settings().sender_password
    subject = "Password Reset Request"
    body = f"""Dear User,

You have requested to reset your password. Please click the link below to proceed:

{reset_link}

Important Notes:
- This link will expire in 5 minutes for security reasons
- If you did not request this password reset, please ignore this email
- For security reasons, please change your password immediately after clicking the link

Best regards,
Deloitte"""

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        logging.info("Connecting to SMTP server...")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        logging.info("Successfully authenticated")
        
        logging.info(f"Sending email to {to_email}")
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        logging.info("Email sent successfully")
        
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email")
    
def send_new_session_email(to_email: str, sub: str):
    sender_email = Settings().sender_email
    sender_password = Settings().sender_password
    subject = "Counseling Session Scheduled"
    body = sub

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        logging.info("Connecting to SMTP server...")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        logging.info("Successfully authenticated")
        
        logging.info(f"Sending email to {to_email}")
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        logging.info("Email sent successfully")
        
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email")