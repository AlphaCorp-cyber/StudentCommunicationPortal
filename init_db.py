#!/usr/bin/env python3
"""
Database initialization script for DriveLink
This script safely initializes the database with proper error handling
"""
import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database():
    """Initialize the database with proper error handling"""
    try:
        from app import app, db
        
        with app.app_context():
            logger.info("Starting database initialization...")
            
            # Import all models to ensure they're registered
            import models
            
            # Create all tables
            db.create_all()
            logger.info("Database tables created successfully")
            
            # Check if we need to add default data
            from models import SystemConfig, LessonPricing
            
            # Add default lesson pricing if it doesn't exist
            if not LessonPricing.query.first():
                logger.info("Adding default lesson pricing...")
                class4_pricing = LessonPricing()
                class4_pricing.license_class = 'Class 4'
                class4_pricing.price_per_30min = 15.00
                class4_pricing.price_per_60min = 25.00
                db.session.add(class4_pricing)
                
                class2_pricing = LessonPricing()
                class2_pricing.license_class = 'Class 2'
                class2_pricing.price_per_30min = 20.00
                class2_pricing.price_per_60min = 35.00
                db.session.add(class2_pricing)
                
                db.session.commit()
                logger.info("Default lesson pricing added")
            
            # Add default system configurations
            default_configs = [
                ('app_name', 'DriveLink', 'Application name'),
                ('max_daily_lessons_per_student', '2', 'Maximum lessons a student can book per day'),
                ('booking_advance_days', '14', 'Maximum days in advance students can book'),
                ('instructor_search_radius_km', '50', 'Default search radius for finding instructors')
            ]
            
            for key, value, description in default_configs:
                if not SystemConfig.query.filter_by(key=key).first():
                    SystemConfig.set_config(key, value, description)
                    logger.info(f"Added system config: {key}")
            
            logger.info("Database initialization completed successfully")
            return True
            
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = init_database()
    exit(0 if success else 1)