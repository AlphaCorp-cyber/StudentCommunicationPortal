
import logging
import os
from datetime import datetime, timedelta
from flask import request, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from models import Student, Lesson, WhatsAppSession, db, LESSON_SCHEDULED, LESSON_COMPLETED, SystemConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WhatsAppBot:
    def __init__(self):
        self.commands = {
            'hi': self.handle_greeting,
            'hello': self.handle_greeting,
            'lessons': self.handle_lessons,
            'schedule': self.handle_schedule,
            'progress': self.handle_progress,
            'help': self.handle_help,
            'menu': self.handle_menu
        }
        
        # Initialize Twilio client
        self.twilio_client = None
        self.initialize_twilio()
    
    def initialize_twilio(self):
        """Initialize Twilio client with credentials from SystemConfig or environment"""
        try:
            # Try to get credentials from SystemConfig first
            account_sid = SystemConfig.get_config('TWILIO_ACCOUNT_SID') or os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = SystemConfig.get_config('TWILIO_AUTH_TOKEN') or os.getenv('TWILIO_AUTH_TOKEN')
            
            if account_sid and auth_token:
                self.twilio_client = Client(account_sid, auth_token)
                self.twilio_phone = SystemConfig.get_config('TWILIO_WHATSAPP_NUMBER') or os.getenv('TWILIO_WHATSAPP_NUMBER')
                logger.info("Twilio client initialized successfully")
            else:
                logger.warning("Twilio credentials not found. WhatsApp messaging will be in mock mode.")
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {str(e)}")
            self.twilio_client = None
    
    def process_message(self, phone_number, message):
        """Process incoming WhatsApp message"""
        try:
            # Clean phone number format
            phone_number = self.clean_phone_number(phone_number)
            
            # Find student by phone number
            student = Student.query.filter_by(phone=phone_number, is_active=True).first()
            
            if not student:
                return self.handle_unknown_student(phone_number)
            
            # Update or create WhatsApp session
            self.update_session(student, message)
            
            # Process message
            response = self.handle_message(student, message.lower().strip())
            
            logger.info(f"WhatsApp message processed for {student.name}: {message}")
            return response
            
        except Exception as e:
            logger.error(f"Error processing WhatsApp message: {str(e)}")
            return "Sorry, I'm having trouble right now. Please try again later."
    
    def clean_phone_number(self, phone):
        """Clean and format phone number"""
        # Remove all non-digit characters
        clean = ''.join(filter(str.isdigit, phone))
        
        # Add Zimbabwe country code if not present
        if not clean.startswith('263'):
            if clean.startswith('0'):
                clean = '263' + clean[1:]
            else:
                clean = '263' + clean
        
        return '+' + clean
    
    def update_session(self, student, message):
        """Update or create WhatsApp session"""
        session_id = f"whatsapp_{student.phone}_{datetime.now().strftime('%Y%m%d')}"
        session = WhatsAppSession.query.filter_by(session_id=session_id).first()
        
        if not session:
            session = WhatsAppSession(
                student_id=student.id,
                session_id=session_id
            )
            db.session.add(session)
        
        session.last_message = message
        session.last_activity = datetime.now()
        session.is_active = True
        
        db.session.commit()
    
    def handle_message(self, student, message):
        """Handle incoming message and route to appropriate handler"""
        # Check for specific commands
        for command, handler in self.commands.items():
            if command in message:
                return handler(student)
        
        # Default response if no command matches
        return self.handle_default(student)
    
    def handle_greeting(self, student):
        """Handle greeting messages"""
        return f"""Hello {student.name}! 👋

Welcome to myInstructor 2.0 WhatsApp Bot!

I can help you with:
📅 View your lessons
📊 Check your progress
🕐 Get your schedule
❓ Get help

Type 'menu' to see all options or 'help' for assistance."""
    
    def handle_lessons(self, student):
        """Handle lessons inquiry"""
        # Get upcoming lessons
        upcoming_lessons = Lesson.query.filter(
            Lesson.student_id == student.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.now()
        ).order_by(Lesson.scheduled_date).limit(5).all()
        
        if not upcoming_lessons:
            return "📅 You have no upcoming lessons scheduled.\n\nContact your instructor to schedule lessons!"
        
        response = f"📅 *Your Upcoming Lessons:*\n\n"
        
        for lesson in upcoming_lessons:
            date_str = lesson.scheduled_date.strftime('%Y-%m-%d')
            time_str = lesson.scheduled_date.strftime('%H:%M')
            instructor_name = lesson.instructor.get_full_name() if lesson.instructor else "No instructor assigned"
            
            response += f"🚗 *{lesson.lesson_type.title()}* - {lesson.duration_minutes} min\n"
            response += f"📅 Date: {date_str}\n"
            response += f"🕐 Time: {time_str}\n"
            response += f"👨‍🏫 Instructor: {instructor_name}\n"
            if lesson.location:
                response += f"📍 Location: {lesson.location}\n"
            response += "\n"
        
        return response
    
    def handle_schedule(self, student):
        """Handle schedule inquiry"""
        # Get lessons for the next 7 days
        end_date = datetime.now() + timedelta(days=7)
        upcoming_lessons = Lesson.query.filter(
            Lesson.student_id == student.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.now(),
            Lesson.scheduled_date <= end_date
        ).order_by(Lesson.scheduled_date).all()
        
        if not upcoming_lessons:
            return "📅 No lessons scheduled for the next 7 days.\n\nContact your instructor to schedule lessons!"
        
        response = f"📅 *Your 7-Day Schedule:*\n\n"
        
        current_date = None
        for lesson in upcoming_lessons:
            lesson_date = lesson.scheduled_date.date()
            
            if current_date != lesson_date:
                current_date = lesson_date
                response += f"📅 *{lesson_date.strftime('%A, %B %d')}*\n"
            
            time_str = lesson.scheduled_date.strftime('%H:%M')
            response += f"  🕐 {time_str} - {lesson.lesson_type.title()} ({lesson.duration_minutes}min)\n"
            if lesson.location:
                response += f"  📍 {lesson.location}\n"
        
        return response
    
    def handle_progress(self, student):
        """Handle progress inquiry"""
        completed_lessons = student.lessons_completed
        total_required = student.total_lessons_required
        progress_percentage = student.get_progress_percentage()
        
        # Get recent completed lessons
        recent_completed = Lesson.query.filter(
            Lesson.student_id == student.id,
            Lesson.status == LESSON_COMPLETED
        ).order_by(Lesson.completed_date.desc()).limit(3).all()
        
        response = f"📊 *Your Learning Progress:*\n\n"
        response += f"✅ Completed: {completed_lessons} / {total_required} lessons\n"
        response += f"📈 Progress: {progress_percentage:.1f}%\n"
        response += f"🎯 License Type: {student.license_type}\n\n"
        
        if recent_completed:
            response += "*Recent Completed Lessons:*\n"
            for lesson in recent_completed:
                date_str = lesson.completed_date.strftime('%Y-%m-%d')
                response += f"✅ {lesson.lesson_type.title()} - {date_str}"
                if lesson.rating:
                    response += f" ⭐ {lesson.rating}/5"
                response += "\n"
        
        remaining = total_required - completed_lessons
        if remaining > 0:
            response += f"\n🎯 {remaining} lessons remaining to complete your course!"
        else:
            response += f"\n🎉 Congratulations! You've completed all required lessons!"
        
        return response
    
    def handle_help(self, student):
        """Handle help request"""
        return """❓ *Help & Commands:*

🔹 *hi/hello* - Get a greeting
🔹 *lessons* - View upcoming lessons
🔹 *schedule* - See 7-day schedule
🔹 *progress* - Check your progress
🔹 *menu* - Show main menu
🔹 *help* - Show this help

💡 *Tips:*
• Lessons are available 6:00 AM - 4:00 PM
• Maximum 2 lessons per day
• Lessons are 30min or 1 hour (combined)

📞 *Need more help?*
Contact your instructor or driving school directly."""
    
    def handle_menu(self, student):
        """Handle menu request"""
        return """📋 *Main Menu:*

Choose what you'd like to do:

1️⃣ View upcoming lessons (type: lessons)
2️⃣ Check your schedule (type: schedule)
3️⃣ See your progress (type: progress)
4️⃣ Get help (type: help)

Just type any of the keywords to get started!

👨‍🏫 Your instructor: """ + (student.instructor.get_full_name() if student.instructor else "Not assigned")
    
    def handle_default(self, student):
        """Handle unrecognized messages"""
        return f"""I didn't understand that, {student.name}. 🤔

Type 'menu' to see available options or 'help' for assistance.

Available commands: lessons, schedule, progress, help, menu"""
    
    def handle_unknown_student(self, phone_number):
        """Handle messages from unknown phone numbers"""
        return """Sorry, I don't recognize this phone number. 📱

Please make sure you're registered as a student with myInstructor 2.0.

Contact your driving school for assistance with registration."""

