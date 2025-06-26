
import logging
import os
from datetime import datetime, timedelta, time
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
            'cancel': self.handle_cancel_lesson,
            'help': self.handle_help,
            'menu': self.handle_menu
        }
        
        # Initialize Twilio client - will be done later with app context
        self.twilio_client = None
        self.twilio_phone = None
    
    def initialize_twilio(self):
        """Initialize Twilio client with credentials from SystemConfig or environment"""
        try:
            # Try to get credentials from SystemConfig first (only if we have app context)
            account_sid = None
            auth_token = None
            
            try:
                account_sid = SystemConfig.get_config('TWILIO_ACCOUNT_SID')
                auth_token = SystemConfig.get_config('TWILIO_AUTH_TOKEN')
            except Exception:
                # No app context or database not available, try environment variables
                pass
            
            # Fallback to environment variables
            account_sid = account_sid or os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = auth_token or os.getenv('TWILIO_AUTH_TOKEN')
            
            if account_sid and auth_token:
                self.twilio_client = Client(account_sid, auth_token)
                try:
                    self.twilio_phone = SystemConfig.get_config('TWILIO_WHATSAPP_NUMBER')
                except Exception:
                    self.twilio_phone = os.getenv('TWILIO_WHATSAPP_NUMBER')
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
        # Check for cancel with lesson number (e.g., "cancel 1")
        if message.startswith('cancel '):
            parts = message.split()
            if len(parts) >= 2:
                return self.process_cancel_lesson_by_number(student, parts[1])
        
        # Handle numerical menu options
        if message in ['1', '2', '3', '4', '5']:
            return self.handle_menu_option(student, message)
        
        # Handle booking duration selection (30 or 60)
        if message in ['30', '60']:
            return self.handle_duration_selection(student, int(message))
        
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

📋 *Main Menu:*

1️⃣ View upcoming lessons
2️⃣ Book a lesson  
3️⃣ Check your progress
4️⃣ Cancel a lesson
5️⃣ Get help

Just reply with a number (1-5) to get started!

