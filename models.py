from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# User roles
ROLE_STUDENT = 'student'
ROLE_INSTRUCTOR = 'instructor'
ROLE_ADMIN = 'admin'
ROLE_SUPER_ADMIN = 'super_admin'

# Lesson statuses
LESSON_SCHEDULED = 'scheduled'
LESSON_COMPLETED = 'completed'
LESSON_CANCELLED = 'cancelled'

# Subscription plans
SUBSCRIPTION_BASIC = 'basic'
SUBSCRIPTION_PREMIUM = 'premium'
SUBSCRIPTION_PRO = 'pro'

# Subscription statuses
SUBSCRIPTION_ACTIVE = 'active'
SUBSCRIPTION_CANCELLED = 'cancelled'
SUBSCRIPTION_EXPIRED = 'expired'
SUBSCRIPTION_SUSPENDED = 'suspended'

# Payment statuses
PAYMENT_PENDING = 'pending'
PAYMENT_COMPLETED = 'completed'
PAYMENT_FAILED = 'failed'
PAYMENT_REFUNDED = 'refunded'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    profile_image_url = db.Column(db.String, nullable=True)
    phone = db.Column(db.String(20), nullable=True)  # WhatsApp number for instructors
    role = db.Column(db.String(20), default=ROLE_INSTRUCTOR)
    active = db.Column(db.Boolean, default=True)
    
    # Instructor location fields
    service_areas = db.Column(db.Text, nullable=True)  # JSON string of areas they serve
    base_location = db.Column(db.String(100), nullable=True)  # Main operating area
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    hourly_rate_30min = db.Column(db.Numeric(10, 2), nullable=True)
    hourly_rate_60min = db.Column(db.Numeric(10, 2), nullable=True)
    bio = db.Column(db.Text, nullable=True)  # Instructor bio/description
    experience_years = db.Column(db.Integer, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Subscription fields
    subscription_status = db.Column(db.String(20), default=SUBSCRIPTION_ACTIVE)
    subscription_plan = db.Column(db.String(20), default=SUBSCRIPTION_BASIC)
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    subscription_auto_renew = db.Column(db.Boolean, default=True)
    
    # Instructor verification and onboarding
    is_verified = db.Column(db.Boolean, default=False)
    license_number = db.Column(db.String(100), nullable=True)
    license_class = db.Column(db.String(20), nullable=True)
    license_expiry = db.Column(db.Date, nullable=True)
    certification_documents = db.Column(db.Text, nullable=True)  # JSON array of document URLs
    vehicle_owned = db.Column(db.Boolean, default=False)
    
    # KYC fields (for both instructors and students)
    id_number = db.Column(db.String(20), nullable=True)  # National ID
    physical_address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(50), nullable=True)
    emergency_contact = db.Column(db.String(20), nullable=True)
    emergency_contact_name = db.Column(db.String(100), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    kyc_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    kyc_submitted_at = db.Column(db.DateTime, nullable=True)
    kyc_approved_at = db.Column(db.DateTime, nullable=True)
    
    # Instructor-specific KYC fields
    years_experience = db.Column(db.Integer, nullable=True)
    
    # Student-specific KYC fields
    provisional_license = db.Column(db.String(100), nullable=True)
    license_type_wanted = db.Column(db.String(20), nullable=True)
    medical_fitness_declared = db.Column(db.Boolean, default=False)
    vision_check_declared = db.Column(db.Boolean, default=False)
    
    # Document upload fields
    national_id_document = db.Column(db.String(255), nullable=True)  # File path
    provisional_license_document = db.Column(db.String(255), nullable=True)  # File path for students
    driving_license_document = db.Column(db.String(255), nullable=True)  # File path for instructors
    instructor_certificate_document = db.Column(db.String(255), nullable=True)  # Teaching certificate
    proof_of_residence_document = db.Column(db.String(255), nullable=True)  # File path
    profile_photo = db.Column(db.String(255), nullable=True)  # File path
    
    # Performance metrics
    total_earnings = db.Column(db.Numeric(10, 2), default=0.00)
    commission_paid = db.Column(db.Numeric(10, 2), default=0.00)
    average_rating = db.Column(db.Float, default=0.0)
    total_lessons_taught = db.Column(db.Integer, default=0)
    
    # Relationships
    instructor_students = db.relationship('Student', backref='instructor', lazy=True)
    instructor_lessons = db.relationship('Lesson', backref='instructor', lazy=True)
    subscriptions = db.relationship('InstructorSubscription', backref='instructor', lazy=True)
    commission_records = db.relationship('CommissionRecord', backref='instructor', lazy=True)
    reviews = db.relationship('InstructorReview', backref='instructor', lazy=True)

    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)

    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username

    def is_student(self):
        return self.role == ROLE_STUDENT

    def is_instructor(self):
        return self.role == ROLE_INSTRUCTOR

    def is_admin(self):
        return self.role == ROLE_ADMIN

    def is_super_admin(self):
        return self.role == ROLE_SUPER_ADMIN
    
    def has_active_subscription(self):
        """Check if instructor has an active subscription"""
        if not self.is_instructor():
            return True  # Non-instructors don't need subscriptions
        return self.subscription_status == SUBSCRIPTION_ACTIVE and self.subscription_end_date and self.subscription_end_date > datetime.now()
    
    def can_take_students(self):
        """Check if instructor can take new students based on subscription plan"""
        if not self.has_active_subscription():
            return False
        
        current_students = Student.query.filter_by(instructor_id=self.id).count()
        limits = {
            SUBSCRIPTION_BASIC: 10,
            SUBSCRIPTION_PREMIUM: 25,
            SUBSCRIPTION_PRO: float('inf')
        }
        return current_students < limits.get(self.subscription_plan, 0)
    
    def get_commission_rate(self):
        """Get commission rate based on subscription plan"""
        rates = {
            SUBSCRIPTION_BASIC: 0.15,  # 15%
            SUBSCRIPTION_PREMIUM: 0.12,  # 12%
            SUBSCRIPTION_PRO: 0.08  # 8%
        }
        return rates.get(self.subscription_plan, 0.15)
    
    def get_subscription_price(self):
        """Get monthly subscription price"""
        prices = {
            SUBSCRIPTION_BASIC: 29.00,
            SUBSCRIPTION_PREMIUM: 49.00,
            SUBSCRIPTION_PRO: 99.00
        }
        return prices.get(self.subscription_plan, 29.00)
    
    def update_rating(self):
        """Update average rating based on reviews"""
        reviews = InstructorReview.query.filter_by(instructor_id=self.id).all()
        if reviews:
            total_rating = sum(review.rating for review in reviews)
            self.average_rating = total_rating / len(reviews)
        else:
            self.average_rating = 0.0

    def __repr__(self):
        return f'<User {self.username}>'

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    license_type = db.Column(db.String(10), default='Class 4')
    
    # Location fields
    current_location = db.Column(db.String(100), nullable=True)  # e.g., "Avondale", "CBD", "Eastlea"
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    preferred_radius_km = db.Column(db.Integer, default=10)  # How far willing to travel
    
    # Foreign key to instructor (now optional - will be assigned after selection)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Status tracking
    registration_date = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    total_lessons_required = db.Column(db.Integer, default=20)
    lessons_completed = db.Column(db.Integer, default=0)
    
    # Financial tracking
    account_balance = db.Column(db.Numeric(10, 2), default=0.00)
    
    # Authentication
    pin_hash = db.Column(db.String(256), nullable=True)  # For PIN-based login
    
    # Relationships
    lessons = db.relationship('Lesson', backref='student', lazy=True, cascade='all, delete-orphan')
    whatsapp_sessions = db.relationship('WhatsAppSession', backref='student', lazy=True)

    def get_progress_percentage(self):
        if self.total_lessons_required == 0:
            return 0
        return min(100, (self.lessons_completed / self.total_lessons_required) * 100)
    
    def get_lesson_price(self, duration_minutes):
        """Get the price for a lesson based on duration and license class"""
        pricing = LessonPricing.query.filter_by(license_class=self.license_type).first()
        if not pricing:
            return 0
        
        if duration_minutes <= 30:
            return float(pricing.price_per_30min)
        else:
            return float(pricing.price_per_60min)
    
    def has_sufficient_balance(self, duration_minutes):
        """Check if student has enough balance for the lesson"""
        lesson_price = self.get_lesson_price(duration_minutes)
        return float(self.account_balance) >= lesson_price

    def can_switch_instructor(self):
        """Check if student can switch instructor (after 5 lessons or 1 week)"""
        # Check if student has completed at least 5 lessons
        completed_lessons = 0
        for lesson in Lesson.query.filter_by(student_id=self.id).all():
            if lesson.status == LESSON_COMPLETED:
                completed_lessons += 1
        
        if completed_lessons >= 5:
            return True
        
        # Check if it's been at least 1 week since registration
        if self.registration_date:
            days_since_registration = (datetime.now() - self.registration_date).days
            if days_since_registration >= 7:
                return True
        
        return False

    def set_pin(self, pin):
        """Set PIN hash for authentication"""
        from werkzeug.security import generate_password_hash
        self.pin_hash = generate_password_hash(str(pin))

    def check_pin(self, pin):
        """Check if provided PIN matches hash"""
        from werkzeug.security import check_password_hash
        if not self.pin_hash:
            return False
        return check_password_hash(self.pin_hash, str(pin))

