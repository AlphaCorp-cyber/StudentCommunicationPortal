#!/usr/bin/env python3
"""
Script to create demo users with properly hashed passwords
"""
from app import app, db
from models import User, ROLE_INSTRUCTOR, ROLE_ADMIN, ROLE_SUPER_ADMIN

def create_demo_users():
    with app.app_context():
        # Clear existing users
        User.query.delete()
        
        # Create demo users
        users = [
            {
                'username': 'instructor',
                'email': 'instructor@myinstructor.com',
                'password': 'password123',
                'first_name': 'John',
                'last_name': 'Instructor',
                'role': ROLE_INSTRUCTOR
            },
            {
                'username': 'admin',
                'email': 'admin@myinstructor.com',
                'password': 'password123',
                'first_name': 'Jane',
                'last_name': 'Admin',
                'role': ROLE_ADMIN
            },
            {
                'username': 'superadmin',
                'email': 'superadmin@myinstructor.com',
                'password': 'password123',
                'first_name': 'Super',
                'last_name': 'Admin',
                'role': ROLE_SUPER_ADMIN
            }
        ]
        
        for user_data in users:
            user = User(
                username=user_data['username'],
                email=user_data['email'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                role=user_data['role']
            )
            user.set_password(user_data['password'])
            db.session.add(user)
        
        db.session.commit()
        print("Demo users created successfully!")
        
        # Verify users
        for user in User.query.all():
            print(f"Created: {user.username} ({user.role}) - {user.email}")

if __name__ == '__main__':
    create_demo_users()