👨‍🏫 Your instructor: {student.instructor.get_full_name() if student.instructor else "Not assigned"}"""
    
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
        """Handle schedule inquiry with instructor availability"""
        # Get student's upcoming lessons
        end_date = datetime.now() + timedelta(days=7)
        upcoming_lessons = Lesson.query.filter(
            Lesson.student_id == student.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.now(),
            Lesson.scheduled_date <= end_date
        ).order_by(Lesson.scheduled_date).all()
        
        # Get instructor's available slots
        instructor = student.instructor
        available_slots = self.get_instructor_available_slots(instructor, days_ahead=7)
        
        response = "📅 *Schedule & Available Times*\n\n"
        
        # Show student's upcoming lessons
        if upcoming_lessons:
            response += "*Your Upcoming Lessons:*\n"
            for lesson in upcoming_lessons:
                date_str = lesson.scheduled_date.strftime('%B %d, %Y')
                time_str = lesson.scheduled_date.strftime('%I:%M %p')
                response += f"• {date_str} at {time_str}\n"
                response += f"  Duration: {lesson.duration_minutes} min\n"
                response += f"  Instructor: {lesson.instructor.get_full_name()}\n\n"
        else:
            response += "You have no upcoming lessons scheduled.\n\n"
        
        # Show instructor's available slots
        if instructor and available_slots:
            response += f"*Available Times with {instructor.get_full_name()}:*\n"
            current_date = None
            slot_count = 0
            
            for slot in available_slots:
                if slot_count >= 10:  # Limit to 10 slots
                    break
                    
                slot_date = slot['start'].date()
                if slot_date != current_date:
                    response += f"\n*{slot['start'].strftime('%A, %B %d')}*\n"
                    current_date = slot_date
                
                start_time = slot['start'].strftime('%I:%M %p')
                end_time = slot['end'].strftime('%I:%M %p')
                response += f"• {start_time} - {end_time}\n"
                slot_count += 1
            
            response += f"\n💡 To book a lesson, reply:\n*book [date] [time]*\n\nExample: *book Dec 25 2:00 PM*"
        else:
            response += "No available time slots found. Contact your instructor directly."
        
        return response
    
    def get_instructor_available_slots(self, instructor, days_ahead=7):
        """Get available time slots for an instructor"""
        if not instructor:
            return []
        
        available_slots = []
        current_date = datetime.now().date()
        
        # Define working hours (6 AM to 4 PM, Monday to Saturday)
        working_hours = {
            0: [(6, 0), (16, 0)],  # Monday
            1: [(6, 0), (16, 0)],  # Tuesday
            2: [(6, 0), (16, 0)],  # Wednesday
            3: [(6, 0), (16, 0)],  # Thursday
            4: [(6, 0), (16, 0)],  # Friday
            5: [(6, 0), (16, 0)],  # Saturday
            6: []  # Sunday (closed)
        }
        
        for day_offset in range(days_ahead):
            check_date = current_date + timedelta(days=day_offset)
            weekday = check_date.weekday()
            
            # Skip if no working hours for this day
            if weekday not in working_hours or not working_hours[weekday]:
                continue
            
            # Get existing lessons for this instructor on this date
            existing_lessons = Lesson.query.filter(
                Lesson.instructor_id == instructor.id,
                Lesson.status == LESSON_SCHEDULED,
                Lesson.scheduled_date >= datetime.combine(check_date, datetime.min.time()),
                Lesson.scheduled_date < datetime.combine(check_date + timedelta(days=1), datetime.min.time())
            ).all()
            
            # Create list of busy time slots
            busy_slots = []
            for lesson in existing_lessons:
                start_time = lesson.scheduled_date
                end_time = start_time + timedelta(minutes=lesson.duration_minutes)
                busy_slots.append((start_time, end_time))
            
            # Generate available slots
            start_hour, start_min = working_hours[weekday][0]
            end_hour, end_min = working_hours[weekday][1]
            
            current_slot = datetime.combine(check_date, time(start_hour, start_min))
            end_of_day = datetime.combine(check_date, time(end_hour, end_min))
            
            while current_slot < end_of_day:
                slot_end = current_slot + timedelta(minutes=60)  # 1-hour slots
                
                # Check if this slot conflicts with existing lessons
                is_available = True
                for busy_start, busy_end in busy_slots:
                    if (current_slot < busy_end and slot_end > busy_start):
                        is_available = False
                        break
                
                # WhatsApp bot booking rules:
                # - Can book tomorrow only after 6 PM today
                # - Booking closes at 3:30 PM on the day
                now = datetime.now()
                slot_date = current_slot.date()
                today = now.date()
                tomorrow = today + timedelta(days=1)
                
                # Check if slot is available based on WhatsApp bot rules
                if is_available and current_slot > now:
                    # If booking for tomorrow, check if it's after 6 PM today
                    if slot_date == tomorrow:
                        if now.hour >= 18:  # After 6 PM, can book tomorrow
                            available_slots.append({
                                'start': current_slot,
                                'end': slot_end
                            })
                    # If booking for today, check if it's before 3:30 PM
                    elif slot_date == today:
                        if now.hour < 15 or (now.hour == 15 and now.minute < 30):  # Before 3:30 PM
                            available_slots.append({
                                'start': current_slot,
                                'end': slot_end
                            })
                
                current_slot += timedelta(minutes=60)  # Move to next hour
        
        return available_slots
    
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
    
    def handle_cancel_lesson(self, student):
        """Handle lesson cancellation request"""
        # Get upcoming lessons that can be cancelled
        upcoming_lessons = Lesson.query.filter(
            Lesson.student_id == student.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.now()
        ).order_by(Lesson.scheduled_date).all()
        
        if not upcoming_lessons:
            return "❌ You have no upcoming lessons to cancel."
        
        response = "📋 *Your Upcoming Lessons:*\n\n"
        response += "To cancel a lesson, reply with:\n*cancel [lesson number]*\n\n"
        
        for i, lesson in enumerate(upcoming_lessons, 1):
            date_str = lesson.scheduled_date.strftime('%B %d, %Y')
            time_str = lesson.scheduled_date.strftime('%I:%M %p')
            instructor_name = lesson.instructor.get_full_name() if lesson.instructor else "No instructor assigned"
            
            response += f"{i}. 🚗 *{lesson.lesson_type.title()}* - {lesson.duration_minutes} min\n"
            response += f"   📅 {date_str} at {time_str}\n"
            response += f"   👨‍🏫 {instructor_name}\n\n"
        
        response += "💡 Example: *cancel 1* (to cancel lesson #1)\n"
        response += "⚠️ Please cancel at least 2 hours before your lesson time."
        
        return response
    
    def process_cancel_lesson_by_number(self, student, lesson_number):
        """Process cancellation of a specific lesson by number"""
        try:
            lesson_num = int(lesson_number)
            
            # Get upcoming lessons
            upcoming_lessons = Lesson.query.filter(
                Lesson.student_id == student.id,
                Lesson.status == LESSON_SCHEDULED,
                Lesson.scheduled_date >= datetime.now()
            ).order_by(Lesson.scheduled_date).all()
            
            if lesson_num < 1 or lesson_num > len(upcoming_lessons):
                return f"❌ Invalid lesson number. You have {len(upcoming_lessons)} upcoming lessons."
            
            lesson = upcoming_lessons[lesson_num - 1]
            
            # Check if cancellation is allowed (at least 2 hours before)
            time_until_lesson = lesson.scheduled_date - datetime.now()
            if time_until_lesson.total_seconds() < 7200:  # 2 hours = 7200 seconds
                return "⚠️ Cannot cancel lessons less than 2 hours before the scheduled time. Please contact your instructor directly."
            
            # Cancel the lesson
            lesson.status = LESSON_CANCELLED
            lesson.updated_at = datetime.now()
            db.session.commit()
            
            date_str = lesson.scheduled_date.strftime('%B %d, %Y')
            time_str = lesson.scheduled_date.strftime('%I:%M %p')
            
            response = f"✅ *Lesson Cancelled Successfully*\n\n"
            response += f"📅 Date: {date_str}\n"
            response += f"🕐 Time: {time_str}\n"
            response += f"⏱️ Duration: {lesson.duration_minutes} minutes\n"
            response += f"👨‍🏫 Instructor: {lesson.instructor.get_full_name()}\n\n"
            response += "Your instructor has been notified. You can reschedule by typing 'schedule'."
            
            logger.info(f"Lesson {lesson.id} cancelled by student {student.name} via WhatsApp")
            return response
            
        except ValueError:
            return "❌ Please provide a valid lesson number. Example: *cancel 1*"
        except Exception as e:
            logger.error(f"Error cancelling lesson: {str(e)}")
            return "❌ Sorry, there was an error cancelling your lesson. Please try again or contact your instructor."
    
    def handle_help(self, student):
        """Handle help request"""
        return """❓ *Help & Commands:*