class Lesson(db.Model):
    __tablename__ = 'lessons'
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=True)
    
    # Lesson details
    lesson_date = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    lesson_type = db.Column(db.String(50), default='practical')  # practical, theory, test
    location = db.Column(db.String(200), nullable=True)
    pickup_location = db.Column(db.String(200), nullable=True)
    pickup_latitude = db.Column(db.Float, nullable=True)
    pickup_longitude = db.Column(db.Float, nullable=True)
    
    # Financial tracking
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    base_price = db.Column(db.Numeric(10, 2), nullable=True)
    surge_multiplier = db.Column(db.Float, default=1.0)
    discount_applied = db.Column(db.Numeric(10, 2), default=0.00)
    promo_code = db.Column(db.String(20), nullable=True)
    
    # Status and tracking
    status = db.Column(db.String(20), default=LESSON_SCHEDULED)
    completed_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Integer, nullable=True)  # 1-5 scale
    
    # Enhanced features
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_pattern = db.Column(db.String(20), nullable=True)  # weekly, biweekly, monthly
    parent_lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=True)
    emergency_contact_notified = db.Column(db.Boolean, default=False)
    lesson_tracking_active = db.Column(db.Boolean, default=False)
    
    # Progress tracking
    skills_practiced = db.Column(db.Text, nullable=True)  # JSON list of skills
    progress_photos = db.Column(db.Text, nullable=True)  # JSON list of photo URLs
    instructor_assessment = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    recurring_lessons = db.relationship('Lesson', backref=db.backref('parent_lesson', remote_side=[id]), lazy=True)

    def mark_completed(self, notes=None, feedback=None, rating=None):
        from app import db
        self.status = LESSON_COMPLETED
        self.completed_date = datetime.now()
        self.notes = notes
        self.feedback = feedback
        self.rating = rating
        
        # Get the student object explicitly
        student = Student.query.get(self.student_id)
        if student and self.cost:
            # Deduct lesson cost from student's balance
            student.account_balance = float(student.account_balance) - float(self.cost)
            # Update student's completed lessons count
            student.lessons_completed += 1
            db.session.commit()

