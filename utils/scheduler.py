from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from employee_filtering.blackbox import select_employees
from models.session import Session, SessionStatus
from models.employee import Employee
from models.chat import Chat
from models.notification import Notification, NotificationStatus
from utils.utils import send_email
import json
from datetime import datetime, timedelta, UTC
import logging
import uuid
import os

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

async def get_employees_in_cooldown():
    """Get list of employees who have had sessions in the cooldown period."""
    try:
        cooldown_date = datetime.now(UTC) - timedelta(days=COOLDOWN_PERIOD_DAYS)
        print('cooldown date: ', cooldown_date)
        # Find all sessions completed after the cooldown date
        recent_sessions = await Session.find({
            "created_at": {"$gte": cooldown_date}
        }).to_list()
        
        # Extract unique employee IDs from recent sessions
        employees_in_cooldown = set(session.user_id for session in recent_sessions)
        
        logger.info(f"Found {len(employees_in_cooldown)} employees in cooldown period")
        return employees_in_cooldown
    except Exception as e:
        logger.error(f"Error getting employees in cooldown: {str(e)}")
        return set()

async def create_notification(employee_id: str, title: str, description: str):
    """Create a notification for an employee."""
    try:
        notification = Notification(
            employee_id=employee_id,
            title=title,
            description=description,
            status=NotificationStatus.UNREAD
        )
        await notification.save()
        logger.info(f"Created notification for employee {employee_id}")
        return notification
    except Exception as e:
        logger.error(f"Error creating notification for employee {employee_id}: {str(e)}")
        return None

async def schedule_session_and_notify(employee_id: str):
    """Schedule a counseling session for an employee and send notifications."""
    try:
        # Get employee details
        employee = await Employee.get_by_id(employee_id)
        if not employee:
            logger.error(f"Employee not found: {employee_id}")
            return

        # Create a new chat for the session
        chat = Chat(
            chat_id=f"CHAT{uuid.uuid4().hex[:6].upper()}",
            user_id=employee_id,
            created_at=datetime.now(UTC)
        )
        await chat.save()

        # Schedule session for tomorrow at 10 AM
        tomorrow = datetime.now(UTC) + timedelta(days=1)
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

        # Create notification
        notification_title = "Counseling Session Scheduled"
        notification_desc = f"A counseling session has been scheduled for you on {scheduled_time.strftime('%Y-%m-%d %H:%M')} UTC."
        await create_notification(employee_id, notification_title, notification_desc)

        # Prepare email content
        email_subject = "Counseling Session Scheduled"
        email_body = f"""Dear {employee.name},

A counseling session has been scheduled for you based on our employee wellness program.

Session Details:
- Date: {scheduled_time.strftime('%Y-%m-%d')}
- Time: {scheduled_time.strftime('%H:%M')} UTC
- Session ID: {session.session_id}

Please make sure to attend the session at the scheduled time. If you need to reschedule, please contact your HR representative.

Best regards,
HR Team"""

        # Send email notification
        await send_email(employee.email, email_body)

        logger.info(f"Session scheduled and notification sent for employee {employee_id}")
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
        
        # Get employees who are in cooldown period
        employees_in_cooldown = await get_employees_in_cooldown()
        
        # Filter out employees who are in cooldown period
        eligible_employees = [emp_id for emp_id in selected_employees if emp_id not in employees_in_cooldown]
        
        # Log the results
        logger.info(f"Employee selection completed at {datetime.now(UTC)}")
        logger.info(f"Selected {len(selected_employees)} employees for counseling")
        logger.info(f"{len(employees_in_cooldown)} employees in cooldown period")
        logger.info(f"{len(eligible_employees)} employees eligible for scheduling")
        logger.info(f"Eligible employee IDs: {eligible_employees}")

        # Schedule sessions for eligible employees
        for employee_id in eligible_employees:
            session = await schedule_session_and_notify(employee_id)
            if session:
                logger.info(f"Session scheduled for employee {employee_id}: {session.session_id}")
            else:
                logger.error(f"Failed to schedule session for employee {employee_id}")
        
    except Exception as e:
        logger.error(f"Error in employee selection process: {str(e)}")

def setup_scheduler():
    """Set up the scheduler to run employee selection."""
    scheduler = AsyncIOScheduler()
    
    # For testing: Run every 15 seconds
    scheduler.add_job(
        run_employee_selection,
        trigger=IntervalTrigger(minutes=2),
        # trigger=IntervalTrigger(seconds=15),
        id='employee_selection',
        name='Minute Employee Selection',
        replace_existing=True
    )
    
    # For production: Run at 9:00 AM every day
    # scheduler.add_job(
    #     run_employee_selection,
    #     trigger=CronTrigger(hour=9, minute=0),
    #     id='employee_selection',
    #     name='Daily Employee Selection',
    #     replace_existing=True
    # )
    
    scheduler.start()
    logger.info("Scheduler started successfully")
    return scheduler 