🔹 Reply with numbers 1-5 for menu options
🔹 *1* - View upcoming lessons
🔹 *2* - Book a lesson (30min or 1 hour)
🔹 *3* - Check your progress
🔹 *4* - Cancel upcoming lessons
🔹 *menu* - Show main menu

💡 *Tips:*
• Lessons are available 6:00 AM - 4:00 PM (Mon-Sat)
• Maximum 2 lessons per day
• Cancel at least 2 hours before lesson time
• Choose 30-minute or 1-hour lessons when booking
• Tomorrow's lessons can be booked after 6:00 PM today

📞 *Need more help?*
Contact your instructor or driving school directly."""
    
    def handle_menu(self, student):
        """Handle menu request"""
        return f"""📋 *Main Menu:*

Choose what you'd like to do:

1️⃣ View upcoming lessons
2️⃣ Book a lesson
3️⃣ Check your progress
4️⃣ Cancel a lesson
5️⃣ Get help

Just reply with a number (1-5) to get started!

👨‍🏫 Your instructor: {student.instructor.get_full_name() if student.instructor else "Not assigned"}"""
    
    def handle_menu_option(self, student, option):
        """Handle numbered menu selections"""
        if option == '1':
            return self.handle_lessons(student)
        elif option == '2':
            return self.handle_book_lesson(student)
        elif option == '3':
            return self.handle_progress(student)
        elif option == '4':
            return self.handle_cancel_lesson(student)
        elif option == '5':
            return self.handle_help(student)
        else:
            return self.handle_default(student)
    
    def handle_book_lesson(self, student):
        """Handle lesson booking - first ask for duration"""
        return """📅 *Book a Lesson*

Please choose your lesson duration:

3️⃣0️⃣ 30 minutes
6️⃣0️⃣ 60 minutes (1 hour)

