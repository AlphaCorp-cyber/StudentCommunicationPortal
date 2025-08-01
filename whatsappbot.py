import logging
import os
import json
from datetime import datetime, timedelta
import time
import base64
from flask import request, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy import and_
from models import User, Student, Lesson, WhatsAppSession, db, LESSON_SCHEDULED, LESSON_COMPLETED, LESSON_CANCELLED, SystemConfig

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
            'menu': self.handle_menu,
            'instructors': self.handle_find_instructors,
            'profile': self.handle_profile_management,
            'location': self.handle_change_location,
            'balance': self.handle_check_balance,
            'fund': self.handle_fund_account,
            'emergency': self.handle_emergency_contact
        }

        # Initialize Twilio client - will be done later with app context
        self.twilio_client = None
        self.twilio_phone = None

    def get_bot_number(self):
        """Get bot's WhatsApp number for tap-to-send links"""
        try:
            # Try to get from SystemConfig first
            bot_number = SystemConfig.get_config('TWILIO_WHATSAPP_NUMBER')
            if bot_number:
                return bot_number.replace('+', '').replace('whatsapp:', '')

            # Try from environment
            if self.twilio_phone:
                return self.twilio_phone.replace('+', '').replace('whatsapp:', '')

            # Try from environment variable
            import os
            env_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
            if env_number:
                return env_number.replace('+', '').replace('whatsapp:', '')

        except Exception as e:
            logger.error(f"Error getting bot number: {str(e)}")

        # Return your actual number as fallback
        return "263719092710"  # Your actual WhatsApp number

    def initialize_twilio(self):
        """Initialize Twilio client with credentials from environment variables or SystemConfig"""
        try:
            # Load environment variables first (from .env file)
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')

            # Try to get credentials from SystemConfig as fallback (only if we have app context)
            if not account_sid or not auth_token:
                try:
                    account_sid = account_sid or SystemConfig.get_config('TWILIO_ACCOUNT_SID')
                    auth_token = auth_token or SystemConfig.get_config('TWILIO_AUTH_TOKEN')
                except Exception:
                    # No app context or database not available
                    pass

            if account_sid and auth_token and account_sid != 'your_twilio_account_sid_here' and auth_token != 'your_auth_token_here':
                self.twilio_client = Client(account_sid, auth_token)

                # Get phone number from environment or SystemConfig
                self.twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
                if not self.twilio_phone:
                    try:
                        self.twilio_phone = SystemConfig.get_config('TWILIO_WHATSAPP_NUMBER')
                    except Exception:
                        self.twilio_phone = None

                logger.info("✅ Twilio client initialized successfully - LIVE MODE")
                logger.info(f"📞 Using Twilio phone: {self.twilio_phone}")
                logger.info("🎯 Quick Reply buttons will be available")
            else:
                logger.warning("⚠️  Twilio credentials not found. WhatsApp messaging will be in MOCK mode.")
                logger.warning("📝 Please update your .env file with real Twilio credentials:")
                logger.warning("   TWILIO_ACCOUNT_SID=your_actual_account_sid")
                logger.warning("   TWILIO_AUTH_TOKEN=your_actual_auth_token")
                logger.warning("💡 Quick Reply buttons only work with real Twilio credentials")
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {str(e)}")
            self.twilio_client = None

    def process_message(self, phone_number, message):
        """Process incoming WhatsApp message for both students and instructors"""
        try:
            # Clean phone number format
            phone_number = self.clean_phone_number(phone_number)

            # First check if it's an instructor
            instructor = User.query.filter_by(phone=phone_number, active=True).filter(
                User.role.in_(['instructor', 'admin', 'super_admin'])
            ).first()

            if instructor:
                # Handle instructor message
                response = self.handle_instructor_message(instructor, message.lower().strip())
                logger.info(f"WhatsApp message processed for instructor {instructor.get_full_name()}: {message}")
                return response

            # Check if it's a student
            student = Student.query.filter_by(phone=phone_number, is_active=True).first()

            if student:
                # Update or create WhatsApp session
                self.update_session(student, message)

                # Process student message
                response = self.handle_message(student, message.lower().strip())
                logger.info(f"WhatsApp message processed for student {student.name}: {message}")
                return response

            # Check if this is an ongoing registration
            registration_state = self.get_registration_state(phone_number)
            if registration_state:
                return self.handle_registration_step(phone_number, message, registration_state)
            
            # Unknown number - start registration
            return self.handle_unknown_student(phone_number)

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

        # Check if session is expired (older than 30 minutes)
        if session.last_activity and (datetime.now() - session.last_activity).total_seconds() > 1800:
            # Clear any booking context if session expired
            if session.last_message and session.last_message.startswith('BOOKING_CONTEXT:'):
                session.last_message = "session_expired"

        # DON'T overwrite last_message if it contains state information
        # Only update if it's a regular message, not state data
        if not (session.last_message and (
            session.last_message == 'awaiting_duration' or 
            session.last_message.startswith('BOOKING_CONTEXT:') or
            session.last_message == 'showing_cancel_options'
        )):
            session.last_message = message

        session.last_activity = datetime.now()
        session.is_active = True

        db.session.commit()

    def handle_message(self, student, message):
        """Handle incoming message and route to appropriate handler"""
        # Extract command from WhatsApp URL if message contains wa.me link
        original_message = message
        if 'wa.me/' in message and 'text=' in message:
            try:
                # Extract the text parameter from the URL
                import urllib.parse
                if '?text=' in message:
                    text_part = message.split('?text=')[1]
                    # Handle URL encoding and get the actual command
                    message = urllib.parse.unquote(text_part).split('&')[0]
                    logger.info(f"Extracted command '{message}' from URL: {original_message}")
            except Exception as e:
                logger.error(f"Error extracting command from URL: {str(e)}")
                # If extraction fails, continue with original message
                pass

        # Reset/restart commands to clear any stuck state - always available
        if message in ['reset', 'restart', 'start', 'clear', 'menu', 'back', 'home']:
            return self.reset_session_and_start(student)

        # Get current session state
        session_state = self.get_session_state(student)
        logger.info(f"Current session state for {student.name}: {session_state}, message: '{message}'")

        # Check for cancel with lesson number (e.g., "cancel 1")
        if message.startswith('cancel '):
            parts = message.split()
            if len(parts) >= 2:
                return self.process_cancel_lesson_by_number(student, parts[1])

        # Check for instructor selection (e.g., "select 1")
        if message.startswith('select '):
            parts = message.split()
            if len(parts) >= 2:
                return self.process_instructor_selection(student, parts[1])

        # Check for timeslot booking (e.g., "book 1" or "book 5")
        if message.startswith('book '):
            parts = message.split()
            if len(parts) >= 2:
                return self.process_timeslot_booking(student, parts[1])

        # Context-aware message handling based on session state
        if session_state == 'awaiting_location_update':
            return self.process_location_update(student, message)
        elif session_state == 'awaiting_email_update':
            return self.process_email_update(student, message)
        elif session_state == 'awaiting_instructor_selection':
            return self.process_instructor_selection(student, message)
        elif session_state == 'awaiting_duration':
            # Handle numbered choices for duration (1=30min, 2=60min, 3=menu)
            if message == '1':
                return self.handle_duration_selection(student, 30)
            elif message == '2':
                return self.handle_duration_selection(student, 60)
            elif message == '3' or message == 'menu':
                return self.reset_session_and_start(student)
            # Also accept direct duration values
            elif message in ['30', '60']:
                return self.handle_duration_selection(student, int(message))
            else:
                return self.handle_duration_selection_error(student, message)

        elif session_state == 'awaiting_booking_slot':
            if message.startswith('book '):
                parts = message.split()
                if len(parts) >= 2:
                    return self.process_timeslot_booking(student, parts[1])
            # Try to parse as just a number
            try:
                slot_num = int(message)
                return self.process_timeslot_booking(student, str(slot_num))
            except ValueError:
                return self.handle_booking_slot_error(student, message)

        # Handle numerical menu options (only when NOT in a specific state)
        if session_state in [None, 'default', 'main_menu'] and message in ['1', '2', '3', '4', '5']:
            return self.handle_menu_option(student, message)

        # Check for word-based commands (more user-friendly)
        message_words = message.lower().split()

        # Check for specific commands - both full words and partial matches
        for command, handler in self.commands.items():
            if command in message or any(word.startswith(command[:3]) for word in message_words if len(word) >= 3):
                return handler(student)

        # Additional easy commands
        if any(word in ['book', 'booking', 'reserve'] for word in message_words):
            return self.handle_book_lesson(student)
        elif any(word in ['view', 'show', 'see'] for word in message_words) and any(word in ['lesson', 'schedule'] for word in message_words):
            return self.handle_lessons(student)
        elif any(word in ['progress', 'status', 'report'] for word in message_words):
            return self.handle_progress(student)
        elif any(word in ['instructor', 'teacher', 'switch'] for word in message_words):
            return self.handle_instructor_switch(student)
        elif any(word in ['email', 'update'] for word in message_words):
            return self.handle_email_update(student)

        # Intelligent fallback - guide user based on context
        return self.handle_contextual_fallback(student, message, session_state)

    def handle_greeting(self, student):
        """Handle greeting messages with interactive buttons"""
        message_body = f"""Hello {student.name}! 👋

Welcome to myInstructor 2.0 WhatsApp Bot!

👨‍🏫 Your instructor: {student.instructor.get_full_name() if student.instructor else "Not assigned"}

Choose an option below:"""

        # Create quick reply buttons
        quick_replies = [
            {"id": "lessons", "title": "📅 View Lessons"},
            {"id": "book", "title": "🎯 Book Lesson"},
            {"id": "progress", "title": "📊 Check Progress"},
            {"id": "help", "title": "❓ Get Help"}
        ]

        return self.send_interactive_message(student.phone, message_body, quick_replies)

    def send_interactive_message(self, phone_number, message_body, quick_replies=None, list_options=None):
        """Send interactive message with Quick Reply buttons using Twilio's Content API"""
        try:
            if not self.twilio_client:
                # In demo mode, return text with options
                logger.info("📱 Running in MOCK mode - no real Twilio client available")
                if quick_replies:
                    reply_text = "\n\n"
                    for idx, reply in enumerate(quick_replies, 1):
                        reply_text += f"{idx}. {reply['title']}\n"
                    reply_text += f"\nReply with {', '.join([str(i) for i in range(1, len(quick_replies)+1)])}"
                    logger.info(f"📝 Mock numbered options: {[r['title'] for r in quick_replies]}")
                    return message_body + reply_text
                elif list_options:
                    list_text = "\n\n*Options:*\n"
                    for idx, option in enumerate(list_options, 1):
                        list_text += f"{idx}. {option['title']}\n"
                    return message_body + list_text
                return message_body

            # Fix phone number formats for WhatsApp
            twilio_phone = self.twilio_phone or os.getenv('TWILIO_PHONE_NUMBER', 'whatsapp:+14155238886')
            if not twilio_phone.startswith('whatsapp:'):
                from_number = f'whatsapp:{twilio_phone}'
            else:
                from_number = twilio_phone

            # Ensure to_number has correct WhatsApp format
            clean_phone = phone_number.replace("+", "").replace("whatsapp:", "")
            to_number = f'whatsapp:+{clean_phone}'

            logger.info(f"📞 Sending from: {from_number} to: {to_number}")

            if quick_replies and len(quick_replies) <= 3:
                # Use simple numbered options - clean and reliable
                try:
                    # Create clean numbered message
                    options_message = f"{message_body}\n\n"

                    for idx, reply in enumerate(quick_replies, 1):
                        options_message += f"{idx}. {reply['title']}\n"

                    options_message += f"\nReply with {', '.join([str(i) for i in range(1, len(quick_replies)+1)])}"

                    # Send the numbered options message
                    message = self.twilio_client.messages.create(
                        from_=from_number,
                        to=to_number,
                        body=options_message
                    )

                    logger.info(f"✅ Numbered options message sent to {phone_number}")
                    return "Message sent successfully"

                except Exception as options_error:
                    logger.warning(f"Numbered options failed: {str(options_error)}")

                    # Fallback to basic text
                    try:
                        fallback_message = message_body + "\n\n"
                        for idx, reply in enumerate(quick_replies, 1):
                            fallback_message += f"{idx}. {reply['title']}\n"
                        fallback_message += "\nReply with number"

                        message = self.twilio_client.messages.create(
                            from_=from_number,
                            to=to_number,
                            body=fallback_message
                        )

                        logger.info(f"✅ Fallback message sent to {phone_number}")
                        return "Message sent successfully"

                    except Exception as text_error:
                        logger.error(f"All message formats failed: {str(text_error)}")

                    # Fallback: Try with approved content template if available
                    try:
                        content_sid = os.getenv('TWILIO_TEMPLATE_SID')
                        if content_sid and content_sid != 'HXf324aa725113107f86055b1cc3d4092a':
                            # Build content variables for the template
                            content_variables = {}
                            for idx, reply in enumerate(quick_replies[:3], 1):
                                content_variables[str(idx)] = reply['title'][:24]

                            # Send using approved template
                            message = self.twilio_client.messages.create(
                                from_=from_number,
                                to=to_number,
                                content_sid=content_sid,
                                content_variables=json.dumps(content_variables)
                            )

                            logger.info(f"✅ Template message sent with SID: {content_sid}")
                            return "Interactive message sent successfully"
                        else:
                            raise Exception("No valid template SID available")

                    except Exception as template_error:
                        logger.warning(f"Template approach failed: {str(template_error)}")

                        # Final fallback to enhanced text with numbered options
                        reply_text = message_body + "\n\n*Quick Options:*\n"
                        for idx, reply in enumerate(quick_replies, 1):
                            reply_text += f"📱 *{idx}* - {reply['title']}\n"
                        reply_text += "\nJust type the number to select an option!"

                        message = self.twilio_client.messages.create(
                            from_=from_number,
                            to=to_number,
                            body=reply_text
                        )

            elif quick_replies and len(quick_replies) > 3:
                # Use numbered list format for more than 3 options
                list_text = message_body + "\n\n*Quick Options:*\n"
                for idx, reply in enumerate(quick_replies, 1):
                    list_text += f"📱 *{idx}* - {reply['title']}\n"
                list_text += "\nJust type the number to select!"

                message = self.twilio_client.messages.create(
                    from_=from_number,
                    to=to_number,
                    body=list_text
                )

            elif list_options:
                # Send message with list options
                list_text = message_body + "\n\n*Options:*\n"
                for idx, option in enumerate(list_options, 1):
                    list_text += f"📱 *{idx}* - {option['title']}\n"
                list_text += "\nJust type the number to select!"

                message = self.twilio_client.messages.create(
                    from_=from_number,
                    to=to_number,
                    body=list_text
                )
            else:
                # Send regular message without interactive elements
                message = self.twilio_client.messages.create(
                    from_=from_number,
                    to=to_number,
                    body=message_body
                )

            logger.info(f"📱 Message sent to {phone_number}")
            return "Message sent successfully"

        except Exception as e:
            logger.error(f"❌ Error sending message: {str(e)}")
            # Fallback to regular message format for demo mode
            if quick_replies:
                reply_text = message_body + "\n\n*Quick Options:*\n"
                for idx, reply in enumerate(quick_replies, 1):
                    reply_text += f"📱 *{idx}* - {reply['title']}\n"
                reply_text += "\nJust type the number to select!"
                return reply_text
            elif list_options:
                list_text = message_body + "\n\n*Options:*\n"
                for idx, option in enumerate(list_options, 1):
                    list_text += f"📱 *{idx}* - {option['title']}\n"
                list_text += "\nJust type the number to select!"
                return list_text
            return message_body

    def handle_lessons(self, student):
        """Handle lessons inquiry with quick reply options"""
        # Get upcoming lessons
        upcoming_lessons = Lesson.query.filter(
            Lesson.student_id == student.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.now()
        ).order_by(Lesson.scheduled_date).limit(5).all()

        if not upcoming_lessons:
            message_body = "📅 You have no upcoming lessons scheduled.\n\nWould you like to book a lesson?"
            quick_replies = [
                {"id": "book", "title": "📅 Book Lesson"},
                {"id": "menu", "title": "🏠 Main Menu"}
            ]
            return self.send_interactive_message(student.phone, message_body, quick_replies)

        response = f"📅 *Your Upcoming Lessons:*\n\n"

        for idx, lesson in enumerate(upcoming_lessons, 1):
            date_str = lesson.scheduled_date.strftime('%Y-%m-%d')
            time_str = lesson.scheduled_date.strftime('%H:%M')
            instructor_name = lesson.instructor.get_full_name() if lesson.instructor else "No instructor assigned"

            response += f"🚗 *{lesson.lesson_type.title()}* - {lesson.duration_minutes} min\n"
            response += f"📅 Date: {date_str}\n"
            response += f"🕐 Time: {time_str}\n"
            response += f"👨‍🏫 Instructor: {instructor_name}\n"
            if lesson.location:
                response += f"📍 Location: {lesson.location}\n"
            response += f"💬 To cancel: type *cancel {idx}*\n\n"

        # Add quick reply options
        quick_replies = [
            {"id": "book", "title": "📅 Book Another"},
            {"id": "progress", "title": "📊 Check Progress"},
            {"id": "menu", "title": "🏠 Main Menu"}
        ]

        return self.send_interactive_message(student.phone, response, quick_replies)

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
        """Handle progress inquiry with quick reply options"""
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

        # Add quick reply options based on progress
        if remaining > 0:
            quick_replies = [
                {"id": "book", "title": "📅 Book Next Lesson"},
                {"id": "lessons", "title": "📋 View Lessons"},
                {"id": "menu", "title": "🏠 Main Menu"}
            ]
        else:
            quick_replies = [
                {"id": "lessons", "title": "📋 View History"},
                {"id": "menu", "title": "🏠 Main Menu"}
            ]

        return self.send_interactive_message(student.phone, response, quick_replies)

    def handle_cancel_lesson(self, student):
        """Handle lesson cancellation request"""
        # Get upcoming lessons that can be cancelled
        upcoming_lessons = Lesson.query.filter(
            Lesson.student_id == student.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.now()
        ).order_by(Lesson.scheduled_date).all()

        if not upcoming_lessons:
            return "❌ You have no upcoming lessons to cancel.\n\nType 'menu' to return to main menu."

        # Set session state to expect cancel selection
        self.set_session_state(student, 'awaiting_cancel_selection')

        response = "📋 *Your Upcoming Lessons:*\n\n"
        response += "🔥 *Tap to Cancel a Lesson:*\n\n"

        for i, lesson in enumerate(upcoming_lessons, 1):
            date_str = lesson.scheduled_date.strftime('%B %d, %Y')
            time_str = lesson.scheduled_date.strftime('%I:%M %p')
            instructor_name = lesson.instructor.get_full_name() if lesson.instructor else "No instructor assigned"

            response += f"❌ *Cancel #{i}* 🚗 *{lesson.lesson_type.title()}* - {lesson.duration_minutes} min\n"
            response += f"   📅 {date_str} at {time_str}\n"
            response += f"   👨‍🏫 {instructor_name}\n\n"

        response += "💡 *Quick options:*\n"
        response += "🔙 Type *menu* to go back\n"
        response += "⚠️ Cancel at least 2 hours before lesson time.\n\n"
        response += "💬 *To cancel a lesson, just type:*\n"
        for i, lesson in enumerate(upcoming_lessons, 1):
            response += f"• Type *cancel {i}* to cancel lesson #{i}\n"

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
                return f"❌ Invalid lessonnumber. You have {len(upcoming_lessons)} upcoming lessons."

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
        """Handle help request with quick reply options"""
        message_body = """❓ *Help & Easy Commands:*

🔥 *Quick Commands:*
• lessons - See your schedule
• book - Book 30min or 1 hour
• progress - Your stats
• cancel - Cancel upcoming
• menu - Back to start
• fund - Top up account
• emergency - Emergency contact

💡 *Pro Tips:*
• Lessons: 6:00 AM - 4:00 PM (Mon-Sat)
• Maximum 2 lessons per day
• Cancel at least 2 hours before lesson time
• Tomorrow's lessons: book after 6:00 PM today

📞 *Need Help?*
• Your instructor: {student.instructor.get_full_name() if student.instructor else "Not assigned"}
• Emergency: Type *emergency*
• Office: +263 77 123 4567"""

        quick_replies = [
            {"id": "book", "title": "📅 Book Lesson"},
            {"id": "lessons", "title": "📋 My Lessons"},
            {"id": "progress", "title": "📊 My Progress"},
            {"id": "emergency", "title": "🚨 Emergency"},
            {"id": "menu", "title": "🏠 Main Menu"}
        ]

        return self.send_interactive_message(student.phone, message_body, quick_replies)

    def handle_menu(self, student):
        """Handle menu request with quick reply options"""
        message_body = f"""📋 *Main Menu:*

👨‍🏫 Your instructor: {student.instructor.get_full_name() if student.instructor else "Not assigned"}
📍 Your location: {student.current_location or "Not set"}
💰 Account balance: ${float(student.account_balance):.2f}

Choose what you'd like to do:"""

        quick_replies = [
            {"id": "instructors", "title": "👨‍🏫 Find Instructors"},
            {"id": "lessons", "title": "📅 View Lessons"},
            {"id": "profile", "title": "👤 Update Profile"},
            {"id": "balance", "title": "💰 Check Balance"},
            {"id": "help", "title": "❓ Get Help"}
        ]

        return self.send_interactive_message(student.phone, message_body, quick_replies)

    def handle_find_instructors(self, student):
        """Handle instructor search based on student location"""
        if not student.current_location:
            return self.handle_set_location_first(student)

        # Get instructors in student's area
        nearby_instructors = self.get_nearby_instructors(student)

        if not nearby_instructors:
            message_body = f"""❌ No instructors found in {student.current_location}.

Try expanding your search or updating your location."""

            quick_replies = [
                {"id": "location", "title": "📍 Change Location"},
                {"id": "menu", "title": "🏠 Main Menu"}
            ]
            return self.send_interactive_message(student.phone, message_body, quick_replies)

        # Show available instructors
        response = f"👨‍🏫 *Available Instructors in {student.current_location}:*\n\n"

        for i, instructor in enumerate(nearby_instructors[:5], 1):  # Show max 5
            response += f"*{i}. {instructor.get_full_name()}*\n"
            response += f"📍 Area: {instructor.base_location}\n"
            response += f"⭐ Experience: {instructor.experience_years or 'N/A'} years\n"
            response += f"💰 Rates: ${float(instructor.hourly_rate_30min or 0):.2f}/30min, ${float(instructor.hourly_rate_60min or 0):.2f}/60min\n"
            if instructor.bio:
                response += f"ℹ️ {instructor.bio[:100]}...\n"
            response += f"📅 Type *select {i}* to view schedule\n\n"

        response += "💡 *Commands:*\n"
        response += "• *select [number]* - View instructor schedule\n"
        response += "• *location* - Change your location\n"
        response += "• *menu* - Main menu"

        return response

    def get_nearby_instructors(self, student):
        """Get instructors near student's location"""
        import json

        # Get all active instructors
        instructors = User.query.filter_by(role='instructor', active=True).all()
        nearby_instructors = []

        student_location = student.current_location.lower() if student.current_location else ""

        for instructor in instructors:
            if instructor.service_areas:
                try:
                    service_areas = json.loads(instructor.service_areas)
                    # Check if student's location matches any service area
                    for area in service_areas:
                        if student_location in area.lower() or area.lower() in student_location:
                            nearby_instructors.append(instructor)
                            break
                except:
                    pass
            elif instructor.base_location:
                # Simple text matching for base location
                if student_location in instructor.base_location.lower() or instructor.base_location.lower() in student_location:
                    nearby_instructors.append(instructor)

        return nearby_instructors

    def handle_set_location_first(self, student):
        """Prompt student to set location first"""
        message_body = """📍 *Set Your Location First*

To find instructors near you, please set your current location.

*Harare Areas Available:*
• CBD
• Avondale
• Eastlea
• Mount Pleasant
• Borrowdale
• Waterfalls
• Mbare
• Highfield
• Glen View

Type your area name (e.g., "CBD" or "Avondale")"""

        # Set state to await location input
        self.set_session_state(student, 'awaiting_location_update')

        return message_body

    def handle_change_location(self, student):
        """Handle location change request"""
        message_body = f"""📍 *Update Your Location*

Current location: {student.current_location or "Not set"}

*Available Areas in Harare:*
• CBD
• Avondale  
• Eastlea
• Mount Pleasant
• Borrowdale
• Waterfalls
• Mbare
• Highfield
• Glen View
• Warren Park
• Kuwadzana
• Budiriro

Type the name of your area:"""

        # Set state to await location input
        self.set_session_state(student, 'awaiting_location_update')

        return message_body

    def handle_profile_management(self, student):
        """Handle profile management menu"""
        # Check if student can switch instructor
        can_switch_instructor = self.can_switch_instructor(student)
        
        message_body = f"""👤 *Your Profile*

📝 Name: {student.name}
📞 Phone: {student.phone}
📧 Email: {student.email or "Not set"}
📍 Location: {student.current_location or "Not set"}
🎯 License Type: {student.license_type}
👨‍🏫 Instructor: {student.instructor.get_full_name() if student.instructor else "Not assigned"}
💰 Balance: ${float(student.account_balance):.2f}

What would you like to update?"""

        quick_replies = [
            {"id": "location", "title": "📍 Change Location"},
            {"id": "email", "title": "📧 Update Email"},
            {"id": "fund", "title": "💰 Fund Account"}
        ]
        
        if can_switch_instructor:
            quick_replies.insert(-1, {"id": "instructor", "title": "👨‍🏫 Switch Instructor"})
        
        quick_replies.append({"id": "menu", "title": "🏠 Main Menu"})

        return self.send_interactive_message(student.phone, message_body, quick_replies)

    def can_switch_instructor(self, student):
        """Check if student can switch instructor (after 5 lessons or 1 week)"""
        from models import Lesson, LESSON_COMPLETED
        
        # Check if student has completed at least 5 lessons
        completed_lessons = Lesson.query.filter_by(


    def handle_emergency_contact(self, student):
        """Handle emergency contact request"""
        message_body = f"""🚨 *Emergency Contacts*

Hi {student.name},

If you need immediate assistance:

👨‍🏫 *Your Instructor:*
• {student.instructor.get_full_name() if student.instructor else "Not assigned"}
• Phone: {student.instructor.phone if student.instructor and student.instructor.phone else "Contact office"}

🏢 *DriveLink Office:*
• Phone: +263 77 123 4567
• Emergency: +263 77 999 8888
• Email: help@drivelink.co.zw

⚠️ *For road emergencies:*
• Police: 999
• Medical: 994
• AA Zimbabwe: +263 4 369 500

Stay safe! 🚗"""

        quick_replies = [
            {"id": "menu", "title": "🏠 Main Menu"},
            {"id": "help", "title": "❓ More Help"}
        ]

        return self.send_interactive_message(student.phone, message_body, quick_replies)


            student_id=student.id,
            status=LESSON_COMPLETED
        ).count()
        
        if completed_lessons >= 5:
            return True
        
        # Check if it's been at least 1 week since registration
        if student.registration_date:
            days_since_registration = (datetime.now() - student.registration_date).days
            if days_since_registration >= 7:
                return True
        
        return False

    def handle_instructor_switch(self, student):
        """Handle instructor switching request"""
        if not self.can_switch_instructor(student):
            completed_lessons = Lesson.query.filter_by(
                student_id=student.id,
                status=LESSON_COMPLETED
            ).count()
            
            days_since_registration = (datetime.now() - student.registration_date).days if student.registration_date else 0
            
            return f"""❌ *Cannot Switch Instructor Yet*

You can switch instructors after:
• Completing 5 lessons (current: {completed_lessons})
• OR after 1 week of registration (current: {days_since_registration} days)

This policy ensures continuity in your learning process.

Type *menu* to return to main menu."""
        
        # Show available instructors
        return self.handle_find_instructors(student)

    def handle_email_update(self, student):
        """Handle email update request"""
        self.set_session_state(student, 'awaiting_email_update')
        
        return f"""📧 *Update Email Address*

Current email: {student.email or "Not set"}

Enter your new email address:

Example: newemail@example.com

Or type *cancel* to go back"""

    def process_email_update(self, student, email_text):
        """Process email update from student"""
        try:
            if email_text.lower().strip() == 'cancel':
                self.set_session_state(student, 'main_menu')
                return self.handle_profile_management(student)
            
            email = email_text.strip().lower()
            if '@' not in email or '.' not in email.split('@')[1]:
                return "Please enter a valid email address or type *cancel* to go back"
            
            # Update student email
            student.email = email
            db.session.commit()
            
            # Clear state
            self.set_session_state(student, 'main_menu')
            
            return f"""✅ *Email Updated Successfully!*

Your new email: {email}

Type *menu* to return to main menu."""
            
        except Exception as e:
            logger.error(f"Error updating email: {str(e)}")
            return "❌ Error updating email. Please try again or contact support."

    def handle_check_balance(self, student):
        """Handle balance inquiry"""
        message_body = f"""💰 *Account Balance*

Current Balance: ${float(student.account_balance):.2f}

Recent Activity:
"""

        # Get recent payments
        recent_payments = Payment.query.filter_by(student_id=student.id).order_by(Payment.created_at.desc()).limit(3).all()

        if recent_payments:
            for payment in recent_payments:
                date_str = payment.created_at.strftime('%Y-%m-%d')
                message_body += f"• +${float(payment.amount):.2f} on {date_str}\n"
        else:
            message_body += "No recent payments found.\n"

        message_body += "\n💡 Need to fund your account? Type *fund*"

        quick_replies = [
            {"id": "fund", "title": "💰 Fund Account"},
            {"id": "menu", "title": "🏠 Main Menu"}
        ]

        return self.send_interactive_message(student.phone, message_body, quick_replies)

    def handle_fund_account(self, student):
        """Handle account funding request"""
        message_body = f"""💰 *Fund Your Account*

Current Balance: ${float(student.account_balance):.2f}

*Payment Methods Available:*
• EcoCash
• OneMoney  
• Bank Transfer
• Cash (Visit Office)

*How to fund:*
1. Make payment using any method above
2. Send screenshot/reference to this number
3. Your account will be updated within 1 hour

*Office Location:*
📍 123 Main Street, Harare CBD
📞 Contact: +263 77 123 4567

For immediate assistance, contact our office."""

        quick_replies = [
            {"id": "balance", "title": "💰 Check Balance"},
            {"id": "menu", "title": "🏠 Main Menu"}
        ]

        return self.send_interactive_message(student.phone, message_body, quick_replies)

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
        # Set session state to expect duration selection
        self.set_session_state(student, 'awaiting_duration')

        message_body = """📅 *Book a Lesson*

Choose your lesson duration:"""

        quick_replies = [
            {"id": "30", "title": "30 minutes"},
            {"id": "60", "title": "60 minutes"},
            {"id": "menu", "title": "Back to Menu"}
        ]

        return self.send_interactive_message(student.phone, message_body, quick_replies)

    def handle_duration_selection(self, student, duration_minutes):
        """Handle duration selection and show available timeslots with booking numbers"""
        if duration_minutes not in [30, 60]:
            return self.handle_duration_selection_error(student, str(duration_minutes))

        instructor = student.instructor
        if not instructor:
            return "❌ No instructor assigned. Please contact the driving school.\n\nType 'menu' to return to main menu."

        # Check if student has sufficient balance
        if not student.has_sufficient_balance(duration_minutes):
            lesson_price = student.get_lesson_price(duration_minutes)
            return f"❌ Insufficient balance for {duration_minutes}-minute lesson.\n\nLesson cost: ${lesson_price:.2f}\nYour balance: ${student.account_balance:.2f}\n\nPlease top up your account and try again.\n\nType 'menu' to return to main menu."

        # Get available slots for the selected duration
        available_slots = self.get_duration_specific_timeslots(instructor, duration_minutes)

        if not available_slots:
            return f"❌ No {duration_minutes}-minute slots available for the next 2 days.\n\nTry:\n• Different duration (type '2' for booking menu)\n• Contact your instructor\n• Type 'menu' for main menu"

        # Store the booking context in session
        self.store_booking_context(student, duration_minutes, available_slots)

        response = f"📅 *Available {duration_minutes}-minute slots:*\n\n"
        response += "💰 *Lesson cost:* $" + f"{student.get_lesson_price(duration_minutes):.2f}\n\n"

        current_date = None
        slot_count = 0

        for i, slot in enumerate(available_slots):
            if slot_count >= 10:  # Limit to 10 slots to avoid message being too long
                break

            slot_date = slot['start'].date()
            if slot_date != current_date:
                response += f"\n*{slot['start'].strftime('%A, %B %d')}*\n"
                current_date = slot_date

            start_time = slot['start'].strftime('%I:%M %p')
            response += f"{i+1}. {start_time}\n"
            slot_count += 1

        response += f"\n🔥 *Quick Booking - Just Reply:*\n\n"

        # Show all available slots with simple reply instructions
        for i, slot in enumerate(available_slots[:10]):  # Show up to 10 slots
            start_time = slot['start'].strftime('%I:%M %p')
            response += f"⚡ Reply *{i+1}* → Book {start_time}\n"

        response += f"\n💬 *How to book:*\n"
        response += f"• Reply with slot number (1, 2, 3, etc.)\n"
        response += f"• Or type *book 1*, *book 2*, etc.\n\n"
        response += f"🔄 *Other options:*\n"
        response += f"• *menu* - Main menu\n"
        response += f"• *book* - Change duration"

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

    def store_booking_context(self, student, duration_minutes, available_slots):
        """Store booking context in WhatsApp session"""
        # Store booking context as JSON string in session data
        booking_context = {
            'duration_minutes': duration_minutes,
            'available_slots': [
                {
                    'start': slot['start'].isoformat(),
                    'end': slot['end'].isoformat()
                } for slot in available_slots[:10]  # Store only first 10 slots
            ]
        }

        # Use new session state management
        self.set_session_state(student, 'awaiting_booking_slot', booking_context)

    def get_session_state(self, student):
        """Get current session state to determine conversation flow"""
        session_id = f"whatsapp_{student.phone}_{datetime.now().strftime('%Y%m%d')}"
        session = WhatsAppSession.query.filter_by(session_id=session_id).first()

        if not session or not session.last_message:
            return 'main_menu'

        message = session.last_message

        # Check for location update state
        if message == 'awaiting_location_update':
            return 'awaiting_location_update'

        # Check for email update state
        if message == 'awaiting_email_update':
            return 'awaiting_email_update'

        # Check for instructor selection state
        if message == 'awaiting_instructor_selection':
            return 'awaiting_instructor_selection'

        # Check if waiting for duration selection
        if message == 'awaiting_duration':
            return 'awaiting_duration'

        # Check if booking context exists (waiting for slot selection)
        if message.startswith('BOOKING_CONTEXT:'):
            return 'awaiting_booking_slot'

        # Check if showing cancel options
        if message == 'showing_cancel_options':
            return 'awaiting_cancel_selection'

        return 'main_menu'

    def set_session_state(self, student, state, data=None):
        """Set session state for conversation flow tracking"""
        session_id = f"whatsapp_{student.phone}_{datetime.now().strftime('%Y%m%d')}"
        session = WhatsAppSession.query.filter_by(session_id=session_id).first()

        if not session:
            session = WhatsAppSession(
                student_id=student.id,
                session_id=session_id
            )
            db.session.add(session)

        if state == 'awaiting_location_update':
            session.last_message = 'awaiting_location_update'
        elif state == 'awaiting_email_update':
            session.last_message = 'awaiting_email_update'
        elif state == 'awaiting_instructor_selection':
            session.last_message = 'awaiting_instructor_selection'
        elif state == 'awaiting_duration':
            session.last_message = 'awaiting_duration'
        elif state == 'awaiting_booking_slot' and data:
            import json
            session.last_message = f"BOOKING_CONTEXT:{json.dumps(data)}"
        elif state == 'awaiting_cancel_selection':
            session.last_message = 'showing_cancel_options'
        else:
            session.last_message = 'main_menu'

        session.last_activity = datetime.now()
        session.is_active = True
        db.session.commit()

    def get_booking_context(self, student):
        """Get stored booking context from WhatsApp session"""
        session_id = f"whatsapp_{student.phone}_{datetime.now().strftime('%Y%m%d')}"
        session = WhatsAppSession.query.filter_by(session_id=session_id).first()

        if session and session.last_message and session.last_message.startswith('BOOKING_CONTEXT:'):
            try:
                # Check if booking context is still valid (not older than 15 minutes)
                if session.last_activity and (datetime.now() - session.last_activity).total_seconds() > 900:
                    # Context expired, clear it
                    self.set_session_state(student, 'main_menu')
                    return None

                import json
                context_json = session.last_message.replace('BOOKING_CONTEXT:', '')
                context = json.loads(context_json)

                # Validate context structure
                if not isinstance(context, dict) or 'duration_minutes' not in context or 'available_slots' not in context:
                    return None

                return context
            except Exception as e:
                logger.error(f"Error parsing booking context: {str(e)}")
                # Clear invalid context
                self.set_session_state(student, 'main_menu')
                return None
        return None

    def process_timeslot_booking(self, student, slot_number):
        """Process booking of a specific timeslot by number"""
        try:
            slot_num = int(slot_number)

            # Get booking context
            booking_context = self.get_booking_context(student)
            if not booking_context:
                return """❌ No active booking session found. 

Please start fresh:
• Type '2' to book a lesson
• Or type 'reset' to clear everything and start over

📋 Need the main menu? Type 'menu'"""

            available_slots = booking_context['available_slots']
            duration_minutes = booking_context['duration_minutes']

            if slot_num < 1 or slot_num > len(available_slots):
                return f"❌ Invalid slot number. Please choose between 1 and {len(available_slots)}."

            selected_slot = available_slots[slot_num - 1]
            scheduled_date = datetime.fromisoformat(selected_slot['start'])

            # Validate the booking is still possible
            current_time = datetime.now()

            # Apply WhatsApp booking time rules
            slot_date = scheduled_date.date()
            current_date = current_time.date()
            tomorrow = current_date + timedelta(days=1)

            # WhatsApp bot booking rules
            if slot_date == tomorrow:
                if current_time.hour < 18:  # Before 6 PM, can't book tomorrow
                    return "⏰ Tomorrow's lessons can only be booked after 6:00 PM today.\n\nType 'menu' to return to main menu or 'reset' to start over."
            elif slot_date == current_date:
                if current_time.hour >= 15 and current_time.minute >= 30:  # After 3:30 PM
                    return "⏰ Booking for today closes at 3:30 PM.\n\nType 'menu' to return to main menu or 'reset' to start over."
            elif slot_date < current_date:
                return "❌ Cannot book lessons in the past.\n\nType 'menu' to return to main menu or 'reset' to start over."

            # Check if slot is still available
            existing_lesson = Lesson.query.filter(
                Lesson.instructor_id == student.instructor_id,
                Lesson.status == LESSON_SCHEDULED,
                Lesson.scheduled_date == scheduled_date
            ).first()

            if existing_lesson:
                return "❌ Sorry, this time slot has been booked by another student. Please choose a different slot or type '2' to see updated availability."

            # Check daily lesson limit
            existing_lessons_count = Lesson.query.filter(
                and_(
                    Lesson.student_id == student.id,
                    Lesson.scheduled_date >= datetime.combine(slot_date, datetime.min.time()),
                    Lesson.scheduled_date < datetime.combine(slot_date + timedelta(days=1), datetime.min.time()),
                    Lesson.status != LESSON_CANCELLED
                )
            ).count()

            if existing_lessons_count >= 2:
                return "❌ You already have 2 lessons scheduled for this day. Maximum 2 lessons per day allowed."

            # Check balance again
            if not student.has_sufficient_balance(duration_minutes):
                lesson_price = student.get_lesson_price(duration_minutes)
                return f"❌ Insufficient balance.\n\nLesson cost: ${lesson_price:.2f}\nYour balance: ${student.account_balance:.2f}"

            # Create the lesson
            lesson = Lesson()
            lesson.student_id = student.id
            lesson.instructor_id = student.instructor_id
            lesson.scheduled_date = scheduled_date
            lesson.duration_minutes = duration_minutes
            lesson.lesson_type = 'practical'
            lesson.cost = student.get_lesson_price(duration_minutes)

            db.session.add(lesson)
            db.session.commit()

            # Clear booking context and reset to main menu
            self.set_session_state(student, 'main_menu')

            # Format confirmation message
            date_str = scheduled_date.strftime('%A, %B %d, %Y')
            time_str = scheduled_date.strftime('%I:%M %p')
            instructor_name = student.instructor.get_full_name()

            response = f"✅ *Lesson Booked Successfully!* 🎉\n\n"
            response += f"📅 **Date:** {date_str}\n"
            response += f"🕐 **Time:** {time_str}\n"
            response += f"⏱️ **Duration:** {duration_minutes} minutes\n"
            response += f"👨‍🏫 **Instructor:** {instructor_name}\n"
            response += f"💰 **Cost:** ${lesson.cost:.2f}\n"
            response += f"💳 **New Balance:** ${float(student.account_balance):.2f}\n\n"
            response += "📲 You'll receive a reminder before your lesson.\n"
            response += "🚗 Good luck with your driving lesson!\n\n"
            response += "Type 'menu' to return to the main menu."

            logger.info(f"Lesson {lesson.id} booked via WhatsApp by student {student.name}")
            return response

        except ValueError:
            return "❌ Please provide a valid slot number. Example: *book 1*"
        except Exception as e:
            logger.error(f"Error booking lesson via WhatsApp: {str(e)}")
            return "❌ Sorry, there was an error booking your lesson. Please try again or contact your instructor."

    def handle_duration_selection_error(self, student, message):
        """Handle invalid duration selection"""
        return f"""❌ Please select a valid lesson duration.

📅 *Book a Lesson*

Just tap and send one of these:

🕐 30
🕑 60

💡 Quick options:
• Type *menu* to return to main menu
• Type *reset* to start over"""

    def handle_booking_slot_error(self, student, message):
        """Handle invalid booking slot selection"""
        booking_context = self.get_booking_context(student)
        if not booking_context:
            return self.handle_book_lesson(student)

        available_slots = booking_context['available_slots']
        duration_minutes = booking_context['duration_minutes']

        return f"""❌ Please select a valid slot number.

Available slots: 1 to {len(available_slots)}

💡 Examples:
• Type *book 1* (to book slot #1)
• Type *1* (shortcut)
• Type 'menu' to return to main menu
• Type '2' to select different duration"""

    def handle_contextual_fallback(self, student, message, session_state):
        """Handle unrecognized messages with context awareness"""
        if session_state == 'awaiting_duration':
            return self.handle_duration_selection_error(student, message)
        elif session_state == 'awaiting_booking_slot':
            return self.handle_booking_slot_error(student, message)
        else:
            return self.handle_default(student)

    def handle_default(self, student):
        """Handle unrecognized messages"""
        return f"""I didn't understand that, {student.name}. 🤔

🔥 *Quick Commands - Just Reply:*

📅 *lessons* - View your schedule
🎯 *book* - Book a lesson
📊 *progress* - Check progress
❌ *cancel* - Cancel lesson
❓ *help* - Get help

🔄 *Quick fixes:*
📋 *menu* - See all options
⚡ *reset* - Start fresh

💬 *Just reply with any word above!*
Example: Reply "*lessons*" or "*book*"""

    def reset_session_and_start(self, student):
        """Reset session state and show main menu"""
        # Clear any booking context and reset to main menu
        self.set_session_state(student, 'main_menu')

        message_body = f"""🔄 *Session Reset* ✅

Hello again {student.name}! 👋

I've cleared everything. Let's start fresh!

👨‍🏫 Your instructor: {student.instructor.get_full_name() if student.instructor else "Not assigned"}

Choose what you'd like to do:"""

        quick_replies = [
            {"id": "lessons", "title": "📅 View Lessons"},
            {"id": "book", "title": "🎯 Book Lesson"},
            {"id": "progress", "title": "📊 Check Progress"},
            {"id": "help", "title": "❓ Get Help"}
        ]

        return self.send_interactive_message(student.phone, message_body, quick_replies)

    def process_location_update(self, student, location_text):
        """Process location update from student"""
        try:
            # Clean and validate location
            location = location_text.strip().title()

            # Valid Harare areas
            valid_areas = [
                'CBD', 'Avondale', 'Eastlea', 'Mount Pleasant', 'Borrowdale',
                'Waterfalls', 'Mbare', 'Highfield', 'Glen View', 'Warren Park',
                'Kuwadzana', 'Budiriro', 'Chitungwiza', 'Epworth', 'Ruwa'
            ]

            # Find matching area (fuzzy matching)
            matched_area = None
            location_lower = location.lower()

            for area in valid_areas:
                if location_lower in area.lower() or area.lower() in location_lower:
                    matched_area = area
                    break

            if not matched_area:
                return f"""❌ Location "{location}" not recognized.

Please choose from these areas:
• CBD
• Avondale
• Eastlea
• Mount Pleasant
• Borrowdale
• Waterfalls
• And more...

Type your area name again:"""

            # Update student location
            student.current_location = matched_area
            db.session.commit()

            # Clear location update state
            self.set_session_state(student, 'main_menu')

            response = f"✅ *Location Updated Successfully!*\n\n"
            response += f"📍 Your location is now set to: *{matched_area}*\n\n"
            response += "You can now find instructors in your area!"

            quick_replies = [
                {"id": "instructors", "title": "👨‍🏫 Find Instructors"},
                {"id": "menu", "title": "🏠 Main Menu"}
            ]

            return self.send_interactive_message(student.phone, response, quick_replies)

        except Exception as e:
            logger.error(f"Error updating location: {str(e)}")
            return "❌ Error updating location. Please try again or contact support."

    def process_instructor_selection(self, student, instructor_number):
        """Process instructor selection and show their schedule"""
        try:
            instructor_num = int(instructor_number)

            # Get nearby instructors again
            nearby_instructors = self.get_nearby_instructors(student)

            if instructor_num < 1 or instructor_num > len(nearby_instructors):
                return f"❌ Invalid instructor number. Please choose between 1 and {len(nearby_instructors)}."

            selected_instructor = nearby_instructors[instructor_num - 1]

            # Show instructor details and schedule
            response = f"👨‍🏫 *{selected_instructor.get_full_name()}*\n\n"
            response += f"📍 Base Area: {selected_instructor.base_location}\n"
            response += f"⭐ Experience: {selected_instructor.experience_years or 'N/A'} years\n"
            response += f"💰 30min lesson: ${float(selected_instructor.hourly_rate_30min or 0):.2f}\n"
            response += f"💰 60min lesson: ${float(selected_instructor.hourly_rate_60min or 0):.2f}\n"

            if selected_instructor.bio:
                response += f"\nℹ️ *About:*\n{selected_instructor.bio}\n"

            # Get available slots for this instructor
            available_slots = self.get_instructor_available_slots(selected_instructor, days_ahead=3)

            if available_slots:
                response += f"\n📅 *Next Available Slots:*\n"
                for i, slot in enumerate(available_slots[:3], 1):
                    date_str = slot['start'].strftime('%A, %B %d')
                    time_str = slot['start'].strftime('%I:%M %p')
                    response += f"{i}. {date_str} at {time_str}\n"
            else:
                response += "\n❌ No available slots in the next 3 days."

            response += f"\n💡 *To book with this instructor:*\n"
            response += f"• Type *choose {instructor_num}* to select them\n"
            response += f"• Type *instructors* to see other options\n"
            response += f"• Type *menu* for main menu"

            return response

        except ValueError:
            return "❌ Please provide a valid instructor number. Example: *select 1*"
        except Exception as e:
            logger.error(f"Error processing instructor selection: {str(e)}")
            return "❌ Error processing selection. Please try again."

    def handle_unknown_student(self, phone_number):
        """Handle messages from unknown phone numbers - start registration"""
        # Set registration state for this phone number
        self.set_registration_state(phone_number, 'awaiting_name')
        
        return f"""👋 *Welcome to DriveLink!*

I don't recognize this number, but I can help you register right now! 📱

Let's get you set up in just a few steps:

*Step 1 of 5: What's your full name?*

Just type your name and I'll guide you through the rest.

Example: John Doe"""

    def process_button_response(self, phone_number, button_text, button_payload):
        """Process button responses from Quick Reply buttons"""
        try:
            # Find the student by phone number
            student = Student.query.filter_by(phone=f"+{phone_number}").first()
            if not student:
                return self.handle_unknown_student(phone_number)

            logger.info(f"🔘 Processing button '{button_payload}' for student {student.name}")

            # Update session activity
            self.update_session(student, f"button:{button_payload}")

            # Handle different button payloads
            if button_payload == "lessons":
                return self.handle_lessons(student)
            elif button_payload == "book":
                return self.handle_book_lesson(student)
            elif button_payload == "progress":
                return self.handle_progress(student)
            elif button_payload == "help":
                return self.handle_help(student)
            elif button_payload == "menu":
                return self.handle_menu(student)
            elif button_payload == "30":
                return self.handle_duration_selection(student, 30)
            elif button_payload == "60":
                return self.handle_duration_selection(student, 60)
            elif button_payload.startswith("slot_"):
                # Handle timeslot booking
                slot_number = button_payload.replace("slot_", "")
                return self.process_timeslot_booking(student, slot_number)
            else:
                # Unknown button payload, show menu
                logger.warning(f"⚠️ Unknown button payload: {button_payload}")
                return self.handle_menu(student)

        except Exception as e:
            logger.error(f"❌ Error processing button response: {str(e)}")
            return "Sorry, there was an error processing your selection. Please try again or type 'menu'."

    def create_quick_reply_template(self, template_name, body_text, button_texts):
        """Create a Quick Reply template using Twilio Content API"""
        try:
            if not self.twilio_client:
                logger.warning("Cannot create template - Twilio client not available")
                return None

            # Build template content
            template_content = {
                "body": body_text,
                "buttons": []
            }

            # Add buttons (max 3 for Quick Reply)
            for idx, button_text in enumerate(button_texts[:3]):
                template_content["buttons"].append({
                    "type": "quick_reply",
                    "text": button_text[:24],  # Max 24 characters
                    "id": f"btn_{idx+1}"
                })

            # Create the template
            content = self.twilio_client.content.v1.contents.create(
                friendly_name=template_name,
                content_type="twilio/quick-reply",
                content=template_content
            )

            logger.info(f"✅ Created template '{template_name}' with SID: {content.sid}")
            return content.sid

        except Exception as e:
            logger.error(f"❌ Error creating template: {str(e)}")
            return None

    # Instructor-specific message handlers
    def handle_instructor_message(self, instructor, message):
        """Handle messages from instructors"""
        instructor_commands = {
            'hi': lambda: self.instructor_greeting(instructor),
            'hello': lambda: self.instructor_greeting(instructor),
            'students': lambda: self.handle_instructor_students(instructor),
            'schedule': lambda: self.handle_instructor_schedule(instructor),
            'lessons': lambda: self.handle_instructor_lessons(instructor),
            'help': lambda: self.instructor_help(instructor),
            'menu': lambda: self.instructor_menu(instructor),
            'today': lambda: self.handle_instructor_today_lessons(instructor),
            'cancel': lambda: self.handle_instructor_cancel_lesson(instructor, message),
            'confirm': lambda: self.handle_instructor_confirm_lesson(instructor, message),
            'complete': lambda: self.handle_instructor_complete_lesson(instructor, message),
            'availability': lambda: self.handle_instructor_availability(instructor),
        }

        # Check for specific instructor commands first
        for command, handler in instructor_commands.items():
            if command in message:
                return handler()

        # Handle lesson status updates with lesson ID
        if message.startswith('cancel ') or message.startswith('confirm ') or message.startswith('complete '):
            return self.handle_instructor_lesson_action(instructor, message)

        # Default instructor response
        return self.instructor_menu(instructor)

    def instructor_greeting(self, instructor):
        """Instructor greeting message"""
        return f"""👨‍🏫 Hello {instructor.get_full_name()}!

Welcome to DriveLink Instructor Portal.

📊 Quick Stats:
• Students: {len(instructor.instructor_students)} assigned
• Today's lessons: {self.count_instructor_today_lessons(instructor)}

What would you like to do?

1. students - View your students
2. today - Today's lessons
3. schedule - Weekly schedule
4. lessons - All upcoming lessons
5. help - Get help

Just type the number or word!"""

    def instructor_menu(self, instructor):
        """Show instructor main menu"""
        return f"""🏠 Instructor Menu - {instructor.get_full_name()}

📚 Available Commands:

1. students - View assigned students
2. today - Today's lesson schedule
3. schedule - This week's schedule  
4. lessons - All upcoming lessons
5. availability - Set your availability
6. help - Get detailed help

💡 Quick Actions:
• cancel [lesson_id] - Cancel a lesson
• confirm [lesson_id] - Confirm a lesson
• complete [lesson_id] - Mark lesson complete

📞 Type any number or command!"""

    def handle_instructor_students(self, instructor):
        """Show instructor's assigned students"""
        students = instructor.instructor_students
        if not students:
            return "📚 No students assigned to you yet."

        response = f"👥 Your Students ({len(students)}):\n\n"
        for i, student in enumerate(students, 1):
            active_lessons = len([l for l in student.lessons if l.status == LESSON_SCHEDULED])
            response += f"{i}. {student.name}\n"
            response += f"   📞 {student.phone}\n"
            response += f"   📍 {student.current_location or 'Location not set'}\n"
            response += f"   📅 Active lessons: {active_lessons}\n"
            response += f"   💰 Balance: ${float(student.account_balance):.2f}\n\n"

        response += "💡 To view a student's details, type: student [number]"
        return response

    def handle_instructor_today_lessons(self, instructor):
        """Show today's lessons for instructor"""
        today = datetime.now().date()
        today_lessons = Lesson.query.filter(
            Lesson.instructor_id == instructor.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.combine(today, datetime.min.time()),
            Lesson.scheduled_date < datetime.combine(today + timedelta(days=1), datetime.min.time())
        ).order_by(Lesson.scheduled_date).all()

        if not today_lessons:
            return f"📅 No lessons scheduled for today ({today.strftime('%A, %B %d')}).\n\nEnjoy your day off! 😊"

        response = f"📅 Today's Lessons - {today.strftime('%A, %B %d')}:\n\n"
        for i, lesson in enumerate(today_lessons, 1):
            time_str = lesson.scheduled_date.strftime('%I:%M %p')
            response += f"{i}. {time_str} - {lesson.student.name}\n"
            response += f"   📞 {lesson.student.phone}\n"
            response += f"   ⏱️ {lesson.duration_minutes} minutes\n"
            response += f"   📍 {lesson.location or 'Location TBD'}\n"
            response += f"   💰 ${float(lesson.cost):.2f}\n"
            response += f"   🆔 Lesson ID: {lesson.id}\n\n"

        response += "💡 Commands:\n"
        response += "• confirm [id] - Confirm lesson\n"
        response += "• cancel [id] - Cancel lesson\n"
        response += "• complete [id] - Mark complete"
        return response

    def handle_instructor_schedule(self, instructor):
        """Show instructor's weekly schedule"""
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=7)
        
        lessons = Lesson.query.filter(
            Lesson.instructor_id == instructor.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.combine(start_date, datetime.min.time()),
            Lesson.scheduled_date < datetime.combine(end_date, datetime.min.time())
        ).order_by(Lesson.scheduled_date).all()

        if not lessons:
            return "📅 No lessons scheduled for the next 7 days."

        response = f"📅 Your Schedule (Next 7 days):\n\n"
        current_date = None
        
        for lesson in lessons:
            lesson_date = lesson.scheduled_date.date()
            if lesson_date != current_date:
                response += f"\n📆 {lesson_date.strftime('%A, %B %d')}:\n"
                current_date = lesson_date
            
            time_str = lesson.scheduled_date.strftime('%I:%M %p')
            response += f"  • {time_str} - {lesson.student.name}\n"
            response += f"    ⏱️ {lesson.duration_minutes}min | 💰 ${float(lesson.cost):.2f}\n"

        return response

    def handle_instructor_lessons(self, instructor):
        """Show all upcoming lessons for instructor"""
        upcoming_lessons = Lesson.query.filter(
            Lesson.instructor_id == instructor.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.now()
        ).order_by(Lesson.scheduled_date).limit(10).all()

        if not upcoming_lessons:
            return "📅 No upcoming lessons scheduled."

        response = f"📚 Upcoming Lessons (Next 10):\n\n"
        for i, lesson in enumerate(upcoming_lessons, 1):
            date_str = lesson.scheduled_date.strftime('%m/%d')
            time_str = lesson.scheduled_date.strftime('%I:%M %p')
            response += f"{i}. {date_str} {time_str} - {lesson.student.name}\n"
            response += f"   ⏱️ {lesson.duration_minutes}min | 💰 ${float(lesson.cost):.2f}\n"
            response += f"   🆔 ID: {lesson.id}\n\n"

        response += "💡 Use lesson ID for actions (cancel/confirm/complete)"
        return response

    def handle_instructor_lesson_action(self, instructor, message):
        """Handle lesson actions like cancel, confirm, complete"""
        parts = message.split()
        if len(parts) < 2:
            return "❌ Please provide lesson ID. Example: cancel 123"

        action = parts[0].lower()
        try:
            lesson_id = int(parts[1])
        except ValueError:
            return "❌ Please provide a valid lesson ID number."

        # Find the lesson
        lesson = Lesson.query.filter_by(id=lesson_id, instructor_id=instructor.id).first()
        if not lesson:
            return f"❌ Lesson {lesson_id} not found or not assigned to you."

        if action == 'cancel':
            lesson.status = LESSON_CANCELLED
            lesson.updated_at = datetime.now()
            db.session.commit()
            
            # Notify student with detailed message
            if lesson.student.phone:
                cancel_msg = f"""❌ *Lesson Cancelled*

Hi {lesson.student.name},

Your instructor has cancelled your lesson:

📅 Date: {lesson.scheduled_date.strftime('%A, %B %d')}
🕐 Time: {lesson.scheduled_date.strftime('%I:%M %p')}

Please reschedule when convenient.

💬 *Quick Actions:*
• Type *book* to schedule new lesson
• Type *lessons* to view remaining lessons
• Contact your instructor if needed"""
                
                self.send_whatsapp_message(lesson.student.phone, cancel_msg)
            return f"✅ Lesson {lesson_id} cancelled. Student has been notified."

        elif action == 'confirm':
            # Send confirmation to student
            if lesson.student.phone:
                confirm_msg = f"""✅ *Lesson Confirmed*

Hi {lesson.student.name}!

Your lesson has been confirmed:

📅 Date: {lesson.scheduled_date.strftime('%A, %B %d')}
🕐 Time: {lesson.scheduled_date.strftime('%I:%M %p')}
⏱️ Duration: {lesson.duration_minutes} minutes

See you there! 🚗"""
                
                self.send_whatsapp_message(lesson.student.phone, confirm_msg)
            return f"✅ Lesson {lesson_id} confirmed. Student has been notified."

        elif action == 'complete':
            lesson.status = LESSON_COMPLETED
            lesson.completed_date = datetime.now()
            lesson.updated_at = datetime.now()
            
            # Update student progress
            if lesson.student:
                lesson.student.lessons_completed += 1
                # Deduct lesson cost from balance
                lesson.student.account_balance = float(lesson.student.account_balance) - float(lesson.cost)
            
            db.session.commit()
            
            # Notify student of completion
            if lesson.student.phone:
                progress_percentage = lesson.student.get_progress_percentage()
                remaining_lessons = lesson.student.total_lessons_required - lesson.student.lessons_completed
                
                complete_msg = f"""🎉 *Lesson Completed!*

Great job today, {lesson.student.name}!

📊 *Your Progress:*
• Completed: {lesson.student.lessons_completed}/{lesson.student.total_lessons_required} lessons
• Progress: {progress_percentage:.1f}%
• Remaining: {remaining_lessons} lessons

💰 Cost: ${float(lesson.cost):.2f} deducted
💳 New Balance: ${float(lesson.student.account_balance):.2f}

Keep up the great work! 🚗✨

Type *progress* to see detailed stats"""
                
                self.send_whatsapp_message(lesson.student.phone, complete_msg)
            
            return f"✅ Lesson {lesson_id} completed. Student progress updated and notified."

        return "❌ Unknown action. Use: cancel, confirm, or complete"

    def handle_instructor_availability(self, instructor):
        """Handle instructor availability settings"""
        return f"""📅 Availability Settings

Current working hours: Mon-Sat, 6:00 AM - 4:00 PM

To update your availability, please:
1. Use the web portal at DriveLink.com
2. Or contact your admin

This feature is coming to WhatsApp soon! 🚀"""

    def count_instructor_today_lessons(self, instructor):
        """Count today's lessons for instructor"""
        today = datetime.now().date()
        return Lesson.query.filter(
            Lesson.instructor_id == instructor.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.combine(today, datetime.min.time()),
            Lesson.scheduled_date < datetime.combine(today + timedelta(days=1), datetime.min.time())


    def send_lesson_reminder_24h(self, lesson):
        """Send 24-hour lesson reminder"""
        if not lesson.student.phone:
            return False
            
        message = f"""🔔 *24-Hour Lesson Reminder*

Hi {lesson.student.name}!

Don't forget your driving lesson tomorrow:

📅 Date: {lesson.scheduled_date.strftime('%A, %B %d')}
🕐 Time: {lesson.scheduled_date.strftime('%I:%M %p')}
⏱️ Duration: {lesson.duration_minutes} minutes
👨‍🏫 Instructor: {lesson.instructor.get_full_name()}

💡 *Quick Commands:*
• Type *lessons* to view all lessons
• Type *cancel {lesson.id}* to cancel (if needed)

See you tomorrow! 🚗"""

        return self.send_whatsapp_message(lesson.student.phone, message)

    def send_lesson_reminder_2h(self, lesson):
        """Send 2-hour lesson reminder"""
        if not lesson.student.phone:
            return False
            
        message = f"""⏰ *Final Reminder - 2 Hours*


    def check_and_warn_low_balance(self, student):
        """Check if student has low balance and send warning"""
        balance = float(student.account_balance)
        min_lesson_cost = student.get_lesson_price(30)  # Cost of 30-min lesson
        
        if balance < min_lesson_cost:
            warning_msg = f"""⚠️ *Low Balance Warning*

Hi {student.name},

Your account balance is running low:

💰 Current Balance: ${balance:.2f}
💡 Minimum for 30-min lesson: ${min_lesson_cost:.2f}

Please top up your account to continue booking lessons.

Type *fund* for funding options."""
            
            self.send_whatsapp_message(student.phone, warning_msg)
            return True
        return False

    def send_weekly_progress_report(self, student):
        """Send weekly progress report to student"""
        from models import Lesson, LESSON_COMPLETED
        from datetime import timedelta
        
        # Get lessons completed in the last week
        week_ago = datetime.now() - timedelta(days=7)
        recent_lessons = Lesson.query.filter(
            Lesson.student_id == student.id,
            Lesson.status == LESSON_COMPLETED,
            Lesson.completed_date >= week_ago
        ).count()
        
        if recent_lessons > 0:
            progress_percentage = student.get_progress_percentage()
            remaining = student.total_lessons_required - student.lessons_completed
            
            report_msg = f"""📊 *Weekly Progress Report*

Hi {student.name}!

Here's your week in review:

🎯 *This Week:*
• Lessons completed: {recent_lessons}
• Total progress: {progress_percentage:.1f}%
• Lessons remaining: {remaining}

💰 Current balance: ${float(student.account_balance):.2f}

Keep up the excellent work! 🚗

Type *book* to schedule your next lesson."""
            
            self.send_whatsapp_message(student.phone, report_msg)



Hi {lesson.student.name}!

Your driving lesson starts in 2 hours:

🕐 Time: {lesson.scheduled_date.strftime('%I:%M %p')}
👨‍🏫 Instructor: {lesson.instructor.get_full_name()}
📍 Location: {lesson.location or 'Will be confirmed by instructor'}

Please be ready! Good luck! 🚗✨"""

        return self.send_whatsapp_message(lesson.student.phone, message)

    def send_instructor_lesson_reminder(self, lesson):
        """Send lesson reminder to instructor"""
        if not lesson.instructor.phone:
            return False
            
        message = f"""📅 *Lesson Reminder*

You have a lesson in 2 hours:

👤 Student: {lesson.student.name}
📞 Phone: {lesson.student.phone}
🕐 Time: {lesson.scheduled_date.strftime('%I:%M %p')}
⏱️ Duration: {lesson.duration_minutes} minutes
📍 Location: {lesson.location or 'TBD'}

💡 Commands:
• *complete {lesson.id}* after lesson
• *cancel {lesson.id}* if needed"""

        return self.send_whatsapp_message(lesson.instructor.phone, message)

    def send_whatsapp_message(self, phone_number, message):
        """Enhanced WhatsApp message sending with better error handling"""
        try:
            if not self.twilio_client:
                logger.warning(f"Twilio not configured. Mock sending to {phone_number}: {message}")
                return False

            if not self.twilio_phone:
                logger.error("Twilio WhatsApp number not configured")
                return False

            # Clean phone number format
            clean_phone = self.clean_phone_number(phone_number)

            # Prepare message parameters
            from_number = f'whatsapp:{self.twilio_phone}' if not self.twilio_phone.startswith('whatsapp:') else self.twilio_phone
            to_number = f'whatsapp:{clean_phone}'

            # Send message via Twilio
            message_instance = self.twilio_client.messages.create(
                body=message,
                from_=from_number,
                to=to_number
            )

            logger.info(f"WhatsApp message sent successfully to {clean_phone}, SID: {message_instance.sid}")
            return True

        except Exception as e:
            logger.error(f"Failed to send WhatsApp message to {phone_number}: {str(e)}")
            return False


        ).count()

    def instructor_help(self, instructor):
        """Show instructor help"""
        return """❓ Instructor Help - DriveLink

🎯 Quick Commands:
• students - View your assigned students
• today - Today's lesson schedule
• schedule - This week's schedule
• lessons - All upcoming lessons
• menu - Return to main menu

📋 Lesson Management:
• cancel [id] - Cancel a lesson
• confirm [id] - Confirm a lesson  
• complete [id] - Mark lesson complete

💡 Examples:
• "today" - See today's lessons
• "cancel 123" - Cancel lesson #123
• "students" - View all your students

🌐 For advanced features, use the web portal at DriveLink.com

Need more help? Contact your admin!"""

    def set_registration_state(self, phone_number, state, data=None):
        """Set registration state for a phone number"""
        from models import SystemConfig
        import json
        
        registration_key = f"registration_{phone_number}"
        registration_data = {
            'state': state,
            'phone': phone_number,
            'data': data or {},
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            SystemConfig.set_config(registration_key, json.dumps(registration_data), 
                                  f"Registration state for {phone_number}")
        except Exception as e:
            logger.error(f"Error setting registration state: {str(e)}")

    def get_registration_state(self, phone_number):
        """Get registration state for a phone number"""
        from models import SystemConfig
        import json
        
        registration_key = f"registration_{phone_number}"
        
        try:
            data_str = SystemConfig.get_config(registration_key)
            if data_str:
                data = json.loads(data_str)
                # Check if registration is not older than 30 minutes
                registration_time = datetime.fromisoformat(data['timestamp'])
                if (datetime.now() - registration_time).total_seconds() < 1800:  # 30 minutes
                    return data
                else:
                    # Clear expired registration
                    self.clear_registration_state(phone_number)
            return None
        except Exception as e:
            logger.error(f"Error getting registration state: {str(e)}")
            return None

    def clear_registration_state(self, phone_number):
        """Clear registration state for a phone number"""
        from models import SystemConfig
        
        registration_key = f"registration_{phone_number}"
        try:
            config = SystemConfig.query.filter_by(key=registration_key).first()
            if config:
                db.session.delete(config)
                db.session.commit()
        except Exception as e:
            logger.error(f"Error clearing registration state: {str(e)}")

    def handle_registration_step(self, phone_number, message, registration_state):
        """Handle each step of the registration process"""
        state = registration_state['state']
        data = registration_state.get('data', {})
        
        if state == 'awaiting_name':
            # Validate name
            name = message.strip().title()
            if len(name) < 2 or not name.replace(' ', '').isalpha():
                return "Please enter a valid name (letters only). Example: John Doe"
            
            data['name'] = name
            self.set_registration_state(phone_number, 'awaiting_email', data)
            
            return f"""✅ Thanks {name}!

*Step 2 of 5: Email Address*

Please enter your email address:

Example: john@email.com

Or type *skip* if you don't have email"""
        
        elif state == 'awaiting_email':
            if message.lower().strip() == 'skip':
                data['email'] = None
            else:
                email = message.strip().lower()
                if '@' not in email or '.' not in email.split('@')[1]:
                    return "Please enter a valid email address or type *skip*"
                data['email'] = email
            
            self.set_registration_state(phone_number, 'awaiting_location', data)
            
            return f"""✅ Email saved!

*Step 3 of 5: Your Location*

Which area in Harare are you located?

*Available Areas:*
• CBD
• Avondale
• Eastlea  
• Mount Pleasant
• Borrowdale
• Waterfalls
• Highfield
• Glen View
• Other areas

Just type your area name:"""
        
        elif state == 'awaiting_location':
            location = message.strip().title()
            data['location'] = location
            self.set_registration_state(phone_number, 'awaiting_license_type', data)
            
            return f"""✅ Location set to {location}!

*Step 4 of 5: License Type*

What license are you learning for?

1. Class 4 (Light Motor Vehicle)
2. Class 2 (Heavy Motor Vehicle)  
3. Motorcycle
4. Other

Just reply with the number (1, 2, 3, or 4):"""
        
        elif state == 'awaiting_license_type':
            license_types = {
                '1': 'Class 4',
                '2': 'Class 2', 
                '3': 'Motorcycle',
                '4': 'Other'
            }
            
            if message.strip() not in license_types:
                return "Please choose 1, 2, 3, or 4"
            
            data['license_type'] = license_types[message.strip()]
            self.set_registration_state(phone_number, 'awaiting_confirmation', data)
            
            return f"""✅ License type: {license_types[message.strip()]}

*Step 5 of 5: Confirm Registration*

📝 *Your Details:*
• Name: {data['name']}
• Email: {data.get('email', 'Not provided')}
• Location: {data['location']}
• License: {data['license_type']}

Is this correct?

1. Yes, create my account
2. No, start over

Reply with 1 or 2:"""
        
        elif state == 'awaiting_confirmation':
            if message.strip() == '1':
                # Create the student account
                return self.create_student_account(phone_number, data)
            elif message.strip() == '2':
                self.clear_registration_state(phone_number)
                return self.handle_unknown_student(phone_number)
            else:
                return "Please reply with 1 to confirm or 2 to start over"
        
        return "Registration error. Please start over by typing 'register'"

    def create_student_account(self, phone_number, data):
        """Create a new student account from registration data"""
        try:
            from models import Student, User
            
            # Auto-assign instructor based on location and availability
            available_instructor = self.find_best_instructor(data['location'], data['license_type'])
            
            # Create student
            student = Student()
            student.name = data['name']
            student.phone = self.clean_phone_number(phone_number)
            student.email = data.get('email')
            student.current_location = data['location']
            student.license_type = data['license_type']
            student.instructor_id = available_instructor.id if available_instructor else None
            student.account_balance = 0.00
            student.is_active = True
            
            db.session.add(student)
            db.session.commit()
            
            # Clear registration state
            self.clear_registration_state(phone_number)
            
            # Send welcome message with instructor notification
            instructor_name = available_instructor.get_full_name() if available_instructor else "Not assigned yet"
            
            # Notify instructor about new student
            if available_instructor and available_instructor.phone:
                instructor_msg = f"""👋 *New Student Assigned!*

📝 Name: {data['name']}
📞 Phone: {student.phone}
📍 Location: {data['location']}
🎯 License: {data['license_type']}

Welcome them and help them get started! 🚗"""
                
                try:
                    self.send_whatsapp_message(available_instructor.phone, instructor_msg)
                except Exception as e:
                    logger.error(f"Failed to notify instructor: {str(e)}")
            
            response = f"""🎉 *Welcome to DriveLink, {data['name']}!*

Your account has been created successfully! ✅

👤 *Your Profile:*
• Name: {data['name']}
• Location: {data['location']}
• License: {data['license_type']}
• Instructor: {instructor_name}

💰 *Next Steps:*
1. Fund your account to book lessons
2. Type *menu* to see all options
3. Type *help* for available commands

🚗 Ready to start your driving journey!

Your instructor has been notified and will contact you soon.

Type *menu* to get started:"""
            
            logger.info(f"New student account created via WhatsApp: {data['name']} ({phone_number})")
            return response
            
        except Exception as e:
            logger.error(f"Error creating student account: {str(e)}")
            self.clear_registration_state(phone_number)
            return """❌ Sorry, there was an error creating your account.

Please try again or contact our office:
📞 +263 77 123 4567

Type 'register' to try again."""

    def find_best_instructor(self, location, license_type):
        """Find the best instructor for a student based on location and license type"""
        from models import User, Vehicle
        from sqlalchemy import func
        
        try:
            # First, try to find instructor with vehicles for this license class in the area
            instructor = db.session.query(User).join(Vehicle, User.id == Vehicle.instructor_id).filter(
                User.role == 'instructor',
                User.active == True,
                Vehicle.license_class == license_type,  
                Vehicle.is_active == True,
                User.base_location.ilike(f'%{location}%')
            ).first()
            
            if instructor:
                return instructor
            
            # Fallback: find instructor with least students in the area
            instructor = db.session.query(User).outerjoin(Student, User.id == Student.instructor_id).filter(
                User.role == 'instructor',
                User.active == True,
                User.base_location.ilike(f'%{location}%')
            ).group_by(User.id).order_by(func.count(Student.id)).first()
            
            if instructor:
                return instructor
            
            # Final fallback: any active instructor
            return User.query.filter_by(role='instructor', active=True).first()
            
        except Exception as e:
            logger.error(f"Error finding instructor: {str(e)}")
            return User.query.filter_by(role='instructor', active=True).first()

# Global bot instance - will be initialized later with app context
whatsapp_bot = WhatsAppBot()

def webhook_handler():
    """Handle incoming WhatsApp webhooks from Twilio with button support"""
    try:
        # Ensure Twilio client is initialized (in case environment changed)
        if not whatsapp_bot.twilio_client:
            whatsapp_bot.initialize_twilio()

        # Get Twilio webhook data
        from_number = request.form.get('From', '')
        message_body = request.form.get('Body', '')

        # Check for button response data (2025 Twilio format)
        button_text = request.form.get('ButtonText', '')
        button_payload = request.form.get('ButtonPayload', '')
        original_message_sid = request.form.get('OriginalRepliedMessageSid', '')

        if from_number:
            # Clean the phone number (remove whatsapp: prefix)
            clean_phone = from_number.replace('whatsapp:', '')

            # Process button response or regular message
            if button_text and button_payload:
                logger.info(f"✅ Button response from {clean_phone}: {button_text} (ID: {button_payload})")
                response_text = whatsapp_bot.process_button_response(clean_phone, button_text, button_payload)
            elif message_body:
                logger.info(f"📝 Text message from {clean_phone}: {message_body}")
                response_text = whatsapp_bot.process_message(clean_phone, message_body)
            else:
                logger.warning(f"⚠️ Empty message from {clean_phone}")
                response_text = "Sorry, I didn't receive any message content. Please try again."

            # Create TwiML response
            twiml_response = MessagingResponse()
            twiml_response.message(response_text)

            return str(twiml_response), 200, {'Content-Type': 'text/xml'}

        return jsonify({'error': 'Missing required parameters'}), 400

    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}")
        # Return friendly error message
        twiml_response = MessagingResponse()
        twiml_response.message("Sorry, I'm having trouble right now. Please try again later.")
        return str(twiml_response), 500, {'Content-Type': 'text/xml'}

def send_whatsapp_message(phone_number, message, buttons=None):
    """Send WhatsApp message via Twilio with optional interactive buttons"""
    try:
        if not whatsapp_bot.twilio_client:
            logger.warning(f"Twilio not configured. Mock sending to {phone_number}: {message}")
            return False

        if not whatsapp_bot.twilio_phone:
            logger.error("Twilio WhatsApp number not configured")
            return False

        # Clean phone number format
        clean_phone = whatsapp_bot.clean_phone_number(phone_number)

        # Prepare message parameters
        message_params = {
            'body': message,
            'from_': f'whatsapp:{whatsapp_bot.twilio_phone}',
            'to': f'whatsapp:{clean_phone}'
        }

        # Add interactive buttons if provided and supported
        if buttons and len(buttons) <= 3:  # WhatsApp allows max 3 buttons
            # For now, we'll append button options to the message
            # Full interactive buttons require WhatsApp Business API approval
            button_text = "\n\n🔘 *Quick replies:*\n"
            for i, button in enumerate(buttons, 1):
                button_text += f"• {button}\n"
            message_params['body'] += button_text

        # Send message via Twilio
        message_instance = whatsapp_bot.twilio_client.messages.create(**message_params)

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