import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import HTTPException
import logging

async def send_email(to_email: str, reset_link: str):
    sender_email = "web103856@gmail.com"
    sender_password = "ipdtsisbfvjbrmkp"

    subject = "Password Reset Request"
    body = f"Click the link to reset your password: {reset_link}"

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
