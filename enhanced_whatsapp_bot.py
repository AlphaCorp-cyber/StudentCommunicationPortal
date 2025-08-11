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
        
        # Enhanced menu options
        if message in ['menu', 'help', 'start']:
            return self.get_student_menu(student)
        elif message in ['1', 'find', 'instructors']:
            return self.start_instructor_search(session, student)
        elif message in ['2', 'book', 'lesson']:
            return self.start_lesson_booking(session, student)
        elif message in ['3', 'lessons']:
            return self.show_student_lessons(student)
        elif message in ['4', 'progress', 'achievements']:
            return self.show_enhanced_student_progress(student)
        elif message in ['5', 'balance', 'rewards']:
            return self.show_balance_and_rewards(student)
        elif message in ['6', 'switch']:
            return self.start_instructor_switch(session, student)
        elif message in ['7', 'safety', 'emergency']:
            return self.show_safety_options(student)
        elif message in ['8', 'help', 'support']:
            return self.show_help_and_support(student)
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
        """Generate the enhanced main menu for students"""
        try:
            from models import StudentProgress, LoyaltyProgram
            from gamification_system import gamification
            
            response = f"🚗 Welcome {student.name}!\n\n"
            
            # Show instructor info
            if student.instructor_id:
                instructor = User.query.get(student.instructor_id)
                response += f"👨‍🏫 Current Instructor: {instructor.get_full_name() if instructor else 'Not assigned'}\n"
                if instructor and instructor.average_rating:
                    response += f"⭐ Rating: {instructor.average_rating:.1f}/5.0\n"
            else:
                response += f"👨‍🏫 No instructor assigned yet\n"
            
            # Show enhanced student stats
            response += f"📚 Lessons completed: {student.lessons_completed or 0}\n"
            response += f"💰 Balance: ${student.balance:.2f}\n"
            
            # Show progress and gamification info
            try:
                progress = StudentProgress.query.filter_by(student_id=student.id).first()
                if progress:
                    response += f"🎯 Test Readiness: {progress.test_readiness_score}%\n"
                    
                    # Show badges
                    badges = json.loads(progress.badges_earned or '[]')
                    if badges:
                        latest_badge = badges[-1] if badges else None
                        if latest_badge and latest_badge in gamification['badges'].BADGES:
                            badge_info = gamification['badges'].BADGES[latest_badge]
                            response += f"🏆 Latest Badge: {badge_info['icon']} {badge_info['name']}\n"
                
                # Show loyalty tier
                loyalty = LoyaltyProgram.query.filter_by(student_id=student.id).first()
                if loyalty and loyalty.current_tier != 'Bronze':
                    response += f"💎 {loyalty.current_tier} Member ({loyalty.total_points} points)\n"
                    
            except Exception as progress_error:
                logger.warning(f"Error getting progress info: {str(progress_error)}")
            
            response += "\n🌟 What would you like to do?\n\n"
            response += "1️⃣ Find Instructors Near Me\n"
            response += "   (AI-powered matching)\n"
            response += "2️⃣ Book a Lesson\n"
            response += "   (Enhanced booking system)\n"
            response += "3️⃣ View My Lessons\n"
            response += "   (Track progress & history)\n"
            response += "4️⃣ My Progress & Achievements\n"
            response += "   (Skills, badges, test readiness)\n"
            response += "5️⃣ Manage Balance & Rewards\n"
            response += "   (Payments, promo codes, loyalty)\n"
            response += "6️⃣ Switch Instructor\n"
            response += "   (Find better matches)\n"
            response += "7️⃣ Safety & Emergency\n"
            response += "   (Emergency contacts, safety tools)\n"
            response += "8️⃣ Help & Support\n"
            response += "   (FAQ, contact support)"
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating enhanced student menu: {str(e)}")
            # Fallback to basic menu
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
        """Start the enhanced lesson booking process"""
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
        
        try:
            from enhanced_features import enhanced_features
            
            # Get dynamic pricing
            pricing_30 = enhanced_features.pricing_engine.calculate_lesson_price(
                student.id, instructor.id, 30, datetime.now() + timedelta(days=1)
            )
            pricing_60 = enhanced_features.pricing_engine.calculate_lesson_price(
                student.id, instructor.id, 60, datetime.now() + timedelta(days=1)
            )
            
            session_data = self.get_session_data(session)
            session_data['booking_lesson'] = True
            session_data['booking_step'] = 'type'
            self.update_session_data(session, session_data)
            
            response = f"📅 Enhanced Booking with {instructor.get_full_name()}\n\n"
            
            # Show lesson types
            response += "🎯 Select lesson type:\n\n"
            response += "1️⃣ Regular Practice Lesson\n"
            response += "2️⃣ Test Preparation Session\n"
            response += "3️⃣ Skill-Specific Training\n"
            response += "4️⃣ Highway Driving Focus\n"
            response += "5️⃣ Cancel booking\n\n"
            
            # Show pricing preview
            price_30 = pricing_30.get('final_price', instructor.hourly_rate_30min or 15) if 'error' not in pricing_30 else instructor.hourly_rate_30min or 15
            price_60 = pricing_60.get('final_price', instructor.hourly_rate_60min or 25) if 'error' not in pricing_60 else instructor.hourly_rate_60min or 25
            
            response += f"💰 Current Pricing:\n"
            response += f"• 30 min: ${price_30:.0f}\n"
            response += f"• 60 min: ${price_60:.0f}\n\n"
            
            # Show surge warning if applicable
            surge_30 = pricing_30.get('surge_multiplier', 1.0) if 'error' not in pricing_30 else 1.0
            if surge_30 > 1.1:
                response += f"⚠️ High demand period ({surge_30:.1f}x pricing)\n"
                response += "Consider booking for later to save money.\n\n"
            
            response += "Choose your lesson type:"
            
            return response
            
        except Exception as e:
            logger.error(f"Error in enhanced booking: {str(e)}")
            # Fallback to basic booking
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
        """Handle the enhanced lesson booking flow"""
        session_data = self.get_session_data(session)
        booking_step = session_data.get('booking_step')
        
        if message in ['5', 'cancel']:
            session_data.pop('booking_lesson', None)
            session_data.pop('booking_step', None)
            session_data.pop('lesson_type', None)
            session_data.pop('lesson_duration', None)
            self.update_session_data(session, session_data)
            return "❌ Booking cancelled. Type 'menu' to return to main menu."
        
        if booking_step == 'type':
            lesson_types = {
                '1': 'regular_practice',
                '2': 'test_preparation', 
                '3': 'skill_specific',
                '4': 'highway_driving'
            }
            
            if message in lesson_types:
                session_data['lesson_type'] = lesson_types[message]
                session_data['booking_step'] = 'duration'
                self.update_session_data(session, session_data)
                return self.show_duration_selection(session, student)
            else:
                return "Please select 1-4 for lesson type or 5 to cancel."
        
        elif booking_step == 'duration':
            if message == '1':
                session_data['lesson_duration'] = 30
                session_data['booking_step'] = 'schedule'
                self.update_session_data(session, session_data)
                return self.show_schedule_options(session, student)
            elif message == '2':
                session_data['lesson_duration'] = 60
                session_data['booking_step'] = 'schedule'
                self.update_session_data(session, session_data)
                return self.show_schedule_options(session, student)
            else:
                return "Please select 1 for 30 minutes, 2 for 60 minutes, or 3 to cancel."
        
        elif booking_step == 'schedule':
            if message == '1':  # Next available
                session_data['scheduling_preference'] = 'next_available'
                session_data['booking_step'] = 'confirm'
                self.update_session_data(session, session_data)
                return self.show_enhanced_booking_confirmation(session, student)
            elif message == '2':  # Specific time
                session_data['scheduling_preference'] = 'specific_time'
                session_data['booking_step'] = 'time_selection'
                self.update_session_data(session, session_data)
                return self.show_time_selection(session, student)
            elif message == '3':  # Recurring
                session_data['scheduling_preference'] = 'recurring'
                session_data['booking_step'] = 'recurring_setup'
                self.update_session_data(session, session_data)
                return self.show_recurring_setup(session, student)
            else:
                return "Please select 1-3 for scheduling or 4 to cancel."
        
        elif booking_step == 'time_selection':
            # Handle specific time selection
            return self.handle_time_selection(session, student, message)
        
        elif booking_step == 'recurring_setup':
            # Handle recurring lesson setup
            return self.handle_recurring_setup(session, student, message)
        
        elif booking_step == 'confirm':
            if message == '1':
                return self.complete_enhanced_lesson_booking(session, student)
            elif message == '2':
                session_data['booking_step'] = 'duration'
                self.update_session_data(session, session_data)
                return self.show_duration_selection(session, student)
            else:
                return "Please select 1 to confirm or 2 to modify booking."
        
        return "Invalid option. Type 'menu' to return to main menu."
    
    def show_enhanced_student_progress(self, student):
        """Show enhanced student progress with gamification"""
        try:
            from models import StudentProgress, LoyaltyProgram
            from gamification_system import gamification
            
            response = f"📊 {student.name}'s Progress Dashboard\n\n"
            
            # Get progress data
            progress = StudentProgress.query.filter_by(student_id=student.id).first()
            if not progress:
                response += "🆕 Welcome! Complete your first lesson to see progress.\n\n"
                response += "Options:\n"
                response += "1️⃣ Book First Lesson\n"
                response += "2️⃣ Find Instructors\n"
                response += "3️⃣ Main Menu"
                return response
            
            # Overall stats
            response += f"🎯 Test Readiness: {progress.test_readiness_score}%\n"
            response += f"📚 Total Lessons: {progress.total_lessons_completed}\n"
            response += f"⏱️ Hours Driven: {progress.total_hours_driven:.1f}\n\n"
            
            # Skills breakdown
            response += "🛣️ Driving Skills:\n"
            skills = [
                ('Parallel Parking', progress.parallel_parking_score),
                ('Highway Driving', progress.highway_driving_score),
                ('City Driving', progress.city_driving_score),
                ('Reverse Parking', progress.reverse_parking_score),
                ('Emergency Braking', progress.emergency_braking_score)
            ]
            
            for skill_name, score in skills:
                stars = "⭐" * (score // 20) + "☆" * (5 - score // 20)
                response += f"  {skill_name}: {stars} ({score}%)\n"
            
            # Badges and achievements
            badges = json.loads(progress.badges_earned or '[]')
            response += f"\n🏆 Badges Earned ({len(badges)}):\n"
            if badges:
                for badge_id in badges[-3:]:  # Show last 3 badges
                    if badge_id in gamification['badges'].BADGES:
                        badge = gamification['badges'].BADGES[badge_id]
                        response += f"  {badge['icon']} {badge['name']}\n"
                if len(badges) > 3:
                    response += f"  ... and {len(badges) - 3} more\n"
            else:
                response += "  No badges yet - keep practicing!\n"
            
            # Next milestones
            milestones = gamification['progress']._get_next_milestones(progress)
            if milestones:
                response += f"\n🎯 Next Goals:\n"
                for milestone in milestones[:2]:
                    progress_bar = "█" * int(milestone['current'] / milestone['target'] * 10)
                    progress_bar += "░" * (10 - len(progress_bar))
                    response += f"  {milestone['description']}\n"
                    response += f"  [{progress_bar}] {milestone['current']}/{milestone['target']}\n"
            
            # Loyalty info
            loyalty = LoyaltyProgram.query.filter_by(student_id=student.id).first()
            if loyalty:
                response += f"\n💎 Loyalty Status:\n"
                response += f"  Tier: {loyalty.current_tier}\n"
                response += f"  Points: {loyalty.total_points}\n"
                response += f"  Available: {loyalty.available_points}\n"
            
            response += f"\nOptions:\n"
            response += f"1️⃣ View All Badges\n"
            response += f"2️⃣ Skills Analysis\n"
            response += f"3️⃣ Set Goals\n"
            response += f"4️⃣ Leaderboard\n"
            response += f"5️⃣ Main Menu"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing enhanced progress: {str(e)}")
            return "Progress data temporarily unavailable. Type 'menu' to return."
    
    def show_balance_and_rewards(self, student):
        """Show balance, payments, and loyalty rewards"""
        try:
            from models import LoyaltyProgram
            
            response = f"💰 Balance & Rewards\n\n"
            response += f"💵 Current Balance: ${student.balance:.2f}\n"
            
            # Loyalty program
            loyalty = LoyaltyProgram.query.filter_by(student_id=student.id).first()
            if loyalty:
                response += f"💎 {loyalty.current_tier} Member\n"
                response += f"⭐ Total Points: {loyalty.total_points}\n"
                response += f"🎁 Available Points: {loyalty.available_points}\n\n"
                
                # Tier benefits
                if loyalty.current_tier == 'Gold':
                    response += "🥇 Gold Benefits:\n• 10% lesson discount\n• Priority booking\n• Bonus points\n\n"
                elif loyalty.current_tier == 'Platinum':
                    response += "🏆 Platinum Benefits:\n• 15% lesson discount\n• VIP support\n• Double points\n• Free lesson monthly\n\n"
            else:
                response += "🆕 Join our loyalty program - earn points with every lesson!\n\n"
            
            # Payment options
            response += "💳 Payment Options:\n"
            response += "1️⃣ Add Funds ($10, $25, $50, $100)\n"
            response += "2️⃣ Auto-Reload Setup\n"
            response += "3️⃣ Redeem Points\n"
            response += "4️⃣ Promo Codes\n"
            response += "5️⃣ Referral Program\n"
            response += "6️⃣ Payment History\n"
            response += "7️⃣ Main Menu"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing balance and rewards: {str(e)}")
            return f"Balance: ${student.balance:.2f}\nType 'menu' to return."
    
    def show_safety_options(self, student):
        """Show safety and emergency options"""
        response = f"🚨 Safety & Emergency Center\n\n"
        response += f"Your safety is our top priority.\n\n"
        
        response += f"🔒 Active Safety Features:\n"
        response += f"• Real-time GPS tracking during lessons\n"
        response += f"• Emergency contact notifications\n"
        response += f"• Instructor background verification\n"
        response += f"• Vehicle safety inspections\n\n"
        
        response += f"🚨 Emergency Options:\n"
        response += f"1️⃣ Emergency Contacts\n"
        response += f"   (Update your emergency contacts)\n"
        response += f"2️⃣ Panic Button Info\n"
        response += f"   (How to use emergency features)\n"
        response += f"3️⃣ Safety Tips\n"
        response += f"   (Stay safe during lessons)\n"
        response += f"4️⃣ Report Safety Issue\n"
        response += f"   (Report any concerns)\n"
        response += f"5️⃣ Safety Training\n"
        response += f"   (Watch safety videos)\n"
        response += f"6️⃣ Main Menu\n\n"
        
        response += f"🆘 EMERGENCY: If you're in immediate danger,\n"
        response += f"call 911 or local emergency services first,\n"
        response += f"then notify DriveLink support."
        
        return response
    
    def show_help_and_support(self, student):
        """Show help and support options"""
        response = f"❓ Help & Support Center\n\n"
        
        response += f"🔍 Quick Help:\n"
        response += f"1️⃣ How to Book Lessons\n"
        response += f"2️⃣ Finding Instructors\n"
        response += f"3️⃣ Payment & Billing\n"
        response += f"4️⃣ Progress Tracking\n"
        response += f"5️⃣ Safety Features\n\n"
        
        response += f"📞 Contact Support:\n"
        response += f"6️⃣ Chat with Agent\n"
        response += f"7️⃣ Report Problem\n"
        response += f"8️⃣ Suggest Feature\n\n"
        
        response += f"📚 Resources:\n"
        response += f"9️⃣ FAQ\n"
        response += f"🔟 Video Tutorials\n"
        response += f"1️⃣1️⃣ Terms & Privacy\n"
        response += f"1️⃣2️⃣ Main Menu\n\n"
        
        response += f"💬 Need immediate help?\n"
        response += f"Text 'agent' to chat with a real person!"
        
        return response
    
    def show_enhanced_booking_confirmation(self, session, student):
        """Show enhanced booking confirmation with all details"""
        try:
            session_data = self.get_session_data(session)
            instructor = User.query.get(student.instructor_id)
            
            lesson_type = session_data.get('lesson_type', 'regular_practice')
            duration = session_data.get('lesson_duration', 60)
            scheduling_pref = session_data.get('scheduling_preference', 'next_available')
            
            # Get dynamic pricing
            from enhanced_features import enhanced_features
            pricing = enhanced_features.pricing_engine.calculate_lesson_price(
                student.id, instructor.id, duration, datetime.now() + timedelta(days=1)
            )
            
            response = f"📋 Booking Confirmation\n\n"
            response += f"👨‍🏫 Instructor: {instructor.get_full_name()}\n"
            response += f"📍 Base Location: {instructor.base_location}\n"
            
            # Lesson type display
            type_names = {
                'regular_practice': 'Regular Practice',
                'test_preparation': 'Test Preparation',
                'skill_specific': 'Skill-Specific Training',
                'highway_driving': 'Highway Driving Focus'
            }
            response += f"🎯 Lesson Type: {type_names.get(lesson_type, 'Regular Practice')}\n"
            response += f"⏱️ Duration: {duration} minutes\n"
            
            # Scheduling info
            if scheduling_pref == 'next_available':
                response += f"📅 Timing: Next available slot\n"
            elif scheduling_pref == 'specific_time':
                selected_date = session_data.get('selected_date', 'TBD')
                response += f"📅 Requested Date: {selected_date}\n"
            elif scheduling_pref == 'recurring':
                pattern = session_data.get('recurring_pattern', 'weekly')
                response += f"🔄 Recurring: {pattern.title()} lessons\n"
            
            # Pricing breakdown
            if 'error' not in pricing:
                final_price = pricing.get('final_price', instructor.hourly_rate_60min or 25)
                surge = pricing.get('surge_multiplier', 1.0)
                discount = pricing.get('discount', 0)
                
                response += f"\n💰 Pricing:\n"
                response += f"   Base Rate: ${pricing.get('base_price', 25):.0f}\n"
                
                if surge > 1.0:
                    response += f"   Demand Surge: {surge:.1f}x\n"
                
                if discount > 0:
                    response += f"   Your Discount: -${discount:.0f}\n"
                
                response += f"   Total Cost: ${final_price:.0f}\n"
                
                # Surge warning
                if surge > 1.2:
                    response += f"\n⚠️ High demand pricing active\n"
                    response += f"💡 Tip: Book for off-peak hours to save money\n"
            else:
                base_rate = instructor.hourly_rate_60min if duration == 60 else instructor.hourly_rate_30min
                response += f"\n💰 Total Cost: ${base_rate or 25}\n"
            
            # Additional features
            response += f"\n✨ Included Features:\n"
            response += f"• Real-time lesson tracking\n"
            response += f"• Progress assessment\n"
            response += f"• Post-lesson summary\n"
            response += f"• Safety monitoring\n"
            
            if lesson_type == 'test_preparation':
                response += f"• Test readiness evaluation\n"
                response += f"• Practice test scenarios\n"
            elif lesson_type == 'skill_specific':
                response += f"• Focused skill development\n"
                response += f"• Progress photos/videos\n"
            
            response += f"\n📱 You'll receive:\n"
            response += f"• Booking confirmation via WhatsApp\n"
            response += f"• Reminder 24 hours before\n"
            response += f"• Instructor contact details\n"
            response += f"• Real-time lesson updates\n"
            
            response += f"\n🔒 Safety Features:\n"
            response += f"• Live GPS tracking\n"
            response += f"• Emergency contact alerts\n"
            response += f"• Panic button access\n"
            response += f"• Instructor verification\n"
            
            response += f"\nConfirm your booking?\n\n"
            response += f"1️⃣ Confirm & Book Lesson\n"
            response += f"2️⃣ Modify Details\n"
            response += f"3️⃣ Cancel Booking"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing enhanced booking confirmation: {str(e)}")
            return self.show_booking_confirmation(session, student)
    
    def complete_enhanced_lesson_booking(self, session, student):
        """Complete the enhanced lesson booking with all features"""
        try:
            from app import db
            from enhanced_features import enhanced_features
            from safety_system import safety_system
            from gamification_system import gamification
            
            session_data = self.get_session_data(session)
            instructor = User.query.get(student.instructor_id)
            
            # Get booking details
            lesson_type = session_data.get('lesson_type', 'regular_practice')
            duration = session_data.get('lesson_duration', 60)
            scheduling_pref = session_data.get('scheduling_preference', 'next_available')
            
            # Calculate pricing
            pricing = enhanced_features.pricing_engine.calculate_lesson_price(
                student.id, instructor.id, duration, datetime.now() + timedelta(days=1)
            )
            
            # Create lesson with enhanced features
            lesson = Lesson()
            lesson.student_id = student.id
            lesson.instructor_id = instructor.id
            lesson.lesson_type = lesson_type
            lesson.duration_minutes = duration
            lesson.status = 'scheduled'
            
            # Set pricing
            if 'error' not in pricing:
                lesson.cost = pricing.get('final_price', 25)
                lesson.base_price = pricing.get('base_price', 25)
                lesson.surge_multiplier = pricing.get('surge_multiplier', 1.0)
                lesson.discount_applied = pricing.get('discount', 0)
            else:
                base_rate = instructor.hourly_rate_60min if duration == 60 else instructor.hourly_rate_30min
                lesson.cost = base_rate or 25
            
            # Set scheduling
            if scheduling_pref == 'next_available':
                lesson.lesson_date = datetime.now() + timedelta(hours=24)  # Next day
            elif scheduling_pref == 'specific_time':
                selected_date = session_data.get('selected_date')
                if selected_date:
                    from datetime import datetime as dt
                    lesson.lesson_date = dt.fromisoformat(selected_date).replace(hour=14)  # 2 PM default
                else:
                    lesson.lesson_date = datetime.now() + timedelta(hours=24)
            elif scheduling_pref == 'recurring':
                lesson.is_recurring = True
                lesson.recurring_pattern = session_data.get('recurring_pattern', 'weekly')
                lesson.lesson_date = datetime.now() + timedelta(days=7)  # Next week
            
            # Set location (mock for demo)
            lesson.location = instructor.base_location or 'To be determined'
            lesson.pickup_location = f"Near {instructor.base_location or 'your location'}"
            
            # Enhanced features
            lesson.lesson_tracking_active = False  # Will be enabled when lesson starts
            lesson.skills_practiced = json.dumps(['basic_driving'])  # Will be updated during lesson
            
            db.session.add(lesson)
            db.session.flush()  # Get lesson ID
            
            # Schedule automatic features
            try:
                # Schedule reminder
                from enhanced_features import CommunicationManager
                CommunicationManager.schedule_reminder(lesson.id, '24_hours')
                
                # Prepare safety tracking
                safety_system['tracker'].start_lesson_tracking(lesson.id)
                
                # Update student progress (booking milestone)
                if student.lessons_completed == 0:
                    gamification['badges'].check_badges_for_student(student.id)
                
            except Exception as feature_error:
                logger.warning(f"Enhanced features setup warning: {str(feature_error)}")
            
            # Update student stats
            student.lessons_completed = (student.lessons_completed or 0) + 1
            
            db.session.commit()
            
            # Clear booking session
            session_data.pop('booking_lesson', None)
            session_data.pop('booking_step', None)
            session_data.pop('lesson_type', None)
            session_data.pop('lesson_duration', None)
            session_data.pop('scheduling_preference', None)
            self.update_session_data(session, session_data)
            
            # Create success message
            response = f"✅ Lesson Booked Successfully!\n\n"
            response += f"📋 Booking Details:\n"
            response += f"• Lesson ID: #{lesson.id}\n"
            response += f"• Instructor: {instructor.get_full_name()}\n"
            response += f"• Date: {lesson.lesson_date.strftime('%Y-%m-%d at %H:%M')}\n"
            response += f"• Duration: {duration} minutes\n"
            response += f"• Cost: ${lesson.cost:.0f}\n"
            response += f"• Type: {lesson_type.replace('_', ' ').title()}\n\n"
            
            if lesson.is_recurring:
                response += f"🔄 Recurring lessons set up ({lesson.recurring_pattern})\n\n"
            
            response += f"📱 What happens next:\n"
            response += f"• Confirmation SMS sent to instructor\n"
            response += f"• Calendar reminder set for 24hrs before\n"
            response += f"• Real-time tracking will start during lesson\n"
            response += f"• Progress will be automatically tracked\n\n"
            
            response += f"🚨 Safety Features Active:\n"
            response += f"• GPS tracking during lesson\n"
            response += f"• Emergency contacts on standby\n"
            response += f"• Panic button available\n"
            response += f"• Instructor verification confirmed\n\n"
            
            response += f"📞 Need to make changes?\n"
            response += f"Reply 'lessons' to view/modify bookings\n"
            response += f"Reply 'menu' to return to main menu\n\n"
            
            response += f"🎉 Enjoy your enhanced driving lesson!"
            
            logger.info(f"Enhanced lesson booking completed: {lesson.id} for student {student.id}")
            return response
            
        except Exception as e:
            logger.error(f"Error completing enhanced lesson booking: {str(e)}")
            db.session.rollback()
            return "❌ Booking failed. Please try again or contact support."
    
    def show_duration_selection(self, session, student):
        """Show enhanced duration selection with pricing"""
        session_data = self.get_session_data(session)
        lesson_type = session_data.get('lesson_type', 'regular_practice')
        instructor = User.query.get(student.instructor_id)
        
        try:
            from enhanced_features import enhanced_features
            
            # Get dynamic pricing
            pricing_30 = enhanced_features.pricing_engine.calculate_lesson_price(
                student.id, instructor.id, 30, datetime.now() + timedelta(days=1)
            )
            pricing_60 = enhanced_features.pricing_engine.calculate_lesson_price(
                student.id, instructor.id, 60, datetime.now() + timedelta(days=1)
            )
            
            response = f"⏱️ Select lesson duration:\n\n"
            
            # Duration recommendations based on lesson type
            if lesson_type == 'test_preparation':
                response += "💡 Recommended: 60 minutes for test prep\n\n"
            elif lesson_type == 'skill_specific':
                response += "💡 Recommended: 30-45 minutes for focused practice\n\n"
            
            # Show options with pricing
            price_30 = pricing_30.get('final_price', instructor.hourly_rate_30min or 15) if 'error' not in pricing_30 else instructor.hourly_rate_30min or 15
            price_60 = pricing_60.get('final_price', instructor.hourly_rate_60min or 25) if 'error' not in pricing_60 else instructor.hourly_rate_60min or 25
            
            response += f"1️⃣ 30 minutes - ${price_30:.0f}\n"
            response += f"2️⃣ 60 minutes - ${price_60:.0f}"
            
            # Show value proposition
            if price_60 < (price_30 * 2):
                savings = (price_30 * 2) - price_60
                response += f" (Save ${savings:.0f}!)"
            
            response += f"\n\n3️⃣ Cancel booking\n\n"
            response += "Choose your duration:"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing duration selection: {str(e)}")
            return f"1️⃣ 30 minutes - ${instructor.hourly_rate_30min or 15}\n2️⃣ 60 minutes - ${instructor.hourly_rate_60min or 25}"
    
    def show_schedule_options(self, session, student):
        """Show scheduling options"""
        response = "📅 When would you like your lesson?\n\n"
        response += "1️⃣ Next Available Slot\n"
        response += "   (Usually within 24-48 hours)\n\n"
        response += "2️⃣ Specific Date & Time\n"
        response += "   (Choose your preferred slot)\n\n"
        response += "3️⃣ Set Up Recurring Lessons\n"
        response += "   (Weekly lessons at same time)\n\n"
        response += "4️⃣ Cancel booking\n\n"
        response += "Choose your preference:"
        
        return response
    
    def show_time_selection(self, session, student):
        """Show specific time selection"""
        from datetime import date, timedelta
        
        response = "🕐 Select your preferred time:\n\n"
        response += "Next 7 days availability:\n\n"
        
        today = date.today()
        for i in range(7):
            check_date = today + timedelta(days=i)
            day_name = check_date.strftime('%A')
            
            response += f"{i+1}️⃣ {day_name} {check_date.strftime('%m/%d')}\n"
        
        response += f"\n8️⃣ Cancel booking\n\n"
        response += "Select a day (1-7):"
        
        return response
    
    def show_recurring_setup(self, session, student):
        """Show recurring lesson setup"""
        response = "🔄 Set up recurring lessons:\n\n"
        response += "1️⃣ Weekly (same day & time)\n"
        response += "2️⃣ Bi-weekly (every 2 weeks)\n" 
        response += "3️⃣ Monthly (once per month)\n\n"
        response += "4️⃣ Cancel booking\n\n"
        response += "Choose frequency:"
        
        return response
    
    def handle_time_selection(self, session, student, message):
        """Handle specific time selection"""
        if message.isdigit() and 1 <= int(message) <= 7:
            from datetime import date, timedelta
            
            selected_day = date.today() + timedelta(days=int(message)-1)
            session_data = self.get_session_data(session)
            session_data['selected_date'] = selected_day.isoformat()
            session_data['booking_step'] = 'confirm'
            self.update_session_data(session, session_data)
            
            return self.show_enhanced_booking_confirmation(session, student)
        elif message == '8':
            return self.handle_lesson_booking_flow(session, student, 'cancel')
        else:
            return "Please select a day (1-7) or 8 to cancel."
    
    def handle_recurring_setup(self, session, student, message):
        """Handle recurring lesson setup"""
        patterns = {'1': 'weekly', '2': 'biweekly', '3': 'monthly'}
        
        if message in patterns:
            session_data = self.get_session_data(session)
            session_data['recurring_pattern'] = patterns[message]
            session_data['is_recurring'] = True
            session_data['booking_step'] = 'confirm'
            self.update_session_data(session, session_data)
            
            return self.show_enhanced_booking_confirmation(session, student)
        elif message == '4':
            return self.handle_lesson_booking_flow(session, student, 'cancel')
        else:
            return "Please select 1-3 for frequency or 4 to cancel."
    
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
        """Start the AI-powered instructor search flow"""
        try:
            from enhanced_features import enhanced_features
            
            # Get smart recommendations using ML algorithm
            recommendations = enhanced_features.get_smart_instructor_recommendations(
                student.id, max_distance=15.0
            )
            
            if not recommendations:
                # Fallback to basic search
                instructors = User.query.filter_by(role=ROLE_INSTRUCTOR, active=True, is_verified=True).limit(10).all()
                if not instructors:
                    return "❌ No verified instructors available at the moment. Please try again later."
                
                # Convert to recommendations format
                recommendations = []
                for instructor in instructors:
                    distance = 0
                    if student.latitude and instructor.latitude:
                        distance = self.calculate_distance(
                            student.latitude, student.longitude,
                            instructor.latitude, instructor.longitude
                        )
                    
                    recommendations.append({
                        'instructor': instructor,
                        'compatibility_score': 0.75,
                        'match_percentage': 75,
                        'distance': distance,
                        'pricing': {'final_price': instructor.hourly_rate_60min or 25},
                        'availability': {'available_today': True},
                        'safety_score': 95
                    })
            
            # Store recommendations in session
            session_data = self.get_session_data(session)
            session_data['selecting_instructor'] = True
            session_data['recommendations'] = [r['instructor'].id for r in recommendations]
            session_data['recommendation_data'] = {r['instructor'].id: r for r in recommendations}
            session_data['current_page'] = 0
            self.update_session_data(session, session_data)
            
            return self.show_smart_instructor_list(recommendations[:5], student, 0, len(recommendations))
            
        except Exception as e:
            logger.error(f"Error in smart instructor search: {str(e)}")
            # Fallback to basic search
            return self.start_basic_instructor_search(session, student)
    
    def start_basic_instructor_search(self, session, student):
        """Fallback basic instructor search"""
        instructors = User.query.filter_by(role=ROLE_INSTRUCTOR, active=True, is_verified=True).limit(10).all()
        
        if not instructors:
            return "❌ No verified instructors available at the moment. Please try again later."
        
        # Calculate distances if student has location
        if student.latitude and student.longitude:
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
    
    def show_smart_instructor_list(self, recommendations, student, page, total):
        """Show AI-powered instructor recommendations"""
        response = f"🤖 Smart Instructor Matches ({len(recommendations)} of {total}):\n\n"
        
        for i, rec in enumerate(recommendations, 1):
            instructor = rec['instructor']
            match_pct = rec.get('match_percentage', 75)
            distance = rec.get('distance', 0)
            pricing = rec.get('pricing', {})
            availability = rec.get('availability', {})
            safety_score = rec.get('safety_score', 95)
            
            # Match indicator
            if match_pct >= 90:
                match_indicator = "🔥 PERFECT MATCH"
            elif match_pct >= 80:
                match_indicator = "⭐ GREAT MATCH"
            elif match_pct >= 70:
                match_indicator = "✅ GOOD MATCH"
            else:
                match_indicator = "👍 SUITABLE"
            
            response += f"{i}️⃣ {instructor.get_full_name()}\n"
            response += f"   {match_indicator} ({match_pct}%)\n"
            response += f"📍 {instructor.base_location or 'Location not set'}"
            if distance > 0:
                response += f" ({distance:.1f}km away)\n"
            else:
                response += "\n"
            
            response += f"⭐ {instructor.experience_years or 0} years • Rating: {instructor.average_rating or 'New'}/5.0\n"
            
            # Dynamic pricing
            final_price = pricing.get('final_price', instructor.hourly_rate_60min or 25)
            surge_multiplier = pricing.get('surge_multiplier', 1.0)
            if surge_multiplier > 1.1:
                response += f"💰 ${final_price:.0f}/hour (High demand)\n"
            else:
                response += f"💰 ${final_price:.0f}/hour\n"
            
            # Availability
            if availability.get('available_today'):
                response += f"🟢 Available today\n"
            else:
                response += f"🟡 Next available: Tomorrow\n"
            
            # Safety score
            if safety_score >= 95:
                response += f"🛡️ Excellent safety record\n\n"
            elif safety_score >= 90:
                response += f"🛡️ Very safe driver\n\n"
            else:
                response += f"🛡️ Safety score: {safety_score}/100\n\n"
        
        response += "Reply with:\n"
        response += "• Number (1-5) to view details\n"
        if page > 0:
            response += "• 'prev' for previous matches\n"
        if (page + 1) * 5 < total:
            response += "• 'next' for more matches\n"
        response += "• 'menu' to return to main menu"
        
        return response
    
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
        
        # Check if using smart recommendations or basic list
        recommendations = session_data.get('recommendations', [])
        instructor_list = session_data.get('instructor_list', [])
        current_page = session_data.get('current_page', 0)
        
        if message == 'menu':
            session_data.pop('selecting_instructor', None)
            session_data.pop('instructor_list', None)
            session_data.pop('recommendations', None)
            session_data.pop('recommendation_data', None)
            self.update_session_data(session, session_data)
            return self.get_student_menu(student)
        
        elif message == 'next':
            next_page = current_page + 1
            start_idx = next_page * 5
            
            if recommendations:
                # Smart recommendations flow
                if start_idx < len(recommendations):
                    session_data['current_page'] = next_page
                    self.update_session_data(session, session_data)
                    
                    # Get recommendation data
                    rec_data = session_data.get('recommendation_data', {})
                    page_recommendations = []
                    for instructor_id in recommendations[start_idx:start_idx+5]:
                        if instructor_id in rec_data:
                            page_recommendations.append(rec_data[instructor_id])
                    
                    return self.show_smart_instructor_list(page_recommendations, student, next_page, len(recommendations))
                else:
                    return "No more matches to show. Type 'menu' to return."
            else:
                # Basic list flow
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
                
                if recommendations:
                    # Smart recommendations flow
                    rec_data = session_data.get('recommendation_data', {})
                    page_recommendations = []
                    for instructor_id in recommendations[start_idx:start_idx+5]:
                        if instructor_id in rec_data:
                            page_recommendations.append(rec_data[instructor_id])
                    
                    return self.show_smart_instructor_list(page_recommendations, student, prev_page, len(recommendations))
                else:
                    # Basic list flow
                    instructors = User.query.filter(User.id.in_(instructor_list[start_idx:start_idx+5])).all()
                    return self.show_instructor_list(instructors, student, prev_page, len(instructor_list))
            else:
                return "Already on first page. Type 'menu' to return."
        
        elif message.isdigit():
            choice = int(message)
            start_idx = current_page * 5
            
            # Determine which list to use
            active_list = recommendations if recommendations else instructor_list
            
            if 1 <= choice <= 5 and start_idx + choice - 1 < len(active_list):
                instructor_id = active_list[start_idx + choice - 1]
                instructor = User.query.get(instructor_id)
                return self.show_enhanced_instructor_details(session, student, instructor)
            else:
                return "Invalid selection. Please choose a number from the list or type 'menu'."
        
        else:
            return "Please choose a number (1-5), 'next', 'prev', or 'menu'."
    
    def show_enhanced_instructor_details(self, session, student, instructor):
        """Show enhanced instructor details with all new features"""
        try:
            from enhanced_features import enhanced_features
            
            # Get recommendation data if available
            session_data = self.get_session_data(session)
            rec_data = session_data.get('recommendation_data', {})
            instructor_rec = rec_data.get(instructor.id, {})
            
            # Calculate distance
            distance_text = ""
            distance = 0
            if student.latitude and instructor.latitude:
                distance = self.calculate_distance(
                    student.latitude, student.longitude,
                    instructor.latitude, instructor.longitude
                )
                distance_text = f"\n📏 Distance: {distance:.1f}km from you"
            
            # Get dynamic pricing
            try:
                pricing = enhanced_features.pricing_engine.calculate_lesson_price(
                    student.id, instructor.id, 60, datetime.now() + timedelta(days=1)
                )
            except:
                pricing = {'final_price': instructor.hourly_rate_60min or 25, 'surge_multiplier': 1.0}
            
            # Match score if available
            match_info = ""
            if 'match_percentage' in instructor_rec:
                match_pct = instructor_rec['match_percentage']
                if match_pct >= 90:
                    match_info = f"🔥 PERFECT MATCH ({match_pct}%)\n"
                elif match_pct >= 80:
                    match_info = f"⭐ GREAT MATCH ({match_pct}%)\n"
                elif match_pct >= 70:
                    match_info = f"✅ GOOD MATCH ({match_pct}%)\n"
                else:
                    match_info = f"👍 SUITABLE ({match_pct}%)\n"
            
            response = f"👨‍🏫 {instructor.get_full_name()}\n"
            response += match_info
            response += f"📍 Base Location: {instructor.base_location or 'Not specified'}{distance_text}\n"
            response += f"⭐ Experience: {instructor.experience_years or 0} years\n"
            
            # Enhanced pricing display
            final_price = pricing.get('final_price', instructor.hourly_rate_60min or 25)
            surge_multiplier = pricing.get('surge_multiplier', 1.0)
            if surge_multiplier > 1.1:
                response += f"💰 ${final_price:.0f}/hour (High demand - {surge_multiplier:.1f}x)\n"
            else:
                response += f"💰 ${final_price:.0f}/hour\n"
            
            # Rating with more detail
            response += f"⭐ Rating: {instructor.average_rating or 'New'}/5.0 ({instructor.total_lessons_taught or 0} lessons taught)\n"
            
            # Safety score
            safety_score = instructor_rec.get('safety_score', 95)
            if safety_score >= 95:
                response += f"🛡️ Excellent safety record (95+)\n"
            elif safety_score >= 90:
                response += f"🛡️ Very safe driver ({safety_score}/100)\n"
            else:
                response += f"🛡️ Safety score: {safety_score}/100\n"
            
            # Real-time availability
            availability = instructor_rec.get('availability', {})
            if availability.get('available_today'):
                response += f"🟢 Available today\n"
            else:
                response += f"🟡 Next available: Tomorrow\n"
            
            # Bio
            if instructor.bio:
                response += f"\n📝 About: {instructor.bio[:120]}{'...' if len(instructor.bio) > 120 else ''}\n"
            
            # Specializations (mock data for demo)
            specializations = ["Parallel parking", "Highway driving", "Test preparation"]
            response += f"\n🎯 Specializations: {', '.join(specializations[:2])}\n"
            
            # Store instructor for selection
            session_data['selected_instructor_id'] = instructor.id
            self.update_session_data(session, session_data)
            
            response += "\nWhat would you like to do?\n"
            response += "1️⃣ Select This Instructor\n"
            response += "2️⃣ View Reviews & Ratings\n"
            response += "3️⃣ Check Schedule & Availability\n"
            response += "4️⃣ Get Pricing Breakdown\n"
            response += "5️⃣ Back to List\n"
            response += "6️⃣ Main Menu"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing enhanced instructor details: {str(e)}")
            # Fallback to basic details
            return self.show_instructor_details(session, student, instructor)
    
    def show_instructor_details(self, session, student, instructor):
        """Fallback basic instructor details"""
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
        """Handle actions from enhanced instructor detail view"""
        session_data = self.get_session_data(session)
        instructor_id = session_data.get('selected_instructor_id')
        
        if not instructor_id:
            return "Session expired. Please search for instructors again."
        
        instructor = User.query.get(instructor_id)
        if not instructor:
            return "Instructor not found. Please search again."
        
        if message == '1':  # Select instructor
            return self.assign_instructor_to_student(session, student, instructor)
        elif message == '2':  # View reviews and ratings
            return self.show_enhanced_instructor_reviews(instructor)
        elif message == '3':  # Check schedule and availability
            return self.show_enhanced_instructor_schedule(instructor)
        elif message == '4':  # Get pricing breakdown
            return self.show_pricing_breakdown(session, student, instructor)
        elif message == '5':  # Back to list
            return self.start_instructor_search(session, student)
        elif message == '6' or message == 'menu':  # Main menu
            session_data.pop('selecting_instructor', None)
            session_data.pop('selected_instructor_id', None)
            self.update_session_data(session, session_data)
            return self.get_student_menu(student)
        else:
            return "Please select 1-6 or type 'menu'."
    
    def show_enhanced_instructor_reviews(self, instructor):
        """Show enhanced reviews with detailed breakdown"""
        try:
            from models import Review
            
            reviews = Review.query.filter_by(instructor_id=instructor.id).order_by(
                Review.created_at.desc()
            ).limit(5).all()
            
            response = f"⭐ Reviews for {instructor.get_full_name()}\n\n"
            
            if not reviews:
                response += "🆕 New instructor - no reviews yet!\n"
                response += "Be the first to book and leave a review.\n\n"
                response += f"💡 Based on verification:\n"
                response += f"✅ Licensed instructor\n"
                response += f"✅ Background checked\n"
                response += f"✅ Vehicle inspected\n\n"
            else:
                # Overall stats
                avg_patience = sum(r.patience_rating for r in reviews if r.patience_rating) / len([r for r in reviews if r.patience_rating])
                avg_teaching = sum(r.teaching_style_rating for r in reviews if r.teaching_style_rating) / len([r for r in reviews if r.teaching_style_rating])
                avg_punctuality = sum(r.punctuality_rating for r in reviews if r.punctuality_rating) / len([r for r in reviews if r.punctuality_rating])
                
                response += f"📊 Rating Breakdown:\n"
                response += f"⭐ Overall: {instructor.average_rating:.1f}/5.0\n"
                response += f"😌 Patience: {avg_patience:.1f}/5.0\n"
                response += f"🎓 Teaching: {avg_teaching:.1f}/5.0\n"
                response += f"⏰ Punctuality: {avg_punctuality:.1f}/5.0\n\n"
                
                response += f"📚 Recent Reviews:\n"
                for review in reviews[:3]:
                    response += f"⭐ {review.overall_rating}/5 - {review.created_at.strftime('%b %Y')}\n"
                    if review.review_text:
                        text = review.review_text[:80] + "..." if len(review.review_text) > 80 else review.review_text
                        response += f"   \"{text}\"\n"
                    response += "\n"
            
            response += "Options:\n"
            response += "1️⃣ Select This Instructor\n"
            response += "2️⃣ Back to Details\n"
            response += "3️⃣ Main Menu"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing enhanced reviews: {str(e)}")
            return self.show_instructor_reviews(instructor)
    
    def show_enhanced_instructor_schedule(self, instructor):
        """Show enhanced schedule with real-time availability"""
        try:
            from datetime import date, timedelta
            from models import InstructorAvailability, Lesson
            
            response = f"📅 Schedule for {instructor.get_full_name()}\n\n"
            
            # Next 7 days availability
            today = date.today()
            response += "🗓️ Next 7 Days:\n"
            
            for i in range(7):
                check_date = today + timedelta(days=i)
                day_name = check_date.strftime('%A')[:3]
                
                # Check existing lessons
                existing_lessons = Lesson.query.filter(
                    Lesson.instructor_id == instructor.id,
                    Lesson.lesson_date >= datetime.combine(check_date, time.min),
                    Lesson.lesson_date < datetime.combine(check_date + timedelta(days=1), time.min),
                    Lesson.status.in_(['scheduled', 'confirmed'])
                ).count()
                
                # Mock availability (in real app, would check InstructorAvailability)
                if check_date.weekday() < 5:  # Weekday
                    available_slots = 8 - existing_lessons
                else:  # Weekend
                    available_slots = 4 - existing_lessons
                
                if available_slots > 0:
                    response += f"{day_name} {check_date.strftime('%m/%d')}: 🟢 {available_slots} slots\n"
                else:
                    response += f"{day_name} {check_date.strftime('%m/%d')}: 🔴 Fully booked\n"
            
            response += "\n⏰ Typical Hours:\n"
            response += "• Weekdays: 8:00 AM - 6:00 PM\n"
            response += "• Weekends: 9:00 AM - 4:00 PM\n"
            response += "• Flexible timing available\n\n"
            
            # Popular time slots
            response += "🎯 Popular Times:\n"
            response += "• Morning (8-10 AM): Less traffic\n"
            response += "• Afternoon (2-4 PM): Good practice\n"
            response += "• Evening (5-7 PM): High demand\n\n"
            
            response += "Options:\n"
            response += "1️⃣ Select This Instructor\n"
            response += "2️⃣ Request Specific Time\n"
            response += "3️⃣ Back to Details\n"
            response += "4️⃣ Main Menu"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing enhanced schedule: {str(e)}")
            return self.show_instructor_availability(instructor)
    
    def show_pricing_breakdown(self, session, student, instructor):
        """Show detailed pricing breakdown with dynamic factors"""
        try:
            from enhanced_features import enhanced_features
            
            response = f"💰 Pricing for {instructor.get_full_name()}\n\n"
            
            # Get pricing for different scenarios
            pricing_30 = enhanced_features.pricing_engine.calculate_lesson_price(
                student.id, instructor.id, 30, datetime.now() + timedelta(days=1)
            )
            pricing_60 = enhanced_features.pricing_engine.calculate_lesson_price(
                student.id, instructor.id, 60, datetime.now() + timedelta(days=1)
            )
            
            # 30-minute lesson
            response += "⏱️ 30-Minute Lesson:\n"
            if 'error' not in pricing_30:
                response += f"   Base Price: ${pricing_30.get('base_price', 15):.0f}\n"
                if pricing_30.get('surge_multiplier', 1.0) > 1.0:
                    response += f"   Demand Surge: {pricing_30.get('surge_multiplier', 1.0):.1f}x\n"
                if pricing_30.get('discount', 0) > 0:
                    response += f"   Your Discount: -${pricing_30.get('discount', 0):.0f}\n"
                response += f"   Final Price: ${pricing_30.get('final_price', 15):.0f}\n\n"
            else:
                response += f"   ${instructor.hourly_rate_30min or 15}/lesson\n\n"
            
            # 60-minute lesson
            response += "⏱️ 60-Minute Lesson:\n"
            if 'error' not in pricing_60:
                response += f"   Base Price: ${pricing_60.get('base_price', 25):.0f}\n"
                if pricing_60.get('surge_multiplier', 1.0) > 1.0:
                    response += f"   Demand Surge: {pricing_60.get('surge_multiplier', 1.0):.1f}x\n"
                if pricing_60.get('discount', 0) > 0:
                    response += f"   Your Discount: -${pricing_60.get('discount', 0):.0f}\n"
                response += f"   Final Price: ${pricing_60.get('final_price', 25):.0f}\n\n"
            else:
                response += f"   ${instructor.hourly_rate_60min or 25}/lesson\n\n"
            
            # Pricing factors
            response += "📊 Pricing Factors:\n"
            current_hour = datetime.now().hour
            if 7 <= current_hour <= 9 or 17 <= current_hour <= 19:
                response += "⬆️ Peak hours (7-9 AM, 5-7 PM)\n"
            
            if datetime.now().weekday() >= 5:
                response += "⬆️ Weekend premium\n"
            
            # Your benefits
            response += "\n🎁 Your Benefits:\n"
            if student.lessons_completed == 0:
                response += "✨ 15% first-time student discount\n"
            
            # Check loyalty program
            try:
                from models import LoyaltyProgram
                loyalty = LoyaltyProgram.query.filter_by(student_id=student.id).first()
                if loyalty:
                    if loyalty.current_tier == 'Gold':
                        response += "🥇 Gold member: 10% discount\n"
                    elif loyalty.current_tier == 'Platinum':
                        response += "🏆 Platinum member: 15% discount\n"
            except:
                pass
            
            response += "\n💡 Save Money Tips:\n"
            response += "• Book off-peak hours\n"
            response += "• Consider longer lessons (better value)\n"
            response += "• Refer friends for bonus credits\n\n"
            
            response += "Options:\n"
            response += "1️⃣ Select This Instructor\n"
            response += "2️⃣ View Promo Codes\n"
            response += "3️⃣ Back to Details\n"
            response += "4️⃣ Main Menu"
            
            return response
            
        except Exception as e:
            logger.error(f"Error showing pricing breakdown: {str(e)}")
            return f"💰 Standard Rates:\n30 min: ${instructor.hourly_rate_30min or 15}\n60 min: ${instructor.hourly_rate_60min or 25}"
    
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