from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from employee_filtering.blackbox import select_employees
from models.session import Session, SessionStatus
from models.employee import Employee
from models.chat import Chat
from models.notification import Notification, create_notification
from models.chain import Chain, ChainStatus
from utils.utils import send_new_session_email, send_deadline_reminder_email, send_deadline_over_email
import json
from datetime import datetime, timedelta, timezone
import logging
import uuid
import os

from utils.chain_creation import create_chain

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cooldown period in days (configurable)
COOLDOWN_PERIOD_DAYS = 14

async def generate_employee_data_json():
    """Generate employee_data.json from database."""
    try:
        # Delete existing file if it exists
        if os.path.exists('employee_data.json'):
            os.remove('employee_data.json')
            logger.info("Deleted existing employee_data.json")

        # Get all employees from database
        employees = await Employee.find_all()
        
        # Prepare data in the required format
        employee_data = []
        for employee in employees:
            # Convert datetime objects to strings in company_data
            company_data = employee.company_data.dict()
            
            # Convert dates in activity
            for activity in company_data['activity']:
                activity['Date'] = activity['Date'].strftime('%m/%d/%Y')
            
            # Convert dates in leave
            for leave in company_data['leave']:
                leave['Leave_Start_Date'] = leave['Leave_Start_Date'].strftime('%m/%d/%Y')
                leave['Leave_End_Date'] = leave['Leave_End_Date'].strftime('%m/%d/%Y')
            
            # Convert dates in onboarding
            for onboarding in company_data['onboarding']:
                onboarding['Joining_Date'] = onboarding['Joining_Date'].strftime('%Y-%m-%d')
            
            # Convert dates in rewards
            for reward in company_data['rewards']:
                reward['Award_Date'] = reward['Award_Date'].strftime('%Y-%m-%d')
            
            # Convert dates in vibemeter
            for vibe in company_data['vibemeter']:
                vibe['Response_Date'] = vibe['Response_Date'].strftime('%Y-%m-%d')
            
            # Create employee entry
            employee_entry = {
                "employee_id": employee.employee_id,
                "company_data": company_data
            }
            employee_data.append(employee_entry)
        
        # Write to file
        with open('employee_data.json', 'w') as f:
            json.dump(employee_data, f, indent=4)
        
        logger.info(f"Generated employee_data.json with {len(employee_data)} employees")
        return True
        
    except Exception as e:
        logger.error(f"Error generating employee_data.json: {str(e)}")
        return False

async def schedule_session_and_notify(employee_id: str):
    """Schedule a counseling session for an employee and send notifications."""
    try:
        # Get employee details
        employee = await Employee.get_by_id(employee_id)
        if not employee:
            logger.error(f"Employee not found: {employee_id}")
            return

        # Create a new chain for the series of sessions
        chain = Chain(
            employee_id=employee_id,
            status=ChainStatus.ACTIVE,
            notes="Automatically created counseling chain"
        )
        await chain.save()

        # Create a new chat for the session
        chat = Chat(
            chat_id=f"CHAT{uuid.uuid4().hex[:6].upper()}",
            user_id=employee_id,
            created_at=datetime.now(timezone.utc)
        )
        await chat.save()

        # Schedule session for tomorrow at 10 AM
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        scheduled_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)

        # Create new session
        session = Session(
            user_id=employee_id,
            chat_id=chat.chat_id,
            status=SessionStatus.PENDING,
            scheduled_at=scheduled_time,
            notes="Automatically scheduled counseling session"
        )
        await session.save()

        # Add session to chain
        await chain.add_session(session.session_id)

        # Create notification
        notification_title = "Counseling Session Scheduled"
        notification_desc = f"A counseling session has been scheduled for you on {scheduled_time.strftime('%Y-%m-%d %H:%M')} timezone.utc."
        await create_notification(employee_id, notification_title, notification_desc)

        # Prepare email content
        email_body = f"""Dear {employee.name},

A counseling session has been scheduled for you based on our employee wellness program.

Session Details:
- Date: {scheduled_time.strftime('%Y-%m-%d')}
- Time: {scheduled_time.strftime('%H:%M')} timezone.utc
- Session ID: {session.session_id}
- Chain ID: {chain.chain_id}

Please make sure to attend the session at the scheduled time. If you need to reschedule, please contact your HR representative.

Best regards,
HR Team"""

        # Send email notification
        await send_new_session_email(employee.email, email_body)

        logger.info(f"Chain and session scheduled for employee {employee_id}")
        return session

    except Exception as e:
        logger.error(f"Error scheduling session for employee {employee_id}: {str(e)}")
        return None