class WhatsAppSession(db.Model):
    __tablename__ = 'whatsapp_sessions'
    id = db.Column(db.Integer, primary_key=True)
    
    # Support for all user types
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # For instructors/admins
    phone_number = db.Column(db.String(20), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)  # student, instructor, admin, super_admin, unknown
    
    # Session details
    session_id = db.Column(db.String(100), unique=True, nullable=False)
    session_data = db.Column(db.Text, nullable=True)  # JSON data for registration/booking flows
    last_message = db.Column(db.Text, nullable=True)
    last_activity = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)

class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    id = db.Column(db.Integer, primary_key=True)
    registration_number = db.Column(db.String(20), unique=True, nullable=False)
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    license_class = db.Column(db.String(10), nullable=False)  # Class 4, Class 2, etc.
    
    # Assignment
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    lessons = db.relationship('Lesson', backref='vehicle', lazy=True)
    instructor = db.relationship('User', backref='assigned_vehicles', lazy=True)

class LessonPricing(db.Model):
    __tablename__ = 'lesson_pricing'
    id = db.Column(db.Integer, primary_key=True)
    license_class = db.Column(db.String(10), nullable=False)  # Class 4, Class 2, etc.
    price_per_30min = db.Column(db.Numeric(10, 2), nullable=False)
    price_per_60min = db.Column(db.Numeric(10, 2), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_type = db.Column(db.String(20), nullable=False)  # 'cash', 'online'
    payment_method = db.Column(db.String(50), nullable=True)  # 'visa', 'mastercard', 'ecocash', etc.
    reference_number = db.Column(db.String(100), nullable=True)
    
    # Admin who processed the payment
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    student = db.relationship('Student', backref='payments')
    admin = db.relationship('User', backref='processed_payments')

class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @staticmethod
    def get_config(key, default=None):
        config = SystemConfig.query.filter_by(key=key).first()
        return config.value if config else default

    @staticmethod
    def set_config(key, value, description=None):
        config = SystemConfig.query.filter_by(key=key).first()
        if config:
            config.value = value
            config.description = description
            config.updated_at = datetime.now()
        else:
            config = SystemConfig()
            config.key = key
            config.value = value
            config.description = description
            db.session.add(config)
        db.session.commit()

class InstructorSubscription(db.Model):
    """Tracks instructor subscription history and payments"""
    __tablename__ = 'instructor_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan = db.Column(db.String(20), nullable=False)  # basic, premium, pro
    status = db.Column(db.String(20), default=SUBSCRIPTION_ACTIVE)
    
    # Billing period
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    
    # Payment details
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_status = db.Column(db.String(20), default=PAYMENT_PENDING)
    payment_method = db.Column(db.String(50), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)
    stripe_invoice_id = db.Column(db.String(255), nullable=True)
    
    # Auto-renewal
    auto_renew = db.Column(db.Boolean, default=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

class CommissionRecord(db.Model):
    """Tracks commission taken from each lesson"""
    __tablename__ = 'commission_records'
    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=False)
    
    # Financial details
    lesson_amount = db.Column(db.Numeric(10, 2), nullable=False)
    commission_rate = db.Column(db.Float, nullable=False)  # Percentage as decimal (0.15 = 15%)
    commission_amount = db.Column(db.Numeric(10, 2), nullable=False)
    instructor_earning = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Payment status
    paid_to_instructor = db.Column(db.Boolean, default=False)
    payment_date = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    lesson = db.relationship('Lesson', backref='commission_record')

class InstructorReview(db.Model):
    """Student reviews and ratings for instructors"""
    __tablename__ = 'instructor_reviews'
    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=True)
    
    # Review content
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    comment = db.Column(db.Text, nullable=True)
    
    # Categories for detailed feedback
    punctuality_rating = db.Column(db.Integer, nullable=True)
    teaching_quality_rating = db.Column(db.Integer, nullable=True)
    communication_rating = db.Column(db.Integer, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    student = db.relationship('Student', backref='instructor_reviews')
    lesson = db.relationship('Lesson', backref='review')

class SubscriptionPlan(db.Model):
    """Configuration for subscription plans"""
    __tablename__ = 'subscription_plans'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)  # basic, premium, pro
    
    # Pricing
    monthly_price = db.Column(db.Numeric(10, 2), nullable=False)
    yearly_price = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Limits and features
    student_limit = db.Column(db.Integer, nullable=True)  # NULL = unlimited
    commission_rate = db.Column(db.Float, nullable=False)  # Percentage as decimal
    priority_support = db.Column(db.Boolean, default=False)
    analytics_access = db.Column(db.Boolean, default=False)
    custom_branding = db.Column(db.Boolean, default=False)
    
    # Plan configuration
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text, nullable=True)
    features = db.Column(db.Text, nullable=True)  # JSON array of feature descriptions
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