Reply with *30* or *60* to see available time slots."""
    
    def handle_duration_selection(self, student, duration_minutes):
        """Handle duration selection and show available timeslots"""
        if duration_minutes not in [30, 60]:
            return "❌ Please select either 30 or 60 minutes."
        
        instructor = student.instructor
        if not instructor:
            return "❌ No instructor assigned. Please contact the driving school."
        
        # Get available slots for the selected duration
        available_slots = self.get_duration_specific_timeslots(instructor, duration_minutes)
        
        if not available_slots:
            return f"❌ No {duration_minutes}-minute slots available for the next 2 days.\n\nPlease try again later or contact your instructor."
        
        response = f"📅 *Available {duration_minutes}-minute slots:*\n\n"
        
        current_date = None
        slot_count = 0
        
        for slot in available_slots:
            if slot_count >= 15:  # Limit to 15 slots to avoid message being too long
                break
                
            slot_date = slot['start'].date()
            if slot_date != current_date:
                response += f"\n*{slot['start'].strftime('%A, %B %d')}*\n"
                current_date = slot_date
            
            start_time = slot['start'].strftime('%I:%M %p')
            response += f"• {start_time}\n"
            slot_count += 1
        
        response += f"\n💡 To book a slot, contact your instructor:\n📞 {instructor.get_full_name()}"
        response += f"\n\nType 'menu' to return to the main menu."
        
        return response
    
    def get_duration_specific_timeslots(self, instructor, duration_minutes):
        """Get available timeslots for specific duration (30 or 60 minutes)"""
        if not instructor:
            return []
        
        available_slots = []
        current_time = datetime.now()
        start_date = current_time.date()
        
        # Define working hours (6 AM to 4 PM, Monday to Saturday)
        working_hours = {
            0: (6, 16),   # Monday
            1: (6, 16),   # Tuesday  
            2: (6, 16),   # Wednesday
            3: (6, 16),   # Thursday
            4: (6, 16),   # Friday
            5: (6, 16),   # Saturday
            6: None       # Sunday (closed)
        }
        
        # Check today and tomorrow only
        for day_offset in range(2):
            check_date = start_date + timedelta(days=day_offset)
            weekday = check_date.weekday()
            
            # Skip if no working hours for this day
            if weekday not in working_hours or working_hours[weekday] is None:
                continue
            
            start_hour, end_hour = working_hours[weekday]
            
            # Get existing lessons for this instructor on this date
            existing_lessons = Lesson.query.filter(
                Lesson.instructor_id == instructor.id,
                Lesson.status == LESSON_SCHEDULED,
                Lesson.scheduled_date >= datetime.combine(check_date, datetime.min.time()),
                Lesson.scheduled_date < datetime.combine(check_date + timedelta(days=1), datetime.min.time())
            ).all()
            
            # Create set of busy 30-minute slots
            busy_slots = set()
            for lesson in existing_lessons:
                start_time = lesson.scheduled_date
                # Mark all 30-minute slots this lesson occupies as busy
                slots_needed = (lesson.duration_minutes + 29) // 30  # Round up to nearest 30min
                for i in range(slots_needed):
                    slot_time = start_time + timedelta(minutes=i * 30)
                    busy_slots.add(slot_time.replace(second=0, microsecond=0))
            
            # Generate available slots based on duration
            for hour in range(start_hour, end_hour):
                for minute in [0, 30]:
                    slot_time = datetime.combine(check_date, datetime.min.time().replace(hour=hour, minute=minute))
                    
                    # Skip if slot is in the past
                    if slot_time <= current_time:
                        continue
                    
                    # Check if this slot and required consecutive slots are available
                    slots_needed = 1 if duration_minutes == 30 else 2
                    is_available = True
                    
                    for i in range(slots_needed):
                        check_slot = slot_time + timedelta(minutes=i * 30)
                        if check_slot in busy_slots:
                            is_available = False
                            break
                        # Make sure we don't go past working hours
                        if check_slot.hour >= end_hour:
                            is_available = False
                            break
                    
                    if is_available:
                        # Apply WhatsApp booking time rules
                        slot_date = slot_time.date()
                        today = current_time.date()
                        tomorrow = today + timedelta(days=1)
                        
                        # Check booking rules
                        if slot_date == tomorrow:
                            # Can book tomorrow only after 6 PM today
                            if current_time.hour >= 18:
                                available_slots.append({
                                    'start': slot_time,
                                    'end': slot_time + timedelta(minutes=duration_minutes)
                                })
                        elif slot_date == today:
                            # Can book today only before 3:30 PM
                            if current_time.hour < 15 or (current_time.hour == 15 and current_time.minute < 30):
                                available_slots.append({
                                    'start': slot_time,
                                    'end': slot_time + timedelta(minutes=duration_minutes)
                                })
        
        return available_slots
    
    def handle_default(self, student):
        """Handle unrecognized messages"""
        return f"""I didn't understand that, {student.name}. 🤔

Reply with 'menu' to see available options or '5' for help.

📋 Quick menu:
1️⃣ View lessons | 2️⃣ Book lesson | 3️⃣ Progress | 4️⃣ Cancel | 5️⃣ Help"""
    
    def handle_unknown_student(self, phone_number):
        """Handle messages from unknown phone numbers"""
        return """Sorry, I don't recognize this phone number. 📱

Please make sure you're registered as a student with myInstructor 2.0.

Contact your driving school for assistance with registration."""

# Global bot instance - will be initialized later with app context
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