async def run_employee_selection():
    """Run the employee selection process and schedule sessions."""
    try:
        # Generate employee_data.json from database
        if not await generate_employee_data_json():
            logger.error("Failed to generate employee_data.json")
            return
        
        # Read employee data from the generated JSON file
        with open('employee_data.json', 'r') as f:
            employee_data = json.load(f)
        
        # Run the selection process
        selected_employees = select_employees(employee_data)
        
        # for every selected employee, check if they have a chain
        for employee_id in selected_employees:
            # check if the employee has a chain
            chain = await Chain.find_one({"employee_id": employee_id, "status": ChainStatus.ACTIVE})
            if chain:
                continue
            
            chain = await Chain.find_one({"employee_id": employee_id})
            # get the last session in the chain
            last_session = await Session.find_one({"session_id": chain.session_ids[-1]})

            # check if the last session's created at is less than 14 days ago
            if last_session.created_at > datetime.now(timezone.utc) - timedelta(days=14):
                continue

            await create_chain(
                employee_id=employee_id,
                notes="Automatically created counseling chain",
                scheduled_time=datetime.now(timezone.utc)
            )
        
        # Log the results
        logger.info(f"Employee selection completed at {datetime.now(timezone.utc)}")
        logger.info(f"Selected {len(selected_employees)} employees for counseling")
        
    except Exception as e:
        logger.error(f"Error in employee selection process: {str(e)}")
        raise e

async def run_deadline_check():
    """Run the deadline check process."""
    try:
        # Get all sessions that are pending and have a scheduled_at date in the past
        pending_sessions = await Session.find({
            "status": SessionStatus.PENDING,
            "scheduled_at": {"$lte": datetime.now(timezone.utc)}
        }).to_list()

        # check if the scheduled_at is past +2 days 
        for session in pending_sessions:
            if session.scheduled_at < datetime.now(timezone.utc) - timedelta(days=1):
                # get the employee details
                employee = await Employee.find_one({"employee_id": session.user_id})

                # send a notification to the employee
                await send_deadline_reminder_email(employee.email)
            elif session.scheduled_at < datetime.now(timezone.utc) - timedelta(days=2):
                # send a notification to the employee
                await send_deadline_over_email(employee.email)
                # escalate the chain
                chain = await Chain.find_one({"session_ids": {"$in": [session.session_id]}})
                if chain:
                    await chain.escalate_chain(reason=f"Chain escalated because the employee didn't complete the session within the deadline")
        
        active_sessions = await Session.find({
            "status": SessionStatus.ACTIVE
        }).to_list()

        for session in active_sessions:
            if session.scheduled_at < datetime.now(timezone.utc) - timedelta(days=1):
                employee = await Employee.find_one({"employee_id": session.user_id})
                await send_deadline_reminder_email(employee.email)
            elif session.scheduled_at < datetime.now(timezone.utc) - timedelta(days=2):
                continue
            else:
                chats = await Chat.find({
                    "chat_id": session.chat_id
                }).to_list()

                # get the last message from the chat
                last_message = chats[-1].messages[-1]
                # if the session deadline is over, but the last message is within an hour don't cancel the session
                if last_message.timestamp > session.scheduled_at + timedelta(days=2) - timedelta(hours=1):
                    continue
                
                chain = await Chain.find_one({"session_ids": {"$in": [session.session_id]}})
                if chain:
                    await chain.escalate_chain(reason=f"Chain escalated because the employee didn't complete the session within the deadline")

    except Exception as e:
        logger.error(f"Error in deadline check process: {str(e)}")
        raise e

# clear notifications which are older than 10 days
async def clear_notifications():
    """Clear notifications which are older than 10 days."""
    try:
        # Get all notifications older than 10 days
        notifications = await Notification.find({
            "created_at": {"$lte": datetime.now(timezone.utc) - timedelta(days=10)}
        }).to_list()

        # delete the notifications
        for notification in notifications:
            await notification.delete()

        logger.info(f"Cleared {len(notifications)} notifications")
    except Exception as e:
        logger.error(f"Error in clearing notifications: {str(e)}")
        raise e


def setup_scheduler():
    """Set up the scheduler to run employee selection."""
    try:
        scheduler = AsyncIOScheduler()
    
    # For production: Run at 9:00 AM every day
        scheduler.add_job(
            run_employee_selection,
            trigger=CronTrigger(hour=9, minute=0),
            id='employee_selection',
            name='Daily Employee Selection',
            replace_existing=True
        )

        # For production: Run at 9:00 AM every day
        scheduler.add_job(
            run_deadline_check,
            trigger=CronTrigger(hour=9, minute=0),
            id='deadline_check',
            name='Daily Deadline Check',
            replace_existing=True
        )

        # clear notifications which are older than 10 days at 12:00 AM every day
        scheduler.add_job(
            clear_notifications,
            trigger=CronTrigger(hour=0, minute=0),
            id='clear_notifications',
            name='Clear Notifications',
            replace_existing=True
        )
    
        scheduler.start()
        logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error(f"Error in setting up scheduler: {str(e)}")
    return scheduler 