class InstructorPayout(db.Model):
    """Tracks payouts to instructors"""
    __tablename__ = 'instructor_payouts'
    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Payout details
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    period_start = db.Column(db.DateTime, nullable=False)
    period_end = db.Column(db.DateTime, nullable=False)
    
    # Payment information
    payment_method = db.Column(db.String(50), nullable=False)  # bank_transfer, paypal, etc.
    payment_reference = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default=PAYMENT_PENDING)
    
    # Bank details (if applicable)
    bank_name = db.Column(db.String(100), nullable=True)
    account_number = db.Column(db.String(50), nullable=True)
    account_name = db.Column(db.String(100), nullable=True)
    
    # Processing details
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    processor = db.relationship('User', foreign_keys=[processed_by], backref='processed_payouts')

class MarketplaceBooking(db.Model):
    """Direct bookings from marketplace without pre-assigned instructor"""
    __tablename__ = 'marketplace_bookings'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    # Booking preferences
    preferred_location = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    max_distance_km = db.Column(db.Integer, default=10)
    
    # Lesson details
    lesson_type = db.Column(db.String(20), nullable=False)  # Class 4, Class 2, etc.
    duration_minutes = db.Column(db.Integer, nullable=False)
    preferred_date = db.Column(db.Date, nullable=False)
    preferred_time = db.Column(db.Time, nullable=False)
    max_price = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Status
    status = db.Column(db.String(20), default='open')  # open, matched, cancelled, expired
    assigned_instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=True)
    
    # Special requirements
    automatic_transmission = db.Column(db.Boolean, default=False)
    pickup_required = db.Column(db.Boolean, default=False)
    special_notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    # Relationships
    student = db.relationship('Student', backref='marketplace_bookings')
    assigned_instructor = db.relationship('User', backref='marketplace_assignments')
    lesson = db.relationship('Lesson', backref='marketplace_booking')

