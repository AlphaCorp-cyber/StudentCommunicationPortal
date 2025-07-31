#!/usr/bin/env python3
"""
Add phone numbers to existing instructors for WhatsApp integration
"""

from app import app, db
from models import User

def add_instructor_phone_numbers():
    """Add phone numbers to existing instructors"""
    with app.app_context():
        # Sample instructor phone numbers for testing
        instructor_phones = {
            'instructor_cbd': '+263719092710',      # John Mapfumo - CBD area
            'instructor_eastlea': '+263719092711',  # Mary Ncube - Eastlea area  
            'instructor_highfield': '+263719092712', # David Moyo - Highfield area
            'instructor_glen_view': '+263719092713', # Sarah Chikwanha - Glen View area
            'instructor_borrowdale': '+263719092714' # James Mufandaedza - Borrowdale area
        }

        updated_count = 0
        
        for username, phone in instructor_phones.items():
            instructor = User.query.filter_by(username=username).first()
            if instructor:
                if not instructor.phone:  # Only update if phone is not set
                    instructor.phone = phone
                    updated_count += 1
                    print(f"✅ Updated {instructor.get_full_name()}: {phone}")
                else:
                    print(f"📞 {instructor.get_full_name()} already has phone: {instructor.phone}")
            else:
                print(f"❌ Instructor '{username}' not found")

        if updated_count > 0:
            db.session.commit()
            print(f"\n🎉 Successfully updated {updated_count} instructor phone numbers!")
            print("\n📱 Instructors can now use WhatsApp:")
            
            # Show all instructors with phones
            instructors_with_phones = User.query.filter(
                User.role == 'instructor', 
                User.phone.isnot(None)
            ).all()
            
            for instructor in instructors_with_phones:
                print(f"  • {instructor.get_full_name()}: {instructor.phone}")
                
            print("\n💡 These instructors can now:")
            print("  • Send 'hi' to the WhatsApp bot")
            print("  • View their students: 'students'")
            print("  • Check today's lessons: 'today'")
            print("  • View weekly schedule: 'schedule'")
            print("  • Manage lessons: 'cancel [id]', 'confirm [id]', 'complete [id]'")
            
        else:
            print("ℹ️ No instructor phone numbers needed updating")

if __name__ == '__main__':
    add_instructor_phone_numbers()