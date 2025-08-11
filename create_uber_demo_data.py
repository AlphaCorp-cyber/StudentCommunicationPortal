#!/usr/bin/env python3
"""
Create demo data for the Uber-style WhatsApp bot system
This creates students, instructors, and shows the instructor selection flow
"""

import os
import sys
from datetime import datetime, timedelta

# Add the current directory to the path so we can import our modules
sys.path.append('.')

from app import app, db
from models import User, Student, Lesson

def create_demo_data():
    """Create demo data for testing the Uber-style instructor selection"""
    
    with app.app_context():
        print("🚗 Creating Uber-style demo data...")
        
        # Create verified instructors with different locations and ratings
        instructors_data = [
            {
                'name': 'John Smith',
                'phone': '+263719123456',
                'email': 'john.smith@drivelink.com',
                'base_location': 'Harare CBD',
                'latitude': -17.8292,
                'longitude': 31.0522,
                'experience_years': 8,
                'hourly_rate_30min': 20,
                'hourly_rate_60min': 35,
                'average_rating': 4.8,
                'total_lessons_taught': 156,
                'bio': 'Patient and experienced instructor specializing in defensive driving techniques.',
                'is_verified': True,
                'active': True
            },
            {
                'name': 'Sarah Johnson',
                'phone': '+263719234567',
                'email': 'sarah.johnson@drivelink.com',
                'base_location': 'Avondale',
                'latitude': -17.8089,
                'longitude': 31.0409,
                'experience_years': 5,
                'hourly_rate_30min': 18,
                'hourly_rate_60min': 30,
                'average_rating': 4.9,
                'total_lessons_taught': 89,
                'bio': 'Friendly instructor with expertise in parallel parking and city driving.',
                'is_verified': True,
                'active': True
            },
            {
                'name': 'Michael Brown',
                'phone': '+263719345678',
                'email': 'michael.brown@drivelink.com',
                'base_location': 'Belvedere',
                'latitude': -17.8344,
                'longitude': 31.0669,
                'experience_years': 12,
                'hourly_rate_30min': 25,
                'hourly_rate_60min': 40,
                'average_rating': 4.7,
                'total_lessons_taught': 234,
                'bio': 'Veteran instructor with specialization in highway driving and test preparation.',
                'is_verified': True,
                'active': True
            },
            {
                'name': 'Lisa Williams',
                'phone': '+263719456789',
                'email': 'lisa.williams@drivelink.com',
                'base_location': 'Mount Pleasant',
                'latitude': -17.7969,
                'longitude': 31.0769,
                'experience_years': 3,
                'hourly_rate_30min': 15,
                'hourly_rate_60min': 25,
                'average_rating': 4.6,
                'total_lessons_taught': 45,
                'bio': 'Young and energetic instructor perfect for nervous beginners.',
                'is_verified': True,
                'active': True
            },
            {
                'name': 'David Wilson',
                'phone': '+263719567890',
                'email': 'david.wilson@drivelink.com',
                'base_location': 'Borrowdale',
                'latitude': -17.7519,
                'longitude': 31.1169,
                'experience_years': 10,
                'hourly_rate_30min': 22,
                'hourly_rate_60min': 38,
                'average_rating': 4.5,
                'total_lessons_taught': 178,
                'bio': 'Professional instructor specializing in luxury vehicles and advanced techniques.',
                'is_verified': True,
                'active': True
            }
        ]
        
        # Create instructor users
        instructor_users = []
        for instructor_data in instructors_data:
            # Check if instructor already exists
            existing = User.query.filter_by(phone=instructor_data['phone']).first()
            if existing:
                print(f"📞 Instructor {instructor_data['name']} already exists")
                instructor_users.append(existing)
                continue
            
            instructor = User()
            instructor.username = instructor_data['email']  # Use email as username
            instructor.password_hash = 'demo_hash_not_for_login'  # Demo password hash
            instructor.name = instructor_data['name']
            instructor.first_name = instructor_data['name'].split()[0]
            instructor.last_name = instructor_data['name'].split()[-1]
            instructor.phone = instructor_data['phone']
            instructor.email = instructor_data['email']
            instructor.role = 'instructor'
            instructor.base_location = instructor_data['base_location']
            instructor.latitude = instructor_data['latitude']
            instructor.longitude = instructor_data['longitude']
            instructor.experience_years = instructor_data['experience_years']
            instructor.hourly_rate_30min = instructor_data['hourly_rate_30min']
            instructor.hourly_rate_60min = instructor_data['hourly_rate_60min']
            instructor.average_rating = instructor_data['average_rating']
            instructor.total_lessons_taught = instructor_data['total_lessons_taught']
            instructor.bio = instructor_data['bio']
            instructor.is_verified = instructor_data['is_verified']
            instructor.active = instructor_data['active']
            instructor.subscription_plan = 'premium'  # All demo instructors have premium
            instructor.account_balance = 500.0  # Demo balance
            
            db.session.add(instructor)
            instructor_users.append(instructor)
            print(f"👨‍🏫 Created instructor: {instructor.name} in {instructor.base_location}")
        
        # Create test students with different locations
        students_data = [
            {
                'name': 'Emma Davis',
                'phone': '+263719092710',  # This is the test number from the requirement
                'email': 'emma.davis@student.com',
                'current_location': 'Harare CBD',
                'latitude': -17.8292,
                'longitude': 31.0522,
                'account_balance': 100.0
            },
            {
                'name': 'James Anderson',
                'phone': '+263719876543',
                'email': 'james.anderson@student.com',
                'current_location': 'Avondale',
                'latitude': -17.8089,
                'longitude': 31.0409,
                'account_balance': 150.0
            },
            {
                'name': 'Sophia Miller',
                'phone': '+263719765432',
                'email': 'sophia.miller@student.com',
                'current_location': 'Mount Pleasant',
                'latitude': -17.7969,
                'longitude': 31.0769,
                'account_balance': 200.0
            }
        ]
        
        # Create student users and corresponding student records
        for student_data in students_data:
            # Check if student already exists
            existing_user = User.query.filter_by(phone=student_data['phone']).first()
            existing_student = Student.query.filter_by(phone=student_data['phone']).first()
            
            if existing_user or existing_student:
                print(f"📱 Student {student_data['name']} already exists")
                continue
            
            # Create User record
            student_user = User()
            student_user.username = student_data['email']  # Use email as username
            student_user.password_hash = 'demo_hash_not_for_login'  # Demo password hash
            student_user.name = student_data['name']
            student_user.first_name = student_data['name'].split()[0]
            student_user.last_name = student_data['name'].split()[-1]
            student_user.phone = student_data['phone']
            student_user.email = student_data['email']
            student_user.role = 'student'
            student_user.account_balance = student_data['account_balance']
            student_user.active = True
            
            db.session.add(student_user)
            db.session.flush()  # Get the ID
            
            # Create Student record
            student = Student()
            student.name = student_data['name']
            student.phone = student_data['phone']
            student.email = student_data['email']
            student.current_location = student_data['current_location']
            student.latitude = student_data['latitude']
            student.longitude = student_data['longitude']
            student.account_balance = student_data['account_balance']
            student.is_active = True
            student.kyc_status = 'verified'  # Pre-verified for demo
            student.date_joined = datetime.now() - timedelta(days=10)  # Registered 10 days ago
            
            db.session.add(student)
            print(f"🎓 Created student: {student.name} in {student.current_location}")
        
        # Create some sample lessons to show history
        db.session.commit()
        
        # Get the created students and instructors
        emma = Student.query.filter_by(phone='+263719092710').first()
        john_instructor = User.query.filter_by(phone='+263719123456').first()
        
        if emma and john_instructor:
            # Create a completed lesson for Emma with John using correct field names
            lesson = Lesson()
            lesson.student_id = emma.id
            lesson.instructor_id = john_instructor.id
            lesson.lesson_date = datetime.now() - timedelta(days=3)  # Using lesson_date field
            lesson.duration_minutes = 60
            lesson.cost = 35.0
            lesson.status = 'completed'
            lesson.location = 'Harare CBD'
            lesson.notes = 'First lesson completed successfully'
            
            db.session.add(lesson)
            print(f"📚 Created sample lesson: Emma with John (completed)")
        
        db.session.commit()
        print("\n✅ Demo data created successfully!")
        print("\n🚗 Uber-style Features Ready:")
        print("📱 Test with WhatsApp number: +263719092710")
        print("👨‍🏫 5 verified instructors available")
        print("🎓 3 test students created")
        print("📍 Location-based instructor search enabled")
        print("⭐ Rating and review system ready")
        print("💰 Pricing comparison available")
        print("🔄 Instructor switching system active")
        
        print("\n📋 WhatsApp Bot Test Commands:")
        print("• Send 'hi' or 'menu' to start")
        print("• Option 1: Find Instructors Near Me")
        print("• Option 6: Switch Instructor (if assigned)")
        print("• Full Uber-like instructor browsing experience")

if __name__ == '__main__':
    create_demo_data()