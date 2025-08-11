import logging
import os
import json
import base64
import uuid
from datetime import datetime, timedelta
from flask import request, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy import and_, or_
from models import (
    User, Student, Lesson, WhatsAppSession, db, 
    LESSON_SCHEDULED, LESSON_COMPLETED, LESSON_CANCELLED,
    ROLE_STUDENT, ROLE_INSTRUCTOR, ROLE_ADMIN, ROLE_SUPER_ADMIN
)
import requests
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedWhatsAppBot:
    """Enhanced WhatsApp bot supporting all user roles with document upload capabilities"""
    
    def __init__(self):
        self.twilio_client = None
        self.twilio_phone = None
        self.initialize_twilio()
        
        # Upload folder for documents
        self.upload_folder = 'static/uploads'
        os.makedirs(self.upload_folder, exist_ok=True)
        
        # Allowed file extensions for documents
        self.allowed_extensions = {'png', 'jpg', 'jpeg', 'pdf', 'doc', 'docx'}
        
    def initialize_twilio(self):
        """Initialize Twilio client with credentials"""
        try:
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            self.twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
            
            if account_sid and auth_token:
                self.twilio_client = Client(account_sid, auth_token)
                logger.info("✅ Enhanced WhatsApp Bot initialized successfully")
                logger.info(f"📞 Using Twilio phone: {self.twilio_phone}")
            else:
                logger.warning("⚠️ Twilio credentials not found")
                
        except Exception as e:
            logger.error(f"Failed to initialize Twilio: {str(e)}")
    
    def clean_phone_number(self, phone):
        """Clean and format phone number"""
        clean = ''.join(filter(str.isdigit, phone))
        
        # Add country code if not present (assuming Zimbabwe +263)
        if not clean.startswith('263'):
            if clean.startswith('0'):
                clean = '263' + clean[1:]
            else:
                clean = '263' + clean
        
        return '+' + clean
    
    def get_or_create_session(self, phone_number, user_id=None, user_type='unknown'):
        """Get or create WhatsApp session for any user type"""
        session_id = f"whatsapp_{phone_number}_{datetime.now().strftime('%Y%m%d')}"
        session = WhatsAppSession.query.filter_by(session_id=session_id).first()
        
        if not session:
            session = WhatsAppSession()
            session.session_id = session_id
            session.phone_number = phone_number
            session.user_id = user_id
            session.user_type = user_type
            session.session_data = json.dumps({})
            session.created_at = datetime.now()
            session.is_active = True
            db.session.add(session)
        
        session.last_activity = datetime.now()
        session.is_active = True
        db.session.commit()
        return session
    
    def get_session_data(self, session):
        """Get session data as dictionary"""
        try:
            return json.loads(session.session_data or '{}')
        except:
            return {}
    
    def update_session_data(self, session, data):
        """Update session data"""
        session.session_data = json.dumps(data)
        session.last_activity = datetime.now()
        db.session.commit()
    
    def identify_user(self, phone_number):
        """Identify user type and return user object"""
        # Check for instructor/admin/super_admin
        user = User.query.filter_by(phone=phone_number, active=True).first()
        if user:
            return user, user.role
        
        # Check for student
        student = Student.query.filter_by(phone=phone_number, is_active=True).first()
        if student:
            return student, ROLE_STUDENT
        
        return None, 'unknown'
    
    def process_message(self, phone_number, message, media_url=None):
        """Main message processing entry point"""
        try:
            phone_number = self.clean_phone_number(phone_number)
            user, user_type = self.identify_user(phone_number)
            
            # Get or create session
            session = self.get_or_create_session(
                phone_number, 
                user.id if user else None, 
                user_type
            )
            
            # Handle media (document uploads)
            if media_url:
                return self.handle_media_upload(session, user, user_type, media_url, message)
            
            # Route to appropriate handler based on user type
            if user_type == 'unknown':
                return self.handle_new_student_registration(session, message)
            elif user_type == ROLE_STUDENT:
                return self.handle_student_message(session, user, message)
            elif user_type == ROLE_INSTRUCTOR:
                return self.handle_instructor_message(session, user, message)
            elif user_type == ROLE_ADMIN:
                return self.handle_admin_message(session, user, message)
            elif user_type == ROLE_SUPER_ADMIN:
                return self.handle_super_admin_message(session, user, message)
            
            return "I'm not sure how to help you. Please contact support."
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return "Sorry, I'm having technical difficulties. Please try again later."
    
    def handle_new_student_registration(self, session, message):
        """Handle new student registration process"""
        session_data = self.get_session_data(session)
        registration_step = session_data.get('registration_step', 'start')
        
        if registration_step == 'start' or message.lower() in ['hi', 'hello', 'start', 'register']:
            session_data['registration_step'] = 'name'
            self.update_session_data(session, session_data)
            
            return (
                "👋 Welcome to DriveLink! I'm here to help you get started with driving lessons.\n\n"
                "To register as a new student, I'll need some information from you.\n\n"
                "First, what is your full name?"
            )
        
        elif registration_step == 'name':
            session_data['name'] = message.strip()
            session_data['registration_step'] = 'email'
            self.update_session_data(session, session_data)
            
            return f"Nice to meet you, {message.strip()}! What is your email address?"
        
        elif registration_step == 'email':
            session_data['email'] = message.strip()
            session_data['registration_step'] = 'location'
            self.update_session_data(session, session_data)
            
            return "Great! What city/area are you located in? This helps us find instructors near you."
        
        elif registration_step == 'location':
            session_data['location'] = message.strip()
            session_data['registration_step'] = 'documents'
            self.update_session_data(session, session_data)
            
            return (
                "Perfect! Now I need you to upload your documents for verification.\n\n"
                "Please send me the following documents one by one:\n"
                "1. 📄 National ID or Passport\n"
                "2. 📄 Provisional Driving License (if you have one)\n"
                "3. 📄 Proof of Residence\n"
                "4. 📸 Profile Photo\n\n"
                "Send your National ID first as a photo or PDF."
            )
        
        elif registration_step == 'documents':
            return (
                "Please send your documents as photos or PDF files.\n\n"
                "I'm waiting for:\n"
                "1. 📄 National ID or Passport\n"
                "2. 📄 Provisional Driving License\n"
                "3. 📄 Proof of Residence\n"
                "4. 📸 Profile Photo\n\n"
                "Send them one by one."
            )
        
        return "I didn't understand that. Please type 'start' to begin registration."
    
    def handle_media_upload(self, session, user, user_type, media_url, message):
        """Handle document/media uploads"""
        try:
            session_data = self.get_session_data(session)
            
            if user_type == 'unknown' and session_data.get('registration_step') == 'documents':
                return self.handle_student_document_upload(session, media_url, message)
            
            return "I can process your document. What type of document is this?"
            
        except Exception as e:
            logger.error(f"Error handling media upload: {str(e)}")
            return "Sorry, I couldn't process your document. Please try again."
    
    def handle_student_document_upload(self, session, media_url, message):
        """Handle document uploads during student registration"""
        try:
            session_data = self.get_session_data(session)
            documents = session_data.get('documents', {})
            
            # Download and save the document
            file_path = self.download_and_save_media(media_url, session.phone_number)
            
            if not file_path:
                return "Sorry, I couldn't download your document. Please try again."
            
            # Determine document type based on upload progress
            doc_count = len(documents)
            
            if doc_count == 0:
                documents['national_id'] = file_path
                next_doc = "Provisional Driving License"
            elif doc_count == 1:
                documents['provisional_license'] = file_path
                next_doc = "Proof of Residence"
            elif doc_count == 2:
                documents['proof_of_residence'] = file_path
                next_doc = "Profile Photo"
            elif doc_count == 3:
                documents['profile_photo'] = file_path
                next_doc = None
            
            session_data['documents'] = documents
            
            if next_doc:
                self.update_session_data(session, session_data)
                return f"✅ Document received! Now please send your {next_doc}."
            else:
                # All documents received, create student account
                return self.complete_student_registration(session, session_data)
                
        except Exception as e:
            logger.error(f"Error handling student document upload: {str(e)}")
            return "Sorry, I couldn't process your document. Please try again."
    
    def download_and_save_media(self, media_url, phone_number):
        """Download and save media file from Twilio"""
        try:
            # Create user-specific directory
            user_dir = os.path.join(self.upload_folder, f"student_{phone_number}")
            os.makedirs(user_dir, exist_ok=True)
            
            # Download the file
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            
            if account_sid and auth_token:
                response = requests.get(media_url, auth=(account_sid, auth_token))
            else:
                return None
            
            if response.status_code == 200:
                # Generate unique filename
                file_extension = 'jpg'  # Default to jpg
                content_type = response.headers.get('content-type', '')
                
                if 'pdf' in content_type:
                    file_extension = 'pdf'
                elif 'png' in content_type:
                    file_extension = 'png'
                
                filename = f"{uuid.uuid4().hex}.{file_extension}"
                file_path = os.path.join(user_dir, filename)
                
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                
                return file_path
            
        except Exception as e:
            logger.error(f"Error downloading media: {str(e)}")
        
        return None
    
    def complete_student_registration(self, session, session_data):
        """Complete student registration and create account"""
        try:
            # Create new student
            student = Student()
            student.name = session_data['name']
            student.email = session_data['email']
            student.phone = session.phone_number
            student.current_location = session_data['location']
            student.is_active = True
            
            # Store documents info in address field for now (can be enhanced later)
            documents = session_data.get('documents', {})
            doc_info = f"Documents uploaded: {', '.join(documents.keys())}"
            student.address = doc_info
            
            db.session.add(student)
            db.session.commit()
            
            # Clear registration session
            session_data = {'registration_complete': True}
            self.update_session_data(session, session_data)
            
            return (
                "🎉 Congratulations! Your registration is complete.\n\n"
                "✅ All documents received\n"
                "⏳ Your account is under review\n\n"
                "You'll receive confirmation within 24 hours. Once approved, you can:\n"
                "• Browse instructors\n"
                "• Book lessons\n"
                "• Track your progress\n\n"
                "Type 'menu' anytime to see available options."
            )
            
        except Exception as e:
            logger.error(f"Error completing registration: {str(e)}")
            db.session.rollback()
            return "Sorry, there was an error completing your registration. Please contact support."
    
    def handle_student_message(self, session, student, message):
        """Handle messages from registered students"""
        message = message.lower().strip()
        session_data = self.get_session_data(session)
        
        # Handle instructor selection flow
        if session_data.get('selecting_instructor'):
            if session_data.get('selected_instructor_id'):
                return self.handle_instructor_detail_action(session, student, message)
            else:
                return self.handle_instructor_selection(session, student, message)
        
        # Handle instructor switching flow
        if session_data.get('switching_instructor'):
            return self.handle_instructor_switching(session, student, message)
        
        # Handle booking flow
        if session_data.get('booking_lesson'):
            return self.handle_lesson_booking_flow(session, student, message)
        
        # Main menu options
        if message in ['menu', 'help', 'start']:
            return self.get_student_menu(student)
        elif message in ['1', 'find', 'instructors']:
            return self.start_instructor_search(session, student)
        elif message in ['2', 'current', 'instructor']:
            return self.show_current_instructor(student)
        elif message in ['3', 'book']:
            return self.start_lesson_booking(session, student)
        elif message in ['4', 'lessons']:
            return self.show_student_lessons(student)
        elif message in ['5', 'progress']:
            return self.show_student_progress(student)
        elif message in ['6', 'switch']:
            return self.start_instructor_switch(session, student)
        elif message in ['7', 'profile']:
            return self.show_student_profile(student)
        else:
            return self.get_student_menu(student)
    
    def handle_instructor_message(self, session, instructor, message):
        """Handle messages from instructors"""
        message = message.lower().strip()
        
        if message in ['menu', 'help', 'start']:
            return self.get_instructor_menu(instructor)
        elif message in ['1', 'students']:
            return self.show_instructor_students(instructor)
        elif message in ['2', 'today']:
            return self.show_today_lessons(instructor)
        elif message in ['3', 'schedule']:
            return self.show_instructor_schedule(instructor)
        elif message in ['4', 'earnings']:
            return self.show_instructor_earnings(instructor)
        elif message in ['5', 'profile']:
            return self.show_instructor_profile(instructor)
        else:
            return self.get_instructor_menu(instructor)
    
    def handle_admin_message(self, session, admin, message):
        """Handle messages from admins"""
        message = message.lower().strip()
        
        if message in ['menu', 'help', 'start']:
            return self.get_admin_menu(admin)
        elif message in ['1', 'students']:
            return self.show_all_students(admin)
        elif message in ['2', 'instructors']:
            return self.show_all_instructors(admin)
        elif message in ['3', 'lessons']:
            return self.show_all_lessons(admin)
        elif message in ['4', 'approvals']:
            return self.show_pending_approvals(admin)
        elif message in ['5', 'reports']:
            return self.show_admin_reports(admin)
        else:
            return self.get_admin_menu(admin)
    
    def handle_super_admin_message(self, session, super_admin, message):
        """Handle messages from super admins"""
        message = message.lower().strip()
        
        if message in ['menu', 'help', 'start']:
            return self.get_super_admin_menu(super_admin)
        elif message in ['1', 'users']:
            return self.show_all_users(super_admin)
        elif message in ['2', 'system']:
            return self.show_system_stats(super_admin)
        elif message in ['3', 'settings']:
            return self.show_system_settings(super_admin)
        elif message in ['4', 'logs']:
            return self.show_system_logs(super_admin)
        else:
            return self.get_super_admin_menu(super_admin)
    
    # Menu methods for different user types
    def get_student_menu(self, student):
        current_instructor = f"\n📍 Current Instructor: {student.instructor.get_full_name()}" if student.instructor_id else "\n📍 No instructor assigned yet"
        
        return (
            f"🎓 Welcome {student.name}!{current_instructor}\n\n"
            "What would you like to do?\n\n"
            "1️⃣ Find Instructors Near Me\n"
            "2️⃣ View My Current Instructor\n"
            "3️⃣ Book New Lesson\n"
            "4️⃣ View My Lessons\n"
            "5️⃣ My Progress\n"
            "6️⃣ Switch Instructor\n"
            "7️⃣ My Profile\n\n"
            "Reply with a number (1-7) or type the option name."
        )
    
    def get_instructor_menu(self, instructor):
        return (
            f"👨‍🏫 Welcome {instructor.get_full_name()}!\n\n"
            "Instructor Dashboard:\n\n"
            "1️⃣ My Students\n"
            "2️⃣ Today's Lessons\n"
            "3️⃣ Full Schedule\n"
            "4️⃣ Earnings\n"
            "5️⃣ My Profile\n\n"
            "Reply with a number (1-5) or type the option name."
        )
    
    def get_admin_menu(self, admin):
        return (
            f"👨‍💼 Welcome {admin.get_full_name()}!\n\n"
            "Admin Dashboard:\n\n"
            "1️⃣ All Students\n"
            "2️⃣ All Instructors\n"
            "3️⃣ All Lessons\n"
            "4️⃣ Pending Approvals\n"
            "5️⃣ Reports\n\n"
            "Reply with a number (1-5) or type the option name."
        )
    
    def get_super_admin_menu(self, super_admin):
        return (
            f"🔧 Welcome {super_admin.get_full_name()}!\n\n"
            "Super Admin Dashboard:\n\n"
            "1️⃣ All Users\n"
            "2️⃣ System Statistics\n"
            "3️⃣ System Settings\n"
            "4️⃣ System Logs\n\n"
            "Reply with a number (1-4) or type the option name."
        )
    
    # Placeholder methods for specific functionalities
    def show_student_lessons(self, student):
        lessons = Lesson.query.filter_by(student_id=student.id).order_by(Lesson.lesson_date.desc()).limit(5).all()
        if not lessons:
            return "📚 You don't have any lessons yet. Type '2' to book your first lesson!"
        
        response = "📚 Your Recent Lessons:\n\n"
        for lesson in lessons:
            response += f"📅 {lesson.lesson_date.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"👨‍🏫 {lesson.instructor.get_full_name()}\n"
            response += f"⏱️ {lesson.duration} minutes\n"
            response += f"📍 Status: {lesson.status}\n\n"
        
        return response + "Type 'menu' to return to main menu."
    
    def start_lesson_booking(self, session, student):
        """Start the lesson booking process"""
        if not student.instructor_id:
            return (
                "❌ You need to select an instructor first!\n\n"
                "Use option 1 from the main menu to find and select an instructor, "
                "then you can book lessons.\n\n"
                "Type 'menu' to return to main menu."
            )
        
        instructor = User.query.get(student.instructor_id)
        if not instructor or not instructor.active:
            return (
                "❌ Your assigned instructor is currently unavailable.\n\n"
                "Please select a new instructor or contact support.\n\n"
                "Type 'menu' to return to main menu."
            )
        
        session_data = self.get_session_data(session)
        session_data['booking_lesson'] = True
        session_data['booking_step'] = 'duration'
        self.update_session_data(session, session_data)
        
        return (
            f"📅 Booking lesson with {instructor.get_full_name()}\n\n"
            "Select lesson duration:\n\n"
            f"1️⃣ 30 minutes - ${instructor.hourly_rate_30min or 15}\n"
            f"2️⃣ 60 minutes - ${instructor.hourly_rate_60min or 25}\n\n"
            "3️⃣ Cancel booking\n\n"
            "Choose your option:"
        )
    
    def handle_lesson_booking_flow(self, session, student, message):
        """Handle the lesson booking flow"""
        session_data = self.get_session_data(session)
        booking_step = session_data.get('booking_step')
        
        if message == '3' or message == 'cancel':
            session_data.pop('booking_lesson', None)
            session_data.pop('booking_step', None)
            self.update_session_data(session, session_data)
            return "❌ Booking cancelled. Type 'menu' to return to main menu."
        
        if booking_step == 'duration':
            if message == '1':
                session_data['lesson_duration'] = 30
                session_data['booking_step'] = 'confirm'
                self.update_session_data(session, session_data)
                return self.show_booking_confirmation(session, student)
            elif message == '2':
                session_data['lesson_duration'] = 60
                session_data['booking_step'] = 'confirm'
                self.update_session_data(session, session_data)
                return self.show_booking_confirmation(session, student)
            else:
                return "Please select 1 for 30 minutes, 2 for 60 minutes, or 3 to cancel."
        
        elif booking_step == 'confirm':
            if message == '1':
                return self.complete_lesson_booking(session, student)
            elif message == '2':
                session_data['booking_step'] = 'duration'
                self.update_session_data(session, session_data)
                return self.start_lesson_booking(session, student)
            else:
                return "Please select 1 to confirm or 2 to change duration."
        
        return "Invalid option. Type 'menu' to return to main menu."
    
    def show_booking_confirmation(self, session, student):
        """Show booking confirmation details"""
        session_data = self.get_session_data(session)
        duration = session_data.get('lesson_duration')
        instructor = User.query.get(student.instructor_id)
        
        if duration == 30:
            price = instructor.hourly_rate_30min or 15
        else:
            price = instructor.hourly_rate_60min or 25
        
        # Check if student has enough balance
        balance_sufficient = student.account_balance >= price
        balance_warning = "" if balance_sufficient else "\n⚠️ Insufficient balance! Please add funds first."
        
        response = f"📅 Lesson Booking Confirmation\n\n"
        response += f"👨‍🏫 Instructor: {instructor.get_full_name()}\n"
        response += f"⏱️ Duration: {duration} minutes\n"
        response += f"💰 Cost: ${price}\n"
        response += f"💳 Your Balance: ${student.account_balance}\n"
        response += balance_warning
        response += "\n\nNext available time slots will be shown after confirmation.\n"
        response += "For specific time requests, contact your instructor.\n\n"
        
        if balance_sufficient:
            response += "1️⃣ Confirm Booking\n"
        response += "2️⃣ Change Duration\n"
        response += "3️⃣ Cancel"
        
        return response
    
    def complete_lesson_booking(self, session, student):
        """Complete the lesson booking"""
        try:
            session_data = self.get_session_data(session)
            duration = session_data.get('lesson_duration')
            instructor = User.query.get(student.instructor_id)
            
            if duration == 30:
                price = instructor.hourly_rate_30min or 15
            else:
                price = instructor.hourly_rate_60min or 25
            
            # Check balance again
            if student.account_balance < price:
                return "❌ Insufficient balance. Please add funds and try again."
            
            # Create lesson (in real implementation, would schedule for specific time)
            from datetime import datetime, timedelta
            lesson_time = datetime.now() + timedelta(days=1)  # Default to tomorrow
            
            lesson = Lesson()
            lesson.student_id = student.id
            lesson.instructor_id = instructor.id
            lesson.lesson_date = lesson_time
            lesson.duration_minutes = duration
            lesson.cost = price
            lesson.status = LESSON_SCHEDULED
            lesson.location = f"{instructor.base_location} (Details via instructor)"
            
            db.session.add(lesson)
            
            # Update student balance (reserve the amount)
            student.account_balance -= price
            
            db.session.commit()
            
            # Clear booking session
            session_data.pop('booking_lesson', None)
            session_data.pop('booking_step', None)
            session_data.pop('lesson_duration', None)
            self.update_session_data(session, session_data)
            
            return (
                f"✅ Lesson booked successfully!\n\n"
                f"📋 Booking Details:\n"
                f"• Instructor: {instructor.get_full_name()}\n"
                f"• Duration: {duration} minutes\n"
                f"• Cost: ${price}\n"
                f"• Status: Scheduled\n"
                f"• Lesson ID: {lesson.id}\n\n"
                f"📱 Your instructor will contact you to confirm the exact time and location.\n"
                f"💳 Remaining balance: ${student.account_balance}\n\n"
                f"Type 'menu' to return to main menu."
            )
            
        except Exception as e:
            logger.error(f"Error completing lesson booking: {str(e)}")
            db.session.rollback()
            return "❌ Booking failed. Please try again or contact support."
    
    def start_instructor_search(self, session, student):
        """Start the instructor search flow"""
        instructors = User.query.filter_by(role=ROLE_INSTRUCTOR, active=True, is_verified=True).limit(10).all()
        
        if not instructors:
            return "❌ No verified instructors available at the moment. Please try again later."
        
        # Calculate distances if student has location
        if student.latitude and student.longitude:
            # Sort by distance (simplified - in production use proper geolocation)
            instructors = sorted(instructors, key=lambda x: self.calculate_distance(
                student.latitude, student.longitude, 
                x.latitude or 0, x.longitude or 0
            ))
        
        # Store instructor list in session
        session_data = self.get_session_data(session)
        session_data['selecting_instructor'] = True
        session_data['instructor_list'] = [instructor.id for instructor in instructors]
        session_data['current_page'] = 0
        self.update_session_data(session, session_data)
        
        return self.show_instructor_list(instructors[:5], student, 0, len(instructors))
    
    def show_instructor_list(self, instructors, student, page, total):
        """Show a paginated list of instructors"""
        response = f"👨‍🏫 Available Instructors ({len(instructors)} of {total}):\n\n"
        
        for i, instructor in enumerate(instructors, 1):
            distance_text = ""
            if student.latitude and instructor.latitude:
                distance = self.calculate_distance(
                    student.latitude, student.longitude,
                    instructor.latitude, instructor.longitude
                )
                distance_text = f" ({distance:.1f}km away)"
            
            response += f"{i}️⃣ {instructor.get_full_name()}{distance_text}\n"
            response += f"📍 {instructor.base_location or 'Location not set'}\n"
            response += f"⭐ {instructor.experience_years or 0} years experience\n"
            response += f"💰 ${instructor.hourly_rate_60min or 25}/hour\n"
            response += f"⭐ Rating: {instructor.average_rating or 'New'}/5.0\n\n"
        
        response += "Reply with:\n"
        response += "• Number (1-5) to select instructor\n"
        if page > 0:
            response += "• 'prev' for previous page\n"
        if (page + 1) * 5 < total:
            response += "• 'next' for more instructors\n"
        response += "• 'menu' to return to main menu"
        
        return response
    
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points (simplified)"""
        # Simplified distance calculation for demo
        import math
        return math.sqrt((lat2 - lat1)**2 + (lon2 - lon1)**2) * 100  # Rough km conversion
    
    def handle_instructor_selection(self, session, student, message):
        """Handle instructor selection during search"""
        session_data = self.get_session_data(session)
        instructor_list = session_data.get('instructor_list', [])
        current_page = session_data.get('current_page', 0)
        
        if message == 'menu':
            session_data.pop('selecting_instructor', None)
            session_data.pop('instructor_list', None)
            self.update_session_data(session, session_data)
            return self.get_student_menu(student)
        
        elif message == 'next':
            next_page = current_page + 1
            start_idx = next_page * 5
            if start_idx < len(instructor_list):
                session_data['current_page'] = next_page
                self.update_session_data(session, session_data)
                instructors = User.query.filter(User.id.in_(instructor_list[start_idx:start_idx+5])).all()
                return self.show_instructor_list(instructors, student, next_page, len(instructor_list))
            else:
                return "No more instructors to show. Type 'menu' to return."
        
        elif message == 'prev':
            if current_page > 0:
                prev_page = current_page - 1
                start_idx = prev_page * 5
                session_data['current_page'] = prev_page
                self.update_session_data(session, session_data)
                instructors = User.query.filter(User.id.in_(instructor_list[start_idx:start_idx+5])).all()
                return self.show_instructor_list(instructors, student, prev_page, len(instructor_list))
            else:
                return "Already on first page. Type 'menu' to return."
        
        elif message.isdigit():
            choice = int(message)
            start_idx = current_page * 5
            if 1 <= choice <= 5 and start_idx + choice - 1 < len(instructor_list):
                instructor_id = instructor_list[start_idx + choice - 1]
                instructor = User.query.get(instructor_id)
                return self.show_instructor_details(session, student, instructor)
            else:
                return "Invalid selection. Please choose a number from the list or type 'menu'."
        
        else:
            return "Please choose a number (1-5), 'next', 'prev', or 'menu'."
    
    def show_instructor_details(self, session, student, instructor):
        """Show detailed instructor information and selection options"""
        distance_text = ""
        if student.latitude and instructor.latitude:
            distance = self.calculate_distance(
                student.latitude, student.longitude,
                instructor.latitude, instructor.longitude
            )
            distance_text = f"\n📏 Distance: {distance:.1f}km from you"
        
        availability_text = "Available" if instructor.active else "Currently unavailable"
        
        response = f"👨‍🏫 {instructor.get_full_name()}\n\n"
        response += f"📍 Base Location: {instructor.base_location or 'Not specified'}{distance_text}\n"
        response += f"⭐ Experience: {instructor.experience_years or 0} years\n"
        response += f"💰 Rates: ${instructor.hourly_rate_30min or 15}/30min | ${instructor.hourly_rate_60min or 25}/60min\n"
        response += f"⭐ Rating: {instructor.average_rating or 'New'}/5.0 ({instructor.total_lessons_taught or 0} lessons taught)\n"
        response += f"✅ Status: {availability_text}\n"
        
        if instructor.bio:
            response += f"\n📝 About: {instructor.bio[:100]}{'...' if len(instructor.bio) > 100 else ''}\n"
        
        # Store instructor for selection
        session_data = self.get_session_data(session)
        session_data['selected_instructor_id'] = instructor.id
        self.update_session_data(session, session_data)
        
        response += "\nWhat would you like to do?\n"
        response += "1️⃣ Select This Instructor\n"
        response += "2️⃣ View Their Reviews\n"
        response += "3️⃣ Check Availability\n"
        response += "4️⃣ Back to List\n"
        response += "5️⃣ Main Menu"
        
        return response
    
    def handle_instructor_detail_action(self, session, student, message):
        """Handle actions from instructor detail view"""
        session_data = self.get_session_data(session)
        instructor_id = session_data.get('selected_instructor_id')
        
        if not instructor_id:
            return "Session expired. Please search for instructors again."
        
        instructor = User.query.get(instructor_id)
        if not instructor:
            return "Instructor not found. Please search again."
        
        if message == '1':  # Select instructor
            return self.assign_instructor_to_student(session, student, instructor)
        elif message == '2':  # View reviews
            return self.show_instructor_reviews(instructor)
        elif message == '3':  # Check availability
            return self.show_instructor_availability(instructor)
        elif message == '4':  # Back to list
            return self.start_instructor_search(session, student)
        elif message == '5' or message == 'menu':  # Main menu
            session_data.pop('selecting_instructor', None)
            session_data.pop('selected_instructor_id', None)
            self.update_session_data(session, session_data)
            return self.get_student_menu(student)
        else:
            return "Please select 1-5 or type 'menu'."
    
    def assign_instructor_to_student(self, session, student, instructor):
        """Assign selected instructor to student"""
        try:
            # Check if instructor is available
            if not instructor.active:
                return "❌ This instructor is currently unavailable. Please select another instructor."
            
            # Update student's instructor
            old_instructor_id = student.instructor_id
            student.instructor_id = instructor.id
            db.session.commit()
            
            # Clear selection session
            session_data = self.get_session_data(session)
            session_data.pop('selecting_instructor', None)
            session_data.pop('selected_instructor_id', None)
            session_data.pop('switching_instructor', None)
            self.update_session_data(session, session_data)
            
            action = "switched to" if old_instructor_id else "assigned"
            
            return (
                f"✅ Instructor {action} successfully!\n\n"
                f"👨‍🏫 Your instructor: {instructor.get_full_name()}\n"
                f"📍 Location: {instructor.base_location or 'Not specified'}\n"
                f"📱 Phone: {instructor.phone or 'Contact via app'}\n"
                f"💰 Rates: ${instructor.hourly_rate_30min or 15}/30min | ${instructor.hourly_rate_60min or 25}/60min\n\n"
                f"🎉 You can now book lessons with your instructor!\n"
                f"Your instructor will be notified about your assignment.\n\n"
                f"Type 'menu' to see all available options."
            )
            
        except Exception as e:
            logger.error(f"Error assigning instructor: {str(e)}")
            db.session.rollback()
            return "❌ Failed to assign instructor. Please try again."
    
    def show_instructor_reviews(self, instructor):
        """Show instructor reviews and ratings"""
        # In a real implementation, you'd have a reviews table
        total_lessons = instructor.total_lessons_taught or 0
        avg_rating = instructor.average_rating or 0
        
        response = f"⭐ Reviews for {instructor.get_full_name()}\n\n"
        response += f"📊 Overall Rating: {avg_rating:.1f}/5.0\n"
        response += f"📚 Total Lessons Taught: {total_lessons}\n\n"
        
        if total_lessons == 0:
            response += "🆕 This instructor is new to the platform.\n"
            response += "Be the first to book and review!\n\n"
        else:
            response += "Recent student feedback:\n"
            response += "• 'Great instructor, very patient'\n"
            response += "• 'Clear explanations and good teaching'\n"
            response += "• 'Helped me pass my test!'\n\n"
            response += "💡 Book a lesson to experience their teaching style.\n\n"
        
        response += "1️⃣ Select This Instructor\n"
        response += "2️⃣ Back to Details\n"
        response += "3️⃣ Main Menu"
        
        return response
    
    def show_instructor_availability(self, instructor):
        """Show instructor availability information"""
        response = f"📅 Availability for {instructor.get_full_name()}\n\n"
        
        if instructor.active:
            response += "✅ Currently accepting new students\n"
            response += "📅 Typical availability:\n"
            response += "• Monday - Friday: 8:00 AM - 6:00 PM\n"
            response += "• Saturday: 9:00 AM - 3:00 PM\n"
            response += "• Sunday: By appointment\n\n"
            response += "⏰ Flexible scheduling available\n"
            response += "📱 Contact after booking for specific times\n\n"
        else:
            response += "❌ Currently not accepting new students\n"
            response += "📞 Please check back later or select another instructor\n\n"
        
        response += "1️⃣ Select This Instructor\n"
        response += "2️⃣ Back to Details\n"
        response += "3️⃣ Main Menu"
        
        return response
    
    def start_instructor_switch(self, session, student):
        """Start the instructor switching process"""
        if not student.instructor_id:
            return "You don't have an assigned instructor yet. Use option 1 to find instructors."
        
        if not student.can_switch_instructor():
            return (
                "❌ You can only switch instructors after:\n"
                "• Completing 5 lessons with current instructor, OR\n"
                "• Being registered for 1 week\n\n"
                "This policy ensures continuity in your learning.\n"
                "Type 'menu' to return to main menu."
            )
        
        current_instructor = User.query.get(student.instructor_id)
        response = f"Current instructor: {current_instructor.get_full_name()}\n\n"
        response += "⚠️ Switching instructors will:\n"
        response += "• End your current instructor relationship\n"
        response += "• Allow you to select a new instructor\n"
        response += "• May affect lesson continuity\n\n"
        response += "Are you sure you want to switch?\n"
        response += "1️⃣ Yes, Find New Instructor\n"
        response += "2️⃣ No, Keep Current Instructor"
        
        session_data = self.get_session_data(session)
        session_data['switching_instructor'] = True
        self.update_session_data(session, session_data)
        
        return response
    
    def show_current_instructor(self, student):
        """Show current instructor details"""
        if not student.instructor_id:
            return "You don't have an assigned instructor yet. Use option 1 to find and select an instructor."
        
        instructor = User.query.get(student.instructor_id)
        if not instructor:
            return "Your assigned instructor is no longer available. Please select a new instructor."
        
        # Get lesson stats with this instructor
        lessons_with_instructor = Lesson.query.filter_by(
            student_id=student.id, 
            instructor_id=instructor.id
        ).count()
        
        completed_lessons = Lesson.query.filter_by(
            student_id=student.id,
            instructor_id=instructor.id,
            status=LESSON_COMPLETED
        ).count()
        
        response = f"👨‍🏫 Your Instructor: {instructor.get_full_name()}\n\n"
        response += f"📍 Location: {instructor.base_location or 'Not specified'}\n"
        response += f"📱 Phone: {instructor.phone or 'Contact via app'}\n"
        response += f"⭐ Experience: {instructor.experience_years or 0} years\n"
        response += f"⭐ Rating: {instructor.average_rating or 'Not rated'}/5.0\n\n"
        
        response += f"📊 Your Progress Together:\n"
        response += f"• Total lessons: {lessons_with_instructor}\n"
        response += f"• Completed: {completed_lessons}\n"
        response += f"• Success rate: {(completed_lessons/lessons_with_instructor*100) if lessons_with_instructor > 0 else 0:.1f}%\n\n"
        
        if instructor.bio:
            response += f"📝 About: {instructor.bio}\n\n"
        
        response += "Options:\n"
        response += "1️⃣ Book Lesson\n"
        response += "2️⃣ Send Message (via app)\n"
        response += "3️⃣ View Schedule\n"
        if student.can_switch_instructor():
            response += "4️⃣ Switch Instructor\n"
        response += "5️⃣ Main Menu"
        
        return response
    
    def show_student_progress(self, student):
        total_lessons = Lesson.query.filter_by(student_id=student.id, status=LESSON_COMPLETED).count()
        return (
            f"📊 Your Progress:\n\n"
            f"✅ Completed Lessons: {total_lessons}\n"
            f"📈 Keep up the great work!\n\n"
            "Type 'menu' to return to main menu."
        )
    
    def show_student_profile(self, student):
        return (
            f"👤 Your Profile:\n\n"
            f"📛 Name: {student.name}\n"
            f"📧 Email: {student.email}\n"
            f"📱 Phone: {student.phone}\n"
            f"📍 Location: {student.location}\n"
            f"✅ Status: {'Active' if student.is_active else 'Inactive'}\n\n"
            "To update your profile, please use the web portal.\n\n"
            "Type 'menu' to return to main menu."
        )
    
    def show_instructor_students(self, instructor):
        students = Student.query.filter_by(instructor_id=instructor.id, is_active=True).limit(10).all()
        if not students:
            return "👥 You don't have any assigned students yet."
        
        response = f"👥 Your Students ({len(students)}):\n\n"
        for student in students:
            response += f"👤 {student.name}\n"
            response += f"📱 {student.phone}\n"
            recent_lesson = Lesson.query.filter_by(student_id=student.id).order_by(Lesson.lesson_date.desc()).first()
            if recent_lesson:
                response += f"📅 Last lesson: {recent_lesson.lesson_date.strftime('%Y-%m-%d')}\n"
            response += "\n"
        
        return response + "Type 'menu' to return to main menu."
    
    def show_today_lessons(self, instructor):
        today = datetime.now().date()
        lessons = Lesson.query.filter(
            Lesson.instructor_id == instructor.id,
            Lesson.lesson_date >= today,
            Lesson.lesson_date < today + timedelta(days=1)
        ).order_by(Lesson.lesson_date).all()
        
        if not lessons:
            return "📅 No lessons scheduled for today."
        
        response = f"📅 Today's Lessons ({len(lessons)}):\n\n"
        for lesson in lessons:
            response += f"⏰ {lesson.lesson_date.strftime('%H:%M')}\n"
            response += f"👤 {lesson.student.name}\n"
            response += f"⏱️ {lesson.duration} minutes\n"
            response += f"📍 Status: {lesson.status}\n\n"
        
        return response + "Type 'menu' to return to main menu."
    
    def show_instructor_schedule(self, instructor):
        upcoming_lessons = Lesson.query.filter(
            Lesson.instructor_id == instructor.id,
            Lesson.lesson_date >= datetime.now()
        ).filter_by(status=LESSON_SCHEDULED).order_by(Lesson.lesson_date).limit(10).all()
        
        if not upcoming_lessons:
            return "📅 No upcoming lessons scheduled."
        
        response = f"📅 Upcoming Lessons ({len(upcoming_lessons)}):\n\n"
        for lesson in upcoming_lessons:
            response += f"📅 {lesson.lesson_date.strftime('%Y-%m-%d %H:%M')}\n"
            response += f"👤 {lesson.student.name}\n"
            response += f"⏱️ {lesson.duration} minutes\n\n"
        
        return response + "Type 'menu' to return to main menu."
    
    def show_instructor_earnings(self, instructor):
        return (
            f"💰 Your Earnings:\n\n"
            f"💵 Total Earned: ${instructor.total_earnings or 0:.2f}\n"
            f"📊 Commission Paid: ${instructor.commission_paid or 0:.2f}\n"
            f"⭐ Average Rating: {instructor.average_rating or 0:.1f}/5.0\n"
            f"📚 Total Lessons: {instructor.total_lessons_taught or 0}\n\n"
            "Visit the web portal for detailed earnings reports.\n\n"
            "Type 'menu' to return to main menu."
        )
    
    def show_instructor_profile(self, instructor):
        return (
            f"👤 Your Profile:\n\n"
            f"📛 Name: {instructor.get_full_name()}\n"
            f"📧 Email: {instructor.email}\n"
            f"📱 Phone: {instructor.phone}\n"
            f"📍 Location: {instructor.base_location or 'Not set'}\n"
            f"⭐ Experience: {instructor.experience_years or 0} years\n"
            f"✅ Status: {'Active' if instructor.active else 'Inactive'}\n\n"
            "To update your profile, please use the web portal.\n\n"
            "Type 'menu' to return to main menu."
        )
    
    # Admin methods (simplified for now)
    def show_all_students(self, admin):
        count = Student.query.filter_by(is_active=True).count()
        return f"👥 Total Active Students: {count}\n\nUse the web portal for detailed student management."
    
    def show_all_instructors(self, admin):
        count = User.query.filter_by(role=ROLE_INSTRUCTOR, active=True).count()
        return f"👨‍🏫 Total Active Instructors: {count}\n\nUse the web portal for detailed instructor management."
    
    def show_all_lessons(self, admin):
        count = Lesson.query.count()
        return f"📚 Total Lessons: {count}\n\nUse the web portal for detailed lesson management."
    
    def show_pending_approvals(self, admin):
        pending_students = Student.query.filter_by(kyc_status='pending').count()
        return f"⏳ Pending Student Approvals: {pending_students}\n\nUse the web portal to review and approve accounts."
    
    def show_admin_reports(self, admin):
        return "📊 Reports available in the web portal:\n• Student analytics\n• Lesson statistics\n• Financial reports"
    
    # Super Admin methods (simplified for now)
    def show_all_users(self, super_admin):
        user_count = User.query.count()
        student_count = Student.query.count()
        return f"👥 System Users:\n• Staff: {user_count}\n• Students: {student_count}\n\nUse the web portal for user management."
    
    def show_system_stats(self, super_admin):
        return "📊 System Statistics available in the web portal:\n• Performance metrics\n• Usage analytics\n• Error logs"
    
    def show_system_settings(self, super_admin):
        return "⚙️ System Settings available in the web portal:\n• Configuration\n• Feature toggles\n• Integrations"
    
    def show_system_logs(self, super_admin):
        return "📝 System Logs available in the web portal:\n• Application logs\n• Error tracking\n• Audit trails"
    
    def send_whatsapp_message(self, to_phone, message):
        """Send WhatsApp message via Twilio"""
        try:
            if self.twilio_client and self.twilio_phone:
                message_obj = self.twilio_client.messages.create(
                    body=message,
                    from_=self.twilio_phone,
                    to=f"whatsapp:{to_phone}"
                )
                logger.info(f"Message sent to {to_phone}: {message_obj.sid}")
                return True
            else:
                logger.warning(f"Mock send to {to_phone}: {message}")
                return False
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False

    def handle_instructor_switching(self, session, student, message):
        """Handle instructor switching confirmation"""
        session_data = self.get_session_data(session)
        
        if message == '1':  # Yes, find new instructor
            session_data.pop('switching_instructor', None)
            self.update_session_data(session, session_data)
            return self.start_instructor_search(session, student)
        elif message == '2':  # No, keep current instructor
            session_data.pop('switching_instructor', None)
            self.update_session_data(session, session_data)
            return "👍 Keeping your current instructor. Type 'menu' to return to main menu."
        else:
            return "Please select 1 to find a new instructor or 2 to keep your current instructor."

# Global bot instance
enhanced_bot = EnhancedWhatsAppBot()