# Add methods to User model for enhanced functionality
def can_switch_instructor_method(self):
    """Check if student can switch instructors based on business rules"""
    if self.role != 'student':
        return False
    
    # Allow switching if no instructor assigned
    if not hasattr(self, 'instructor_id') or not self.instructor_id:
        return True
    
    # Allow switching after 5 completed lessons with current instructor
    from datetime import datetime, timedelta
    
    try:
        completed_lessons = Lesson.query.filter_by(
            student_id=self.id,
            instructor_id=self.instructor_id,
            status='completed'
        ).count()
        
        if completed_lessons >= 5:
            return True
        
        # Allow switching after 1 week of registration
        one_week_ago = datetime.now() - timedelta(days=7)
        if hasattr(self, 'date_joined') and self.date_joined and self.date_joined <= one_week_ago:
            return True
    except:
        # If there's any error, allow switching to prevent blocking users
        return True
    
    return False

# Attach method to User class
User.can_switch_instructor = can_switch_instructor_method

# Enhanced Review and Rating System
class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Overall rating
    overall_rating = db.Column(db.Integer, nullable=False)  # 1-5 scale
    
    # Detailed ratings
    patience_rating = db.Column(db.Integer, nullable=True)
    teaching_style_rating = db.Column(db.Integer, nullable=True)
    punctuality_rating = db.Column(db.Integer, nullable=True)
    vehicle_condition_rating = db.Column(db.Integer, nullable=True)
    communication_rating = db.Column(db.Integer, nullable=True)
    
    # Text feedback
    review_text = db.Column(db.Text, nullable=True)
    instructor_response = db.Column(db.Text, nullable=True)
    instructor_response_date = db.Column(db.DateTime, nullable=True)
    
    # Progress documentation
    progress_photos = db.Column(db.Text, nullable=True)  # JSON list of photo URLs
    skills_learned = db.Column(db.Text, nullable=True)  # JSON list
    
    # Verification
    is_verified = db.Column(db.Boolean, default=False)
    helpful_votes = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    lesson = db.relationship('Lesson', backref='reviews')
    student = db.relationship('Student', foreign_keys=[student_id], backref='given_reviews')
    instructor = db.relationship('User', foreign_keys=[instructor_id], backref='received_reviews')

