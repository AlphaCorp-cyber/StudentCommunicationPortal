
#!/usr/bin/env python3

from app import app, db
from models import User, Student
import json

def update_database_schema():
    """Update database schema to support location-based features"""
    with app.app_context():
        print("🔄 Updating database schema...")
        
        # Create tables with new schema
        db.create_all()
        
        # Sample instructor data with locations
        sample_instructors = [
            {
                'username': 'instructor_cbd',
                'email': 'cbd@myinstructor.com',
                'first_name': 'John',
                'last_name': 'Mapfumo',
                'base_location': 'CBD',
                'service_areas': json.dumps(['CBD', 'Avondale', 'Mount Pleasant']),
                'hourly_rate_30min': 25.00,
                'hourly_rate_60min': 45.00,
                'experience_years': 8,
                'bio': 'Experienced driving instructor specializing in city driving and defensive driving techniques.'
            },
            {
                'username': 'instructor_eastlea',
                'email': 'eastlea@myinstructor.com', 
                'first_name': 'Mary',
                'last_name': 'Ncube',
                'base_location': 'Eastlea',
                'service_areas': json.dumps(['Eastlea', 'Borrowdale', 'Glen View']),
                'hourly_rate_30min': 22.00,
                'hourly_rate_60min': 40.00,
                'experience_years': 5,
                'bio': 'Patient and friendly instructor with expertise in parallel parking and highway driving.'
            },
            {
                'username': 'instructor_highfield',
                'email': 'highfield@myinstructor.com',
                'first_name': 'David',
                'last_name': 'Moyo',
                'base_location': 'Highfield',
                'service_areas': json.dumps(['Highfield', 'Waterfalls', 'Mbare', 'Warren Park']),
                'hourly_rate_30min': 20.00,
                'hourly_rate_60min': 35.00,
                'experience_years': 12,
                'bio': 'Veteran instructor with over 10 years experience. Specializes in nervous learners.'
            }
        ]
        
        # Create sample instructors
        for instructor_data in sample_instructors:
            existing = User.query.filter_by(username=instructor_data['username']).first()
            if not existing:
                instructor = User()
                instructor.username = instructor_data['username']
                instructor.email = instructor_data['email']
                instructor.first_name = instructor_data['first_name']
                instructor.last_name = instructor_data['last_name']
                instructor.role = 'instructor'
                instructor.base_location = instructor_data['base_location']
                instructor.service_areas = instructor_data['service_areas']
                instructor.hourly_rate_30min = instructor_data['hourly_rate_30min']
                instructor.hourly_rate_60min = instructor_data['hourly_rate_60min']
                instructor.experience_years = instructor_data['experience_years']
                instructor.bio = instructor_data['bio']
                instructor.set_password('instructor123')
                
                db.session.add(instructor)
                print(f"✅ Created instructor: {instructor.get_full_name()} in {instructor.base_location}")
        
        db.session.commit()
        print("🎉 Database schema updated successfully!")
        print("\n📍 Sample instructors created in different areas of Harare")
        print("🔑 Default password for all instructors: instructor123")

if __name__ == "__main__":
    update_database_schema()
