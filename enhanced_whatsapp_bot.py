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
        
        if message in ['menu', 'help', 'start']:
            return self.get_student_menu(student)
        elif message in ['1', 'lessons']:
            return self.show_student_lessons(student)
        elif message in ['2', 'book']:
            return self.start_lesson_booking(session, student)
        elif message in ['3', 'instructors']:
            return self.show_available_instructors(student)
        elif message in ['4', 'progress']:
            return self.show_student_progress(student)
        elif message in ['5', 'profile']:
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
        return (
            f"🎓 Welcome {student.name}!\n\n"
            "What would you like to do?\n\n"
            "1️⃣ View My Lessons\n"
            "2️⃣ Book New Lesson\n"
            "3️⃣ Find Instructors\n"
            "4️⃣ My Progress\n"
            "5️⃣ My Profile\n\n"
            "Reply with a number (1-5) or type the option name."
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
        return (
            "📅 Let's book a new lesson!\n\n"
            "To book a lesson, please use the web portal for now:\n"
            "Visit your student dashboard to:\n"
            "• Choose your instructor\n"
            "• Select date and time\n"
            "• Confirm booking\n\n"
            "Type 'menu' to return to main menu."
        )
    
    def show_available_instructors(self, student):
        instructors = User.query.filter_by(role=ROLE_INSTRUCTOR, active=True).limit(5).all()
        if not instructors:
            return "❌ No instructors available at the moment."
        
        response = "👨‍🏫 Available Instructors:\n\n"
        for instructor in instructors:
            response += f"👤 {instructor.get_full_name()}\n"
            if instructor.base_location:
                response += f"📍 {instructor.base_location}\n"
            if instructor.experience_years:
                response += f"⭐ {instructor.experience_years} years experience\n"
            response += "\n"
        
        return response + "Visit the web portal to view full profiles and book lessons."
    
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

# Global bot instance
enhanced_bot = EnhancedWhatsAppBot()