# Dynamic Pricing System
class PricingRule(db.Model):
    __tablename__ = 'pricing_rules'
    id = db.Column(db.Integer, primary_key=True)
    
    rule_name = db.Column(db.String(100), nullable=False)
    rule_type = db.Column(db.String(20), nullable=False)  # surge, discount, base
    
    # Conditions
    day_of_week = db.Column(db.String(20), nullable=True)  # monday, tuesday, etc.
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    min_distance_km = db.Column(db.Float, nullable=True)
    max_distance_km = db.Column(db.Float, nullable=True)
    location_area = db.Column(db.String(100), nullable=True)
    
    # Pricing modifiers
    multiplier = db.Column(db.Float, default=1.0)
    fixed_amount = db.Column(db.Numeric(10, 2), default=0.00)
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

# Promo Codes and Discounts
class PromoCode(db.Model):
    __tablename__ = 'promo_codes'
    id = db.Column(db.Integer, primary_key=True)
    
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    
    # Discount details
    discount_type = db.Column(db.String(20), nullable=False)  # percentage, fixed_amount
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    max_discount = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Usage limits
    max_uses = db.Column(db.Integer, nullable=True)
    current_uses = db.Column(db.Integer, default=0)
    max_uses_per_user = db.Column(db.Integer, default=1)
    
    # Validity
    valid_from = db.Column(db.DateTime, nullable=False)
    valid_until = db.Column(db.DateTime, nullable=False)
    
    # Conditions
    min_lesson_cost = db.Column(db.Numeric(10, 2), nullable=True)
    applicable_lesson_types = db.Column(db.String(200), nullable=True)  # JSON
    first_time_users_only = db.Column(db.Boolean, default=False)
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

# Real-time Location Tracking
class LocationTracker(db.Model):
    __tablename__ = 'location_tracker'
    id = db.Column(db.Integer, primary_key=True)
    
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    # Current location
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float, nullable=True)
    
    # Tracking status
    tracking_status = db.Column(db.String(20), default='active')  # active, paused, ended
    speed = db.Column(db.Float, nullable=True)  # km/h
    heading = db.Column(db.Float, nullable=True)  # degrees
    
    # Safety features
    emergency_triggered = db.Column(db.Boolean, default=False)
    panic_button_pressed = db.Column(db.Boolean, default=False)
    emergency_contacts_notified = db.Column(db.Boolean, default=False)
    
    timestamp = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    lesson = db.relationship('Lesson', backref='location_tracking')
    instructor = db.relationship('User', foreign_keys=[instructor_id])
    student = db.relationship('Student', foreign_keys=[student_id])

# Progress Tracking and Gamification
class StudentProgress(db.Model):
    __tablename__ = 'student_progress'
    id = db.Column(db.Integer, primary_key=True)
    
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    # Skill assessments
    parallel_parking_score = db.Column(db.Integer, default=0)  # 0-100
    highway_driving_score = db.Column(db.Integer, default=0)
    city_driving_score = db.Column(db.Integer, default=0)
    reverse_parking_score = db.Column(db.Integer, default=0)
    emergency_braking_score = db.Column(db.Integer, default=0)
    
    # Overall progress
    total_lessons_completed = db.Column(db.Integer, default=0)
    total_hours_driven = db.Column(db.Float, default=0.0)
    test_readiness_score = db.Column(db.Integer, default=0)  # 0-100
    
    # Achievements and badges
    badges_earned = db.Column(db.Text, nullable=True)  # JSON list
    milestones_reached = db.Column(db.Text, nullable=True)  # JSON list
    
    # Test preparation
    theory_test_score = db.Column(db.Integer, nullable=True)
    practical_test_scheduled = db.Column(db.Date, nullable=True)
    test_center_preference = db.Column(db.String(100), nullable=True)
    
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    student = db.relationship('Student', backref='progress_tracking')

# Safety and Verification
class SafetyIncident(db.Model):
    __tablename__ = 'safety_incidents'
    id = db.Column(db.Integer, primary_key=True)
    
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    incident_type = db.Column(db.String(50), nullable=False)  # emergency, accident, panic_button
    description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='low')  # low, medium, high, critical
    
    # Location
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    address = db.Column(db.String(300), nullable=True)
    
    # Response
    emergency_services_called = db.Column(db.Boolean, default=False)
    emergency_contacts_notified = db.Column(db.Boolean, default=False)
    resolved = db.Column(db.Boolean, default=False)
    resolution_notes = db.Column(db.Text, nullable=True)
    
    reported_at = db.Column(db.DateTime, default=datetime.now)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    lesson = db.relationship('Lesson', backref='safety_incidents')
    instructor = db.relationship('User', foreign_keys=[instructor_id])
    student = db.relationship('Student', foreign_keys=[student_id])