# Global bot instance
whatsapp_bot = WhatsAppBot()

def webhook_handler():
    """Handle incoming WhatsApp webhooks from Twilio"""
    try:
        # Get Twilio webhook data
        from_number = request.form.get('From', '')
        message_body = request.form.get('Body', '')
        
        if from_number and message_body:
            # Clean the phone number (remove whatsapp: prefix)
            clean_phone = from_number.replace('whatsapp:', '')
            
            # Process the message
            response_text = whatsapp_bot.process_message(clean_phone, message_body)
            
            # Create TwiML response
            twiml_response = MessagingResponse()
            twiml_response.message(response_text)
            
            logger.info(f"Processed WhatsApp message from {clean_phone}: {message_body}")
            
            return str(twiml_response), 200, {'Content-Type': 'text/xml'}
        
        return jsonify({'error': 'Missing required parameters'}), 400
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        # Return empty TwiML response on error
        twiml_response = MessagingResponse()
        return str(twiml_response), 500, {'Content-Type': 'text/xml'}

def send_whatsapp_message(phone_number, message):
    """Send WhatsApp message via Twilio"""
    try:
        if not whatsapp_bot.twilio_client:
            logger.warning(f"Twilio not configured. Mock sending to {phone_number}: {message}")
            return False
        
        if not whatsapp_bot.twilio_phone:
            logger.error("Twilio WhatsApp number not configured")
            return False
        
        # Clean phone number format
        clean_phone = whatsapp_bot.clean_phone_number(phone_number)
        
        # Send message via Twilio
        message_instance = whatsapp_bot.twilio_client.messages.create(
            body=message,
            from_=f'whatsapp:{whatsapp_bot.twilio_phone}',
            to=f'whatsapp:{clean_phone}'
        )
        
        logger.info(f"WhatsApp message sent successfully to {clean_phone}, SID: {message_instance.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {phone_number}: {str(e)}")
        return False

