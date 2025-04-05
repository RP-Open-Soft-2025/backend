import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import HTTPException
import logging
# Avoid direct import to prevent circular references
# from config.config import Settings

# Settings will be imported when functions are called
_settings = None

def get_settings():
    global _settings
    if _settings is None:
        from config.config import Settings
        _settings = Settings()
    return _settings

async def send_email(to_email: str, reset_link: str):
    settings = get_settings()
    sender_email = settings.sender_email
    sender_password = settings.sender_password
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
    
async def send_new_session_email(to_email: str, sub: str):
    settings = get_settings()
    sender_email = settings.sender_email
    sender_password = settings.sender_password
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
    
async def send_new_employee_email(to_email: str, user:str , password:str):
    settings = get_settings()
    sender_email = settings.sender_email
    sender_password = settings.sender_password
    subject = "Your Account Credentials"
    body = f"""Dear Employee,

Welcome to Delloite! We are excited to have you on board and look forward to working with you.

Below are your login credentials for accessing your company account:

Username: {user}

Temporary Password: {password}

For security reasons, please log in and change your password as soon as possible.

We wish you a great start and success in your new role!

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


# def create a mail sender for it the deadline of a session +1 day is over
async def send_deadline_reminder_email(to_email: str):
    settings = get_settings()
    sender_email = settings.sender_email
    sender_password = settings.sender_password
    subject = "Session Deadline Reminder"
    body = f"""Dear Employee,

This is a reminder that your session is scheduled to end in 1 day. Please make sure to attend the session at the scheduled time.

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

async def send_deadline_over_email(to_email: str):
    settings = get_settings()
    sender_email = settings.sender_email
    sender_password = settings.sender_password
    subject = "Session Deadline Over"
    # the body contains that the deadline is over and the employee has not attended the session and will be reported to the HR
    body = f"""Dear Employee,

This is a reminder that your session deadline has passed. You have not attended the session and will be reported to the HR.

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


async def send_escalation_mail(to_email: str, sub: str):
    settings = get_settings()
    sender_email = settings.sender_email
    sender_password = settings.sender_password
    subject = "Escalation Required"
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
    
    

    

