#!/usr/bin/env python3
"""
Gamification and Progress Tracking System for DriveLink
- Badge system
- Achievement tracking
- Progress milestones
- Leaderboards
- Skills assessment
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class BadgeSystem:
    """Achievement badge system for students"""
    
    # Define all available badges
    BADGES = {
        # Skill-based badges
        'parking_master': {
            'name': 'Parking Master',
            'description': 'Perfect parallel parking score (90+)',
            'icon': '🅿️',
            'points': 100,
            'condition': lambda progress: progress.parallel_parking_score >= 90
        },
        'highway_hero': {
            'name': 'Highway Hero', 
            'description': 'Excellent highway driving score (85+)',
            'icon': '🛣️',
            'points': 100,
            'condition': lambda progress: progress.highway_driving_score >= 85
        },
        'city_navigator': {
            'name': 'City Navigator',
            'description': 'Master city driving (80+)',
            'icon': '🏙️',
            'points': 80,
            'condition': lambda progress: progress.city_driving_score >= 80
        },
        'emergency_expert': {
            'name': 'Emergency Expert',
            'description': 'Perfect emergency braking (95+)',
            'icon': '🚨',
            'points': 120,
            'condition': lambda progress: progress.emergency_braking_score >= 95
        },
        'reverse_specialist': {
            'name': 'Reverse Specialist',
            'description': 'Excellent reverse parking (85+)',
            'icon': '↩️',
            'points': 90,
            'condition': lambda progress: progress.reverse_parking_score >= 85
        },
        
        # Progress-based badges
        'first_lesson': {
            'name': 'First Lesson',
            'description': 'Completed your first lesson',
            'icon': '🎓',
            'points': 50,
            'condition': lambda progress: progress.total_lessons_completed >= 1
        },
        'persistent_learner': {
            'name': 'Persistent Learner',
            'description': 'Completed 10 lessons',
            'icon': '📚',
            'points': 200,
            'condition': lambda progress: progress.total_lessons_completed >= 10
        },
        'dedicated_student': {
            'name': 'Dedicated Student',
            'description': 'Completed 25 lessons',
            'icon': '🏆',
            'points': 500,
            'condition': lambda progress: progress.total_lessons_completed >= 25
        },
        'experienced_driver': {
            'name': 'Experienced Driver',
            'description': 'Driven for 20+ hours',
            'icon': '⏱️',
            'points': 300,
            'condition': lambda progress: progress.total_hours_driven >= 20
        },
        'marathon_driver': {
            'name': 'Marathon Driver',
            'description': 'Driven for 50+ hours',
            'icon': '🏃',
            'points': 750,
            'condition': lambda progress: progress.total_hours_driven >= 50
        },
        
        # Test readiness badges
        'test_ready': {
            'name': 'Test Ready',
            'description': 'Test readiness score 80+',
            'icon': '✅',
            'points': 400,
            'condition': lambda progress: progress.test_readiness_score >= 80
        },
        'almost_perfect': {
            'name': 'Almost Perfect',
            'description': 'Test readiness score 95+',
            'icon': '⭐',
            'points': 600,
            'condition': lambda progress: progress.test_readiness_score >= 95
        },
        
        # Social badges
        'helpful_reviewer': {
            'name': 'Helpful Reviewer',
            'description': 'Left 5+ detailed reviews',
            'icon': '💬',
            'points': 150,
            'condition': 'custom'  # Handled separately
        },
        'referral_champion': {
            'name': 'Referral Champion',
            'description': 'Referred 3+ friends',
            'icon': '🤝',
            'points': 300,
            'condition': 'custom'  # Handled separately
        },
        
        # Special achievement badges
        'early_bird': {
            'name': 'Early Bird',
            'description': 'Booked 5+ morning lessons',
            'icon': '🌅',
            'points': 100,
            'condition': 'custom'
        },
        'night_owl': {
            'name': 'Night Owl',
            'description': 'Booked 5+ evening lessons',
            'icon': '🌙',
            'points': 100,
            'condition': 'custom'
        },
        'weather_warrior': {
            'name': 'Weather Warrior',
            'description': 'Practiced in challenging weather',
            'icon': '⛈️',
            'points': 200,
            'condition': 'custom'
        },
        'safety_champion': {
            'name': 'Safety Champion',
            'description': 'No safety incidents for 20+ hours',
            'icon': '🛡️',
            'points': 400,
            'condition': 'custom'
        }
    }
    
    @staticmethod
    def check_badges_for_student(student_id: int) -> List[str]:
        """Check and award new badges for a student"""
        from models import StudentProgress, Student
        
        try:
            progress = StudentProgress.query.filter_by(student_id=student_id).first()
            student = Student.query.get(student_id)
            
            if not progress or not student:
                return []
            
            current_badges = json.loads(progress.badges_earned or '[]')
            new_badges = []
            
            # Check skill and progress-based badges
            for badge_id, badge_info in BadgeSystem.BADGES.items():
                if badge_id not in current_badges:
                    condition = badge_info.get('condition')
                    
                    if callable(condition):
                        if condition(progress):
                            new_badges.append(badge_id)
                    elif condition == 'custom':
                        # Handle custom badges
                        if BadgeSystem._check_custom_badge(badge_id, student_id):
                            new_badges.append(badge_id)
            
            # Update badges if new ones earned
            if new_badges:
                all_badges = current_badges + new_badges
                progress.badges_earned = json.dumps(all_badges)
                
                # Award points
                total_points = sum(BadgeSystem.BADGES[badge]['points'] for badge in new_badges)
                BadgeSystem._award_points(student_id, total_points)
                
                from app import db
                db.session.commit()
                
                logger.info(f"Student {student_id} earned badges: {new_badges}")
            
            return new_badges
            
        except Exception as e:
            logger.error(f"Error checking badges: {str(e)}")
            return []
    
    @staticmethod
    def _check_custom_badge(badge_id: str, student_id: int) -> bool:
        """Check custom badge conditions"""
        from models import Review, LoyaltyProgram, Lesson, SafetyIncident
        
        try:
            if badge_id == 'helpful_reviewer':
                review_count = Review.query.filter_by(student_id=student_id).filter(
                    Review.review_text.isnot(None)
                ).count()
                return review_count >= 5
            
            elif badge_id == 'referral_champion':
                loyalty = LoyaltyProgram.query.filter_by(student_id=student_id).first()
                return loyalty and loyalty.referrals_made >= 3
            
            elif badge_id == 'early_bird':
                morning_lessons = Lesson.query.filter_by(student_id=student_id).filter(
                    Lesson.lesson_date.extract('hour') < 10
                ).count()
                return morning_lessons >= 5
            
            elif badge_id == 'night_owl':
                evening_lessons = Lesson.query.filter_by(student_id=student_id).filter(
                    Lesson.lesson_date.extract('hour') >= 18
                ).count()
                return evening_lessons >= 5
            
            elif badge_id == 'safety_champion':
                # Check for safety incidents
                incidents = SafetyIncident.query.filter_by(student_id=student_id).count()
                progress = StudentProgress.query.filter_by(student_id=student_id).first()
                return incidents == 0 and progress and progress.total_hours_driven >= 20
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking custom badge {badge_id}: {str(e)}")
            return False
    
    @staticmethod
    def _award_points(student_id: int, points: int):
        """Award loyalty points for achievements"""
        from models import LoyaltyProgram
        
        try:
            loyalty = LoyaltyProgram.query.filter_by(student_id=student_id).first()
            if not loyalty:
                loyalty = LoyaltyProgram()
                loyalty.student_id = student_id
                from app import db
                db.session.add(loyalty)
            
            loyalty.total_points += points
            loyalty.available_points += points
            
            # Check for tier upgrades
            BadgeSystem._check_tier_upgrade(loyalty)
            
        except Exception as e:
            logger.error(f"Error awarding points: {str(e)}")
    
    @staticmethod
    def _check_tier_upgrade(loyalty):
        """Check and upgrade loyalty tier based on points"""
        tiers = {
            'Bronze': 0,
            'Silver': 500,
            'Gold': 1500,
            'Platinum': 3000
        }
        
        current_tier = 'Bronze'
        for tier, required_points in tiers.items():
            if loyalty.total_points >= required_points:
                current_tier = tier
        
        if current_tier != loyalty.current_tier:
            loyalty.current_tier = current_tier
            logger.info(f"Student {loyalty.student_id} upgraded to {current_tier} tier!")

class ProgressTracker:
    """Advanced progress tracking and analytics"""
    
    @staticmethod
    def update_lesson_progress(lesson_id: int):
        """Update student progress after lesson completion"""
        from models import Lesson, StudentProgress
        
        try:
            lesson = Lesson.query.get(lesson_id)
            if not lesson or lesson.status != 'completed':
                return
            
            progress = StudentProgress.query.filter_by(student_id=lesson.student_id).first()
            if not progress:
                progress = StudentProgress()
                progress.student_id = lesson.student_id
                from app import db
                db.session.add(progress)
            
            # Update basic stats
            progress.total_lessons_completed += 1
            progress.total_hours_driven += lesson.duration_minutes / 60.0
            
            # Update skill-specific progress based on lesson content
            skills_practiced = json.loads(lesson.skills_practiced or '[]')
            for skill in skills_practiced:
                ProgressTracker._update_skill_score(progress, skill)
            
            # Recalculate test readiness
            progress.test_readiness_score = ProgressTracker._calculate_test_readiness(progress)
            
            from app import db
            db.session.commit()
            
            # Check for new badges
            BadgeSystem.check_badges_for_student(lesson.student_id)
            
        except Exception as e:
            logger.error(f"Error updating lesson progress: {str(e)}")
    
    @staticmethod
    def _update_skill_score(progress, skill: str):
        """Update individual skill scores"""
        # Simplified skill improvement logic
        improvement = 5  # Base improvement per practice
        
        skill_mapping = {
            'parallel_parking': 'parallel_parking_score',
            'highway_driving': 'highway_driving_score', 
            'city_driving': 'city_driving_score',
            'reverse_parking': 'reverse_parking_score',
            'emergency_braking': 'emergency_braking_score'
        }
        
        if skill in skill_mapping:
            current_score = getattr(progress, skill_mapping[skill], 0)
            new_score = min(100, current_score + improvement)
            setattr(progress, skill_mapping[skill], new_score)
    
    @staticmethod
    def _calculate_test_readiness(progress) -> int:
        """Calculate comprehensive test readiness score"""
        # Weighted scoring algorithm
        skill_scores = [
            progress.parallel_parking_score,
            progress.highway_driving_score,
            progress.city_driving_score,
            progress.reverse_parking_score,
            progress.emergency_braking_score
        ]
        
        # Average skill score (40% weight)
        avg_skill = sum(skill_scores) / len(skill_scores) if skill_scores else 0
        skill_component = avg_skill * 0.4
        
        # Experience component (35% weight)
        hours_component = min(100, progress.total_hours_driven * 2) * 0.35
        
        # Lesson frequency component (25% weight)
        lessons_component = min(100, progress.total_lessons_completed * 4) * 0.25
        
        return int(skill_component + hours_component + lessons_component)
    
    @staticmethod
    def get_progress_summary(student_id: int) -> Dict:
        """Get comprehensive progress summary for student"""
        from models import StudentProgress, Student, Lesson
        
        try:
            progress = StudentProgress.query.filter_by(student_id=student_id).first()
            student = Student.query.get(student_id)
            
            if not progress or not student:
                return {}
            
            # Recent activity
            recent_lessons = Lesson.query.filter_by(
                student_id=student_id,
                status='completed'
            ).filter(
                Lesson.completed_date >= datetime.now() - timedelta(days=30)
            ).count()
            
            # Badge info
            badges = json.loads(progress.badges_earned or '[]')
            badge_details = [
                {
                    'id': badge_id,
                    'name': BadgeSystem.BADGES[badge_id]['name'],
                    'icon': BadgeSystem.BADGES[badge_id]['icon']
                }
                for badge_id in badges
                if badge_id in BadgeSystem.BADGES
            ]
            
            return {
                'student_name': student.name,
                'test_readiness': progress.test_readiness_score,
                'total_lessons': progress.total_lessons_completed,
                'total_hours': progress.total_hours_driven,
                'recent_activity': recent_lessons,
                'skill_scores': {
                    'parallel_parking': progress.parallel_parking_score,
                    'highway_driving': progress.highway_driving_score,
                    'city_driving': progress.city_driving_score,
                    'reverse_parking': progress.reverse_parking_score,
                    'emergency_braking': progress.emergency_braking_score
                },
                'badges': badge_details,
                'next_milestones': ProgressTracker._get_next_milestones(progress)
            }
            
        except Exception as e:
            logger.error(f"Error getting progress summary: {str(e)}")
            return {}
    
    @staticmethod
    def _get_next_milestones(progress) -> List[Dict]:
        """Get next achievable milestones for student"""
        milestones = []
        
        # Lesson milestones
        if progress.total_lessons_completed < 10:
            milestones.append({
                'type': 'lessons',
                'description': 'Complete 10 lessons',
                'current': progress.total_lessons_completed,
                'target': 10,
                'reward': 'Persistent Learner badge'
            })
        elif progress.total_lessons_completed < 25:
            milestones.append({
                'type': 'lessons', 
                'description': 'Complete 25 lessons',
                'current': progress.total_lessons_completed,
                'target': 25,
                'reward': 'Dedicated Student badge'
            })
        
        # Test readiness milestone
        if progress.test_readiness_score < 80:
            milestones.append({
                'type': 'test_readiness',
                'description': 'Achieve 80% test readiness',
                'current': progress.test_readiness_score,
                'target': 80,
                'reward': 'Test Ready badge'
            })
        
        # Skill-specific milestones
        skills = {
            'parallel_parking': ('parallel_parking_score', 90, 'Parking Master badge'),
            'highway_driving': ('highway_driving_score', 85, 'Highway Hero badge'),
            'city_driving': ('city_driving_score', 80, 'City Navigator badge')
        }
        
        for skill_name, (attr, target, reward) in skills.items():
            current = getattr(progress, attr, 0)
            if current < target:
                milestones.append({
                    'type': 'skill',
                    'description': f'Master {skill_name.replace("_", " ")}',
                    'current': current,
                    'target': target,
                    'reward': reward
                })
        
        return milestones[:3]  # Return top 3 milestones

class LeaderboardSystem:
    """Leaderboard and ranking system"""
    
    @staticmethod
    def get_leaderboard(category: str = 'overall', limit: int = 10) -> List[Dict]:
        """Get leaderboard for different categories"""
        from models import StudentProgress, Student, LoyaltyProgram
        
        try:
            if category == 'overall':
                # Overall ranking based on test readiness and total points
                query = db.session.query(
                    StudentProgress, Student, LoyaltyProgram
                ).join(
                    Student, StudentProgress.student_id == Student.id
                ).outerjoin(
                    LoyaltyProgram, Student.id == LoyaltyProgram.student_id
                ).order_by(
                    StudentProgress.test_readiness_score.desc(),
                    LoyaltyProgram.total_points.desc()
                ).limit(limit)
                
            elif category == 'test_readiness':
                query = db.session.query(
                    StudentProgress, Student
                ).join(
                    Student, StudentProgress.student_id == Student.id
                ).order_by(
                    StudentProgress.test_readiness_score.desc()
                ).limit(limit)
                
            elif category == 'most_lessons':
                query = db.session.query(
                    StudentProgress, Student
                ).join(
                    Student, StudentProgress.student_id == Student.id
                ).order_by(
                    StudentProgress.total_lessons_completed.desc()
                ).limit(limit)
                
            elif category == 'loyalty_points':
                query = db.session.query(
                    LoyaltyProgram, Student
                ).join(
                    Student, LoyaltyProgram.student_id == Student.id
                ).order_by(
                    LoyaltyProgram.total_points.desc()
                ).limit(limit)
            
            else:
                return []
            
            leaderboard = []
            for i, result in enumerate(query.all(), 1):
                if category == 'overall':
                    progress, student, loyalty = result
                    score = progress.test_readiness_score
                    points = loyalty.total_points if loyalty else 0
                elif category in ['test_readiness', 'most_lessons']:
                    progress, student = result
                    score = progress.test_readiness_score if category == 'test_readiness' else progress.total_lessons_completed
                    points = 0
                else:  # loyalty_points
                    loyalty, student = result
                    score = loyalty.total_points
                    points = loyalty.total_points
                
                leaderboard.append({
                    'rank': i,
                    'student_name': student.name,
                    'score': score,
                    'points': points,
                    'tier': getattr(loyalty, 'current_tier', 'Bronze') if category == 'overall' else None
                })
            
            return leaderboard
            
        except Exception as e:
            logger.error(f"Error getting leaderboard: {str(e)}")
            return []

# Global instances
gamification = {
    'badges': BadgeSystem(),
    'progress': ProgressTracker(),
    'leaderboard': LeaderboardSystem()
}