from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from models import db, LabBooking, InteractiveClassBooking, Lab, InteractiveClass, SystemLog
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def send_notification_to_frontend(user_id, message_type, data):
    """
    Send notification to frontend via Flask-SocketIO or simple flag in database
    For now, we'll log it and store in a notifications table
    """
    logger.info(f"Notification for User {user_id}: {message_type} - {data}")


def check_lab_bookings_for_confirmation(app=None):
    """
    Check all lab bookings and send 10-minute warning notifications
    Runs every 1 minute to catch all bookings
    """
    if app is not None:
        with app.app_context():
            return _check_lab_bookings_for_confirmation()
    return _check_lab_bookings_for_confirmation()


def _check_lab_bookings_for_confirmation():
    logger.info("Checking lab bookings for 10-minute warnings...")
    
    now = datetime.utcnow()
    current_date = now.date()
    
    bookings = LabBooking.query.filter_by(status='pending').all()
    
    for booking in bookings:
        if booking.booking_date == current_date:
            booking_datetime = datetime.combine(current_date, booking.booking_time)
            time_until_booking = (booking_datetime - now).total_seconds() / 60
            
            if 9 <= time_until_booking <= 11 and not booking.warning_sent:
                logger.info(f"Sending 10-min warning for booking {booking.id}")
                send_notification_to_frontend(
                    booking.teacher_id,
                    "lab_warning",
                    {
                        "booking_id": booking.id,
                        "lab_name": booking.lab.name,
                        "message": f"Your lab class '{booking.lab.name}' is about to start in 10 minutes. Please confirm the booking."
                    }
                )
                booking.warning_sent = True
                db.session.commit()


def check_lab_bookings_start_time(app=None):
    """
    Check if bookings have started and send start notification
    Runs every 1 minute
    """
    if app is not None:
        with app.app_context():
            return _check_lab_bookings_start_time()
    return _check_lab_bookings_start_time()


def _check_lab_bookings_start_time():
    logger.info("Checking for booking start times...")
    
    now = datetime.utcnow()
    current_date = now.date()
    
    bookings = LabBooking.query.filter_by(status='pending').all()
    
    for booking in bookings:
        if booking.booking_date == current_date:
            booking_datetime = datetime.combine(current_date, booking.booking_time)
            time_difference = (booking_datetime - now).total_seconds() / 60
            
            if -1 <= time_difference <= 1:
                logger.info(f"Booking {booking.id} has started - sending start notification")
                send_notification_to_frontend(
                    booking.teacher_id,
                    "lab_started",
                    {
                        "booking_id": booking.id,
                        "lab_name": booking.lab.name,
                        "message": f"Your lab class '{booking.lab.name}' has started! Please confirm the lab is engaged."
                    }
                )


def auto_cancel_unconfirmed_bookings(app=None):
    """
    15-Minute Auto-Cancel Rule:
    If teacher doesn't click "Engaged" within 15 minutes, auto-cancel the booking
    Runs every 1 minute
    """
    if app is not None:
        with app.app_context():
            return _auto_cancel_unconfirmed_bookings()
    return _auto_cancel_unconfirmed_bookings()


def _auto_cancel_unconfirmed_bookings():
    logger.info("Checking for auto-cancel conditions...")
    
    now = datetime.utcnow()
    
    bookings = LabBooking.query.filter_by(status='pending').all()
    
    for booking in bookings:
        booking_datetime = datetime.combine(booking.booking_date, booking.booking_time)
        minutes_since_start = (now - booking_datetime).total_seconds() / 60
        
        if minutes_since_start > 15:
            logger.warning(f"Auto-cancelling booking {booking.id} (15 mins exceeded)")
            booking.status = 'cancelled'
            booking.cancelled_at = now
            booking.lab.status = 'free'
            log_entry = SystemLog(
                action='auto_cancel_lab_booking',
                user_id=booking.teacher_id,
                details=f'Lab booking {booking.id} auto-cancelled after 15 minutes'
            )
            db.session.add(log_entry)
            send_notification_to_frontend(
                booking.teacher_id,
                "lab_cancelled",
                {
                    "booking_id": booking.id,
                    "lab_name": booking.lab.name,
                    "message": f"Your lab booking for '{booking.lab.name}' was auto-cancelled (15-minute confirmation timeout)."
                }
            )
            db.session.commit()


def auto_cancel_interactive_unconfirmed_bookings(app=None):
    """
    Same 15-minute rule for interactive class bookings
    """
    if app is not None:
        with app.app_context():
            return _auto_cancel_interactive_unconfirmed_bookings()
    return _auto_cancel_interactive_unconfirmed_bookings()


def _auto_cancel_interactive_unconfirmed_bookings():
    logger.info("Checking interactive class bookings for auto-cancel...")
    
    now = datetime.utcnow()
    bookings = InteractiveClassBooking.query.filter_by(status='pending').all()
    
    for booking in bookings:
        booking_datetime = datetime.combine(booking.booking_date, booking.booking_time)
        minutes_since_start = (now - booking_datetime).total_seconds() / 60
        
        if minutes_since_start > 15:
            logger.warning(f"Auto-cancelling interactive booking {booking.id}")
            booking.status = 'cancelled'
            booking.cancelled_at = now
            booking.interactive_class.status = 'free'
            log_entry = SystemLog(
                action='auto_cancel_interactive_booking',
                user_id=booking.teacher_id,
                details=f'Interactive class booking {booking.id} auto-cancelled after 15 minutes'
            )
            db.session.add(log_entry)
            send_notification_to_frontend(
                booking.teacher_id,
                "interactive_cancelled",
                {
                    "booking_id": booking.id,
                    "class_name": booking.interactive_class.name,
                    "message": f"Your interactive class booking for '{booking.interactive_class.name}' was auto-cancelled."
                }
            )
            db.session.commit()


def start_scheduler(app):
    """Initialize and start the APScheduler"""
    # Schedule jobs with the Flask app passed in so each job can create its own context.
    scheduler.add_job(
        check_lab_bookings_for_confirmation,
        'interval',
        minutes=1,
        id='lab_warning_check',
        name='Check lab bookings for 10-min warning',
        args=[app]
    )
    
    scheduler.add_job(
        check_lab_bookings_start_time,
        'interval',
        minutes=1,
        id='lab_start_check',
        name='Check lab booking start times',
        args=[app]
    )
    
    scheduler.add_job(
        auto_cancel_unconfirmed_bookings,
        'interval',
        minutes=1,
        id='lab_auto_cancel',
        name='Auto-cancel unconfirmed lab bookings',
        args=[app]
    )
    
    scheduler.add_job(
        auto_cancel_interactive_unconfirmed_bookings,
        'interval',
        minutes=1,
        id='interactive_auto_cancel',
        name='Auto-cancel unconfirmed interactive bookings',
        args=[app]
    )
    
    scheduler.start()
    logger.info("APScheduler started successfully!")
