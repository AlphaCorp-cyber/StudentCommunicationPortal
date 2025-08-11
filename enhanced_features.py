#!/usr/bin/env python3
"""
Enhanced Features Implementation for DriveLink
- Real-time location tracking
- Smart matching algorithm
- Dynamic pricing
- Safety features
- Progress tracking
"""

import json
import math
import random
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Tuple
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class LocationService:
    """Real-time location tracking and GPS integration"""
    
    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula"""
        R = 6371  # Earth's radius in kilometers
        
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    @staticmethod
    def get_instructors_by_distance(student_lat: float, student_lon: float, 
                                  max_distance: float = 10.0) -> List[Dict]:
        """Get instructors sorted by distance from student"""
        from models import User
        
        instructors = User.query.filter_by(
            role='instructor', 
            active=True, 
            is_verified=True
        ).all()
        
        instructor_distances = []
        for instructor in instructors:
            if instructor.latitude and instructor.longitude:
                distance = LocationService.calculate_distance(
                    student_lat, student_lon,
                    instructor.latitude, instructor.longitude
                )
                if distance <= max_distance:
                    instructor_distances.append({
                        'instructor': instructor,
                        'distance': distance
                    })
        
        # Sort by distance
        instructor_distances.sort(key=lambda x: x['distance'])
        return instructor_distances
    
    @staticmethod
    def start_lesson_tracking(lesson_id: int) -> bool:
        """Start real-time tracking for a lesson"""
        from app import db
        from models import LocationTracker, Lesson
        
        try:
            lesson = Lesson.query.get(lesson_id)
            if not lesson:
                return False
            
            # Create tracking record
            tracker = LocationTracker()
            tracker.lesson_id = lesson_id
            tracker.instructor_id = lesson.instructor_id
            tracker.student_id = lesson.student_id
            tracker.latitude = 0.0  # Will be updated via GPS
            tracker.longitude = 0.0
            tracker.tracking_status = 'active'
            
            db.session.add(tracker)
            
            # Update lesson status
            lesson.lesson_tracking_active = True
            
            db.session.commit()
            logger.info(f"Started tracking for lesson {lesson_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting lesson tracking: {str(e)}")
            db.session.rollback()
            return False

class SmartMatchingAlgorithm:
    """AI-powered instructor-student matching"""
    
    @staticmethod
    def calculate_compatibility_score(student_id: int, instructor_id: int) -> float:
        """Calculate compatibility score between student and instructor"""
        from models import Student, User, MatchingPreferences, Review
        
        try:
            student = Student.query.get(student_id)
            instructor = User.query.get(instructor_id)
            preferences = MatchingPreferences.query.filter_by(student_id=student_id).first()
            
            if not all([student, instructor, preferences]):
                return 0.5  # Default neutral score
            
            score = 0.0
            max_score = 0.0
            
            # Distance factor (30% weight)
            if student.latitude and instructor.latitude:
                distance = LocationService.calculate_distance(
                    student.latitude, student.longitude,
                    instructor.latitude, instructor.longitude
                )
                distance_score = max(0, 1 - (distance / preferences.max_distance_km))
                score += distance_score * 0.3
            max_score += 0.3
            
            # Experience factor (25% weight)
            if preferences.preferred_experience_years:
                exp_diff = abs(instructor.experience_years - preferences.preferred_experience_years)
                exp_score = max(0, 1 - (exp_diff / 10))  # Normalize to 10 years
                score += exp_score * 0.25
            max_score += 0.25
            
            # Rating factor (20% weight)
            if instructor.average_rating:
                rating_score = instructor.average_rating / 5.0
                score += rating_score * 0.2
            max_score += 0.2
            
            # Availability factor (15% weight)
            availability_score = SmartMatchingAlgorithm._check_availability_match(
                student_id, instructor_id
            )
            score += availability_score * 0.15
            max_score += 0.15
            
            # Reviews sentiment factor (10% weight)
            review_score = SmartMatchingAlgorithm._analyze_review_sentiment(instructor_id)
            score += review_score * 0.1
            max_score += 0.1
            
            return score / max_score if max_score > 0 else 0.5
            
        except Exception as e:
            logger.error(f"Error calculating compatibility: {str(e)}")
            return 0.5
    
    @staticmethod
    def _check_availability_match(student_id: int, instructor_id: int) -> float:
        """Check how well instructor availability matches student preferences"""
        # Simplified implementation - in real app would check detailed schedules
        return random.uniform(0.6, 1.0)  # Mock good availability match
    
    @staticmethod
    def _analyze_review_sentiment(instructor_id: int) -> float:
        """Analyze sentiment of instructor reviews"""
        from models import Review
        
        reviews = Review.query.filter_by(instructor_id=instructor_id).limit(10).all()
        if not reviews:
            return 0.7  # Default neutral-positive
        
        # Simplified sentiment analysis based on ratings and keywords
        total_sentiment = 0
        for review in reviews:
            sentiment = review.overall_rating / 5.0
            if review.review_text:
                # Simple keyword analysis
                positive_words = ['excellent', 'great', 'amazing', 'patient', 'helpful']
                negative_words = ['bad', 'terrible', 'rude', 'impatient', 'late']
                
                text_lower = review.review_text.lower()
                pos_count = sum(1 for word in positive_words if word in text_lower)
                neg_count = sum(1 for word in negative_words if word in text_lower)
                
                if pos_count > neg_count:
                    sentiment += 0.1
                elif neg_count > pos_count:
                    sentiment -= 0.1
            
            total_sentiment += min(1.0, max(0.0, sentiment))
        
        return total_sentiment / len(reviews)
    
    @staticmethod
    def get_recommended_instructors(student_id: int, limit: int = 5) -> List[Dict]:
        """Get top recommended instructors for a student"""
        from models import User, Student
        
        student = Student.query.get(student_id)
        if not student:
            return []
        
        # Get all available instructors
        instructors = User.query.filter_by(
            role='instructor',
            active=True,
            is_verified=True
        ).all()
        
        # Calculate compatibility scores
        recommendations = []
        for instructor in instructors:
            score = SmartMatchingAlgorithm.calculate_compatibility_score(
                student_id, instructor.id
            )
            recommendations.append({
                'instructor': instructor,
                'compatibility_score': score,
                'match_percentage': int(score * 100)
            })
        
        # Sort by score and return top matches
        recommendations.sort(key=lambda x: x['compatibility_score'], reverse=True)
        return recommendations[:limit]

class DynamicPricingEngine:
    """Uber-style dynamic pricing system"""
    
    @staticmethod
    def calculate_lesson_price(student_id: int, instructor_id: int, 
                             duration_minutes: int, lesson_date: datetime) -> Dict:
        """Calculate dynamic price for a lesson"""
        from models import User, PricingRule
        
        try:
            instructor = User.query.get(instructor_id)
            if not instructor:
                return {'error': 'Instructor not found'}
            
            # Base price
            if duration_minutes == 30:
                base_price = float(instructor.hourly_rate_30min or 15)
            else:
                base_price = float(instructor.hourly_rate_60min or 25)
            
            # Apply dynamic pricing rules
            surge_multiplier = DynamicPricingEngine._calculate_surge_multiplier(
                lesson_date, instructor.base_location
            )
            
            # Calculate final price
            dynamic_price = base_price * surge_multiplier
            
            # Check for applicable discounts
            discount = DynamicPricingEngine._check_applicable_discounts(
                student_id, dynamic_price, lesson_date
            )
            
            final_price = dynamic_price - discount
            
            return {
                'base_price': base_price,
                'surge_multiplier': surge_multiplier,
                'dynamic_price': dynamic_price,
                'discount': discount,
                'final_price': final_price,
                'surge_reason': DynamicPricingEngine._get_surge_reason(surge_multiplier)
            }
            
        except Exception as e:
            logger.error(f"Error calculating dynamic price: {str(e)}")
            return {'error': 'Price calculation failed'}
    
    @staticmethod
    def _calculate_surge_multiplier(lesson_date: datetime, location: str) -> float:
        """Calculate surge pricing multiplier based on demand"""
        multiplier = 1.0
        
        # Time-based surge
        hour = lesson_date.hour
        day_of_week = lesson_date.weekday()
        
        # Peak hours (7-9 AM, 5-7 PM on weekdays)
        if day_of_week < 5:  # Weekday
            if (7 <= hour <= 9) or (17 <= hour <= 19):
                multiplier += 0.3  # 30% surge
        
        # Weekend premium
        if day_of_week >= 5:  # Weekend
            multiplier += 0.2  # 20% weekend premium
        
        # Location-based surge (simplified)
        high_demand_areas = ['Harare CBD', 'Avondale', 'Mount Pleasant']
        if location in high_demand_areas:
            multiplier += 0.1  # 10% location premium
        
        # Weather-based surge (mock implementation)
        # In real app, would integrate with weather API
        if random.random() < 0.1:  # 10% chance of weather surge
            multiplier += 0.2  # Bad weather premium
        
        return min(multiplier, 2.5)  # Cap at 2.5x
    
    @staticmethod
    def _check_applicable_discounts(student_id: int, price: float, 
                                  lesson_date: datetime) -> float:
        """Check for applicable discounts"""
        from models import Student, PromoCode, LoyaltyProgram
        
        total_discount = 0.0
        
        # First-time user discount
        student = Student.query.get(student_id)
        if student and student.lessons_completed == 0:
            total_discount += price * 0.15  # 15% first-time discount
        
        # Loyalty program discount
        loyalty = LoyaltyProgram.query.filter_by(student_id=student_id).first()
        if loyalty and loyalty.current_tier in ['Gold', 'Platinum']:
            tier_discount = 0.1 if loyalty.current_tier == 'Gold' else 0.15
            total_discount += price * tier_discount
        
        return min(total_discount, price * 0.4)  # Cap discount at 40%
    
    @staticmethod
    def _get_surge_reason(multiplier: float) -> str:
        """Get human-readable surge reason"""
        if multiplier <= 1.1:
            return "Standard pricing"
        elif multiplier <= 1.3:
            return "Slightly higher demand"
        elif multiplier <= 1.6:
            return "High demand period"
        else:
            return "Very high demand - consider booking later for lower prices"

class SafetyManager:
    """Safety features and emergency management"""
    
    @staticmethod
    def trigger_emergency(lesson_id: int, incident_type: str, description: str) -> bool:
        """Trigger emergency protocol"""
        from app import db
        from models import SafetyIncident, Lesson, Student, User
        
        try:
            lesson = Lesson.query.get(lesson_id)
            if not lesson:
                return False
            
            # Create safety incident
            incident = SafetyIncident()
            incident.lesson_id = lesson_id
            incident.instructor_id = lesson.instructor_id
            incident.student_id = lesson.student_id
            incident.incident_type = incident_type
            incident.description = description
            incident.severity = SafetyManager._assess_severity(incident_type)
            
            db.session.add(incident)
            
            # Notify emergency contacts
            SafetyManager._notify_emergency_contacts(lesson)
            
            # If critical, call emergency services
            if incident.severity == 'critical':
                SafetyManager._alert_emergency_services(incident)
            
            db.session.commit()
            logger.warning(f"Emergency triggered for lesson {lesson_id}: {incident_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error handling emergency: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def _assess_severity(incident_type: str) -> str:
        """Assess incident severity"""
        critical_types = ['accident', 'medical_emergency', 'vehicle_breakdown']
        high_types = ['panic_button', 'harassment', 'unsafe_driving']
        
        if incident_type in critical_types:
            return 'critical'
        elif incident_type in high_types:
            return 'high'
        else:
            return 'medium'
    
    @staticmethod
    def _notify_emergency_contacts(lesson) -> None:
        """Notify emergency contacts"""
        # In real implementation, would send SMS/calls to emergency contacts
        logger.info(f"Emergency contacts notified for lesson {lesson.id}")
    
    @staticmethod
    def _alert_emergency_services(incident) -> None:
        """Alert emergency services for critical incidents"""
        # In real implementation, would integrate with emergency services API
        logger.critical(f"Emergency services alerted for incident {incident.id}")

class ProgressTracker:
    """Student progress tracking and gamification"""
    
    @staticmethod
    def update_skill_assessment(student_id: int, skill: str, score: int) -> bool:
        """Update student's skill assessment score"""
        from app import db
        from models import StudentProgress
        
        try:
            progress = StudentProgress.query.filter_by(student_id=student_id).first()
            if not progress:
                progress = StudentProgress()
                progress.student_id = student_id
                db.session.add(progress)
            
            # Update specific skill score
            skill_mapping = {
                'parallel_parking': 'parallel_parking_score',
                'highway_driving': 'highway_driving_score',
                'city_driving': 'city_driving_score',
                'reverse_parking': 'reverse_parking_score',
                'emergency_braking': 'emergency_braking_score'
            }
            
            if skill in skill_mapping:
                setattr(progress, skill_mapping[skill], score)
                
                # Check for badge eligibility
                ProgressTracker._check_badge_eligibility(progress)
                
                db.session.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating skill assessment: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def _check_badge_eligibility(progress) -> None:
        """Check if student earned new badges"""
        current_badges = json.loads(progress.badges_earned or '[]')
        new_badges = []
        
        # Skill-specific badges
        if progress.parallel_parking_score >= 90 and 'parking_master' not in current_badges:
            new_badges.append('parking_master')
        
        if progress.highway_driving_score >= 85 and 'highway_hero' not in current_badges:
            new_badges.append('highway_hero')
        
        # Progress milestones
        if progress.total_lessons_completed >= 10 and 'persistent_learner' not in current_badges:
            new_badges.append('persistent_learner')
        
        if progress.total_hours_driven >= 20 and 'experienced_driver' not in current_badges:
            new_badges.append('experienced_driver')
        
        # Update badges if new ones earned
        if new_badges:
            all_badges = current_badges + new_badges
            progress.badges_earned = json.dumps(all_badges)
            logger.info(f"Student {progress.student_id} earned badges: {new_badges}")
    
    @staticmethod
    def calculate_test_readiness(student_id: int) -> int:
        """Calculate student's test readiness score"""
        from models import StudentProgress, Lesson
        
        progress = StudentProgress.query.filter_by(student_id=student_id).first()
        if not progress:
            return 0
        
        # Weight different factors
        skill_score = (
            progress.parallel_parking_score * 0.2 +
            progress.highway_driving_score * 0.2 +
            progress.city_driving_score * 0.25 +
            progress.reverse_parking_score * 0.15 +
            progress.emergency_braking_score * 0.2
        )
        
        # Experience factor
        experience_score = min(100, progress.total_hours_driven * 2)  # Cap at 50 hours
        
        # Lesson consistency
        recent_lessons = Lesson.query.filter_by(
            student_id=student_id,
            status='completed'
        ).filter(
            Lesson.completed_date >= datetime.now() - timedelta(days=30)
        ).count()
        
        consistency_score = min(100, recent_lessons * 10)  # Recent activity matters
        
        # Weighted final score
        readiness_score = int(
            skill_score * 0.6 +
            experience_score * 0.25 +
            consistency_score * 0.15
        )
        
        # Update progress record
        progress.test_readiness_score = readiness_score
        
        return readiness_score

