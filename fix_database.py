
import os
from sqlalchemy import create_engine, text
from app import app, db
from models import User, Student, Lesson, WhatsAppSession, SystemConfig

def fix_database_types():
    """Fix database type mismatches"""
    with app.app_context():
        try:
            # Drop and recreate tables to ensure proper types
            db.drop_all()
            db.create_all()
            
            # Create default users for testing
            create_demo_users()
            
            print("Database fixed successfully!")
            
        except Exception as e:
            print(f"Error fixing database: {e}")

def create_demo_users():
    """Create demo users for testing"""
    try:
        # Create Super Admin
        super_admin = User(
            username='superadmin',
            email='superadmin@myinstructor.com',
            first_name='Super',
            last_name='Admin',
            role='super_admin'
        )
        super_admin.set_password('admin123')
        
        # Create Admin
        admin = User(
            username='admin',
            email='admin@myinstructor.com',
            first_name='John',
            last_name='Admin',
            role='admin'
        )
        admin.set_password('admin123')
        
        # Create Instructor
        instructor = User(
            username='instructor',
            email='instructor@myinstructor.com',
            first_name='Jane',
            last_name='Instructor',
            role='instructor'
        )
        instructor.set_password('instructor123')
        
        db.session.add_all([super_admin, admin, instructor])
        db.session.commit()
        
        # Create demo student
        student = Student(
            name='Demo Student',
            phone='+263777123456',
            email='student@example.com',
            instructor_id=instructor.id,
            license_type='Class 4'
        )
        
        db.session.add(student)
        db.session.commit()
        
        print("Demo users created:")
        print("Super Admin - username: superadmin, password: admin123")
        print("Admin - username: admin, password: admin123")
        print("Instructor - username: instructor, password: instructor123")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating demo users: {e}")

if __name__ == "__main__":
    fix_database_types()
