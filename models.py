from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# User roles
ROLE_INSTRUCTOR = 'instructor'
ROLE_ADMIN = 'admin'
ROLE_SUPER_ADMIN = 'super_admin'

# Lesson statuses
LESSON_SCHEDULED = 'scheduled'
LESSON_COMPLETED = 'completed'
LESSON_CANCELLED = 'cancelled'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    profile_image_url = db.Column(db.String, nullable=True)
    role = db.Column(db.String(20), default=ROLE_INSTRUCTOR)
    active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    instructor_students = db.relationship('Student', backref='instructor', lazy=True)
    instructor_lessons = db.relationship('Lesson', backref='instructor', lazy=True)

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

    def is_instructor(self):
        return self.role == ROLE_INSTRUCTOR

    def is_admin(self):
        return self.role == ROLE_ADMIN

    def is_super_admin(self):
        return self.role == ROLE_SUPER_ADMIN

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
    license_type = db.Column(db.String(10), default='B')
    
    # Foreign key to instructor
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Status tracking
    registration_date = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    total_lessons_required = db.Column(db.Integer, default=20)
    lessons_completed = db.Column(db.Integer, default=0)
    
    # Relationships
    lessons = db.relationship('Lesson', backref='student', lazy=True, cascade='all, delete-orphan')
    whatsapp_sessions = db.relationship('WhatsAppSession', backref='student', lazy=True)

    def get_progress_percentage(self):
        if self.total_lessons_required == 0:
            return 0
        return min(100, (self.lessons_completed / self.total_lessons_required) * 100)

class Lesson(db.Model):
    __tablename__ = 'lessons'
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Lesson details
    scheduled_date = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    lesson_type = db.Column(db.String(50), default='practical')  # practical, theory, test
    location = db.Column(db.String(200), nullable=True)
    
    # Status and tracking
    status = db.Column(db.String(20), default=LESSON_SCHEDULED)
    completed_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Integer, nullable=True)  # 1-5 scale
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def mark_completed(self, notes=None, feedback=None, rating=None):
        self.status = LESSON_COMPLETED
        self.completed_date = datetime.now()
        self.notes = notes
        self.feedback = feedback
        self.rating = rating
        
        # Update student's completed lessons count
        if self.student:
            self.student.lessons_completed += 1

class WhatsAppSession(db.Model):
    __tablename__ = 'whatsapp_sessions'
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    # Session details
    session_id = db.Column(db.String(100), unique=True, nullable=False)
    last_message = db.Column(db.Text, nullable=True)
    last_activity = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)

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
            config = SystemConfig(key=key, value=value, description=description)
            db.session.add(config)
        db.session.commit()