class CommunicationManager:
    """Advanced communication features"""
    
    @staticmethod
    def send_lesson_recap(lesson_id: int) -> bool:
        """Send automated lesson recap to student"""
        from app import db
        from models import CommunicationLog, Lesson, Review
        
        try:
            lesson = Lesson.query.get(lesson_id)
            if not lesson or lesson.status != 'completed':
                return False
            
            # Generate recap content
            recap = CommunicationManager._generate_lesson_recap(lesson)
            
            # Log communication
            comm_log = CommunicationLog()
            comm_log.sender_type = 'system'
            comm_log.recipient_type = 'student'
            comm_log.recipient_id = lesson.student_id
            comm_log.message_type = 'lesson_recap'
            comm_log.message_content = recap
            comm_log.lesson_id = lesson_id
            
            db.session.add(comm_log)
            db.session.commit()
            
            # In real implementation, would send via WhatsApp
            logger.info(f"Lesson recap sent for lesson {lesson_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending lesson recap: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def _generate_lesson_recap(lesson) -> str:
        """Generate lesson recap content"""
        recap = f"📚 Lesson Recap - {lesson.lesson_date.strftime('%Y-%m-%d')}\n\n"
        recap += f"⏱️ Duration: {lesson.duration_minutes} minutes\n"
        recap += f"📍 Location: {lesson.location}\n\n"
        
        if lesson.skills_practiced:
            skills = json.loads(lesson.skills_practiced)
            recap += "🎯 Skills Practiced:\n"
            for skill in skills:
                recap += f"• {skill}\n"
            recap += "\n"
        
        if lesson.instructor_assessment:
            recap += f"👨‍🏫 Instructor Notes:\n{lesson.instructor_assessment}\n\n"
        
        if lesson.notes:
            recap += f"📝 Additional Notes:\n{lesson.notes}\n\n"
        
        recap += "🌟 Don't forget to rate your lesson and book your next session!"
        
        return recap
    
    @staticmethod
    def schedule_reminder(lesson_id: int, reminder_type: str = '24_hours') -> bool:
        """Schedule lesson reminder"""
        from app import db
        from models import CommunicationLog, Lesson
        
        try:
            lesson = Lesson.query.get(lesson_id)
            if not lesson:
                return False
            
            # Calculate reminder time
            reminder_times = {
                '24_hours': timedelta(hours=24),
                '2_hours': timedelta(hours=2),
                '30_minutes': timedelta(minutes=30)
            }
            
            reminder_time = lesson.lesson_date - reminder_times.get(reminder_type, timedelta(hours=24))
            
            if reminder_time <= datetime.now():
                return False  # Too late to schedule
            
            # Create reminder message
            message = f"🔔 Lesson Reminder\n\n"
            message += f"📅 Date: {lesson.lesson_date.strftime('%Y-%m-%d %H:%M')}\n"
            message += f"👨‍🏫 Instructor: {lesson.instructor.get_full_name()}\n"
            message += f"📍 Location: {lesson.location}\n"
            message += f"⏱️ Duration: {lesson.duration_minutes} minutes\n\n"
            message += "See you soon! 🚗"
            
            # Schedule communication (in real app, would use task queue)
            comm_log = CommunicationLog()
            comm_log.sender_type = 'system'
            comm_log.recipient_type = 'student'
            comm_log.recipient_id = lesson.student_id
            comm_log.message_type = 'reminder'
            comm_log.message_content = message
            comm_log.lesson_id = lesson_id
            comm_log.sent_at = reminder_time  # Schedule for future
            
            db.session.add(comm_log)
            db.session.commit()
            
            logger.info(f"Reminder scheduled for lesson {lesson_id} at {reminder_time}")
            return True
            
        except Exception as e:
            logger.error(f"Error scheduling reminder: {str(e)}")
            db.session.rollback()
            return False

# Enhanced Services Integration
class EnhancedFeatures:
    """Main class to coordinate all enhanced features"""
    
    def __init__(self):
        self.location_service = LocationService()
        self.matching_algorithm = SmartMatchingAlgorithm()
        self.pricing_engine = DynamicPricingEngine()
        self.safety_manager = SafetyManager()
        self.progress_tracker = ProgressTracker()
        self.communication_manager = CommunicationManager()
    
    def get_smart_instructor_recommendations(self, student_id: int, 
                                           max_distance: float = 10.0) -> List[Dict]:
        """Get AI-powered instructor recommendations"""
        try:
            # Get ML-based recommendations
            recommendations = self.matching_algorithm.get_recommended_instructors(
                student_id, limit=10
            )
            
            # Enhance with real-time data
            enhanced_recommendations = []
            for rec in recommendations:
                instructor = rec['instructor']
                
                # Add dynamic pricing
                pricing = self.pricing_engine.calculate_lesson_price(
                    student_id, instructor.id, 60, datetime.now() + timedelta(days=1)
                )
                
                # Add availability status
                availability = self._check_real_time_availability(instructor.id)
                
                enhanced_rec = {
                    **rec,
                    'pricing': pricing,
                    'availability': availability,
                    'safety_score': self._calculate_safety_score(instructor.id)
                }
                
                enhanced_recommendations.append(enhanced_rec)
            
            return enhanced_recommendations
            
        except Exception as e:
            logger.error(f"Error getting smart recommendations: {str(e)}")
            return []
    
    def _check_real_time_availability(self, instructor_id: int) -> Dict:
        """Check instructor's real-time availability"""
        # Simplified implementation
        return {
            'available_today': random.choice([True, False]),
            'next_available_slot': datetime.now() + timedelta(hours=random.randint(2, 48)),
            'slots_this_week': random.randint(5, 20)
        }
    
    def _calculate_safety_score(self, instructor_id: int) -> int:
        """Calculate instructor safety score"""
        from models import SafetyIncident
        
        # Check incident history
        incidents = SafetyIncident.query.filter_by(instructor_id=instructor_id).count()
        
        # Base score of 95, deduct for incidents
        safety_score = max(70, 95 - (incidents * 5))
        
        return safety_score

# Global enhanced features instance
enhanced_features = EnhancedFeatures()