# Advanced Communication System
class CommunicationLog(db.Model):
    __tablename__ = 'communication_logs'
    id = db.Column(db.Integer, primary_key=True)
    
    sender_type = db.Column(db.String(20), nullable=False)  # student, instructor, system
    sender_id = db.Column(db.Integer, nullable=True)
    recipient_type = db.Column(db.String(20), nullable=False)
    recipient_id = db.Column(db.Integer, nullable=True)
    
    message_type = db.Column(db.String(30), nullable=False)  # text, voice, lesson_recap, reminder
    message_content = db.Column(db.Text, nullable=False)
    media_url = db.Column(db.String(500), nullable=True)  # for voice messages or photos
    
    # Context
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=True)
    related_booking_id = db.Column(db.Integer, nullable=True)
    
    # Status
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)
    delivery_status = db.Column(db.String(20), default='sent')  # sent, delivered, failed
    
    sent_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    lesson = db.relationship('Lesson', backref='communications')

# Instructor Availability Management
class InstructorAvailability(db.Model):
    __tablename__ = 'instructor_availability'
    id = db.Column(db.Integer, primary_key=True)
    
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Time slots
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    
    # Availability status
    is_available = db.Column(db.Boolean, default=True)
    max_lessons_per_slot = db.Column(db.Integer, default=1)
    
    # Special dates
    specific_date = db.Column(db.Date, nullable=True)  # For one-off availability changes
    is_recurring = db.Column(db.Boolean, default=True)
    
    # Pricing overrides
    custom_rate_30min = db.Column(db.Numeric(10, 2), nullable=True)
    custom_rate_60min = db.Column(db.Numeric(10, 2), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    instructor = db.relationship('User', backref='availability_slots')

# Loyalty Program
class LoyaltyProgram(db.Model):
    __tablename__ = 'loyalty_program'
    id = db.Column(db.Integer, primary_key=True)
    
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    # Points system
    total_points = db.Column(db.Integer, default=0)
    points_used = db.Column(db.Integer, default=0)
    available_points = db.Column(db.Integer, default=0)
    
    # Tier system
    current_tier = db.Column(db.String(20), default='Bronze')  # Bronze, Silver, Gold, Platinum
    tier_benefits = db.Column(db.Text, nullable=True)  # JSON
    
    # Referral system
    referral_code = db.Column(db.String(20), unique=True, nullable=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    referrals_made = db.Column(db.Integer, default=0)
    
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    student = db.relationship('Student', foreign_keys=[student_id], backref='loyalty_profile')
    referrer = db.relationship('Student', foreign_keys=[referred_by], backref='referred_students')

# Smart Matching Algorithm Data
class MatchingPreferences(db.Model):
    __tablename__ = 'matching_preferences'
    id = db.Column(db.Integer, primary_key=True)
    
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    # Instructor preferences
    preferred_gender = db.Column(db.String(10), nullable=True)  # male, female, no_preference
    preferred_age_range = db.Column(db.String(20), nullable=True)  # 25-35, 35-45, etc.
    preferred_experience_years = db.Column(db.Integer, nullable=True)
    max_distance_km = db.Column(db.Float, default=10.0)
    
    # Learning preferences
    learning_style = db.Column(db.String(30), nullable=True)  # patient, strict, encouraging
    lesson_pace = db.Column(db.String(20), nullable=True)  # slow, normal, fast
    special_requirements = db.Column(db.Text, nullable=True)  # JSON
    
    # Scheduling preferences
    preferred_days = db.Column(db.String(50), nullable=True)  # JSON array
    preferred_times = db.Column(db.String(50), nullable=True)  # JSON array
    flexible_scheduling = db.Column(db.Boolean, default=True)
    
    # Communication preferences
    communication_style = db.Column(db.String(20), default='whatsapp')
    reminder_frequency = db.Column(db.String(20), default='24_hours')
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    student = db.relationship('Student', backref='matching_preferences')
