
#!/usr/bin/env python3

import os
import sys
import json

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def update_database_schema():
    """Update database schema to support location-based features"""
    # Import after setting up the path
    from app import app, db
    from models import User, Student
    
    with app.app_context():
        print("🔄 Updating database schema...")
        
        # First, let's add the missing columns to the users table
        try:
            with db.engine.connect() as conn:
                # Check if columns exist and add them if they don't
                columns_to_add = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS service_areas TEXT",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS base_location VARCHAR(100)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS latitude FLOAT",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS longitude FLOAT",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS hourly_rate_30min NUMERIC(10,2)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS hourly_rate_60min NUMERIC(10,2)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS experience_years INTEGER"
                ]
                
                for sql in columns_to_add:
                    try:
                        conn.execute(db.text(sql))
                        conn.commit()
                        print(f"✅ Added column from: {sql.split('ADD COLUMN IF NOT EXISTS')[1].split()[0]}")
                    except Exception as e:
                        print(f"⚠️ Column might already exist: {e}")
                        
                # Add missing columns to students table
                student_columns = [
                    "ALTER TABLE students ADD COLUMN IF NOT EXISTS current_location VARCHAR(100)",
                    "ALTER TABLE students ADD COLUMN IF NOT EXISTS latitude FLOAT",
                    "ALTER TABLE students ADD COLUMN IF NOT EXISTS longitude FLOAT", 
                    "ALTER TABLE students ADD COLUMN IF NOT EXISTS preferred_radius_km INTEGER DEFAULT 10",
                    "ALTER TABLE students ADD COLUMN IF NOT EXISTS account_balance NUMERIC(10,2) DEFAULT 0.00"
                ]
                
                for sql in student_columns:
                    try:
                        conn.execute(db.text(sql))
                        conn.commit()
                        print(f"✅ Added student column: {sql.split('ADD COLUMN IF NOT EXISTS')[1].split()[0]}")
                    except Exception as e:
                        print(f"⚠️ Student column might already exist: {e}")
                        
        except Exception as e:
            print(f"❌ Error updating table structure: {str(e)}")
            return
        
        # Now create any missing tables
        db.create_all()
        print("✅ Created missing tables")
        
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
            else:
                print(f"⚠️ Instructor {instructor_data['username']} already exists, skipping...")
        
        try:
            db.session.commit()
            print("🎉 Database schema updated successfully!")
            print("\n📍 Sample instructors created in different areas of Harare")
            print("🔑 Default password for all instructors: instructor123")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error updating database: {str(e)}")

if __name__ == "__main__":
    update_database_schema()
