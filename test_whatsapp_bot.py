
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from app import app
from models import db, Student, User, Lesson, WhatsAppSession, LESSON_SCHEDULED
from whatsappbot import whatsapp_bot

def test_whatsapp_bot():
    """Comprehensive test of WhatsApp bot functionality"""
    
    with app.app_context():
        print("🤖 Starting WhatsApp Bot Tests...")
        
        # Initialize the bot
        whatsapp_bot.initialize_twilio()
        
        # Get a test student
        student = Student.query.first()
        if not student:
            print("❌ No students found in database. Please create a student first.")
            return False
        
        print(f"📱 Testing with student: {student.name} ({student.phone})")
        
        # Test scenarios
        test_scenarios = [
            # Basic greeting
            ("hi", "Should show welcome menu"),
            ("hello", "Should show welcome menu"),
            ("Hi there", "Should show welcome menu"),
            
            # Menu navigation
            ("menu", "Should show main menu"),
            ("reset", "Should reset and show menu"),
            ("1", "Should show lessons"),
            ("2", "Should start booking flow"),
            ("3", "Should show progress"),
            ("4", "Should show cancel options"),
            ("5", "Should show help"),
            
            # Word-based commands
            ("lessons", "Should show lesson list"),
            ("book", "Should ask for duration"),
            ("progress", "Should show progress stats"),
            ("cancel", "Should show cancellation options"),
            ("help", "Should show help menu"),
            
            # Booking flow
            ("book", "Start booking"),
            ("30", "Select 30-minute duration"),
            ("back", "Go back from booking"),
            
            ("book", "Start booking again"),
            ("60", "Select 60-minute duration"),
            ("menu", "Exit booking flow"),
            
            # Error handling
            ("invalid command", "Should handle gracefully"),
            ("xyz", "Should show default help"),
            ("", "Should handle empty message"),
            
            # Edge cases
            ("book 999", "Should handle invalid slot"),
            ("cancel 999", "Should handle invalid lesson"),
            ("random text with book in it", "Should detect book command"),
            
            # Reset functionality
            ("reset", "Should always work to clear state"),
            ("restart", "Should work as reset"),
            ("clear", "Should work as reset"),
        ]
        
        success_count = 0
        total_tests = len(test_scenarios)
        
        for i, (message, description) in enumerate(test_scenarios, 1):
            print(f"\n🔍 Test {i}/{total_tests}: {description}")
            print(f"📤 Sending: '{message}'")
            
            try:
                response = whatsapp_bot.process_message(student.phone, message)
                
                # Basic validation
                if response and len(response) > 0:
                    print(f"✅ Got response ({len(response)} chars)")
                    if len(response) > 200:
                        print(f"📝 Response preview: {response[:200]}...")
                    else:
                        print(f"📝 Response: {response}")
                    success_count += 1
                else:
                    print(f"❌ Empty or invalid response")
                    
            except Exception as e:
                print(f"❌ Error: {str(e)}")
        
        print(f"\n📊 Test Results: {success_count}/{total_tests} tests passed")
        
        if success_count == total_tests:
            print("🎉 All tests passed! WhatsApp bot is working perfectly.")
            return True
        else:
            print(f"⚠️ {total_tests - success_count} tests failed. Bot needs attention.")
            return False

if __name__ == "__main__":
    test_whatsapp_bot()