def send_lesson_reminder(lesson):
    """Send lesson reminder to student"""
    if not lesson.student.phone:
        return False
    
    message = f"""🔔 *Lesson Reminder*

Hi {lesson.student.name}!

You have a {lesson.lesson_type} lesson scheduled:

📅 Date: {lesson.scheduled_date.strftime('%Y-%m-%d')}
🕐 Time: {lesson.scheduled_date.strftime('%H:%M')}
⏱️ Duration: {lesson.duration_minutes} minutes
👨‍🏫 Instructor: {lesson.instructor.get_full_name()}
📍 Location: {lesson.location or 'TBA'}

Please be on time! 🚗"""
    
    return send_whatsapp_message(lesson.student.phone, message)

def send_lesson_confirmation(lesson):
    """Send lesson confirmation to student"""
    if not lesson.student.phone:
        return False
    
    message = f"""✅ *Lesson Confirmed*

Hi {lesson.student.name}!

Your lesson has been scheduled:

📅 Date: {lesson.scheduled_date.strftime('%Y-%m-%d')}
🕐 Time: {lesson.scheduled_date.strftime('%H:%M')}
⏱️ Duration: {lesson.duration_minutes} minutes
👨‍🏫 Instructor: {lesson.instructor.get_full_name()}
📍 Location: {lesson.location or 'TBA'}

We'll send you a reminder before your lesson. Good luck! 🚗"""
    
    return send_whatsapp_message(lesson.student.phone, message)
