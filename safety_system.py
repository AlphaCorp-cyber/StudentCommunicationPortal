#!/usr/bin/env python3
"""
Comprehensive Safety System for DriveLink
- Emergency protocols
- Panic button functionality
- Real-time tracking
- Incident management
- Emergency contact system
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class EmergencyProtocol:
    """Emergency response and safety protocols"""
    
    EMERGENCY_TYPES = {
        'panic_button': {
            'severity': 'high',
            'response_time': 30,  # seconds
            'auto_actions': ['notify_contacts', 'alert_dispatch']
        },
        'accident': {
            'severity': 'critical',
            'response_time': 10,
            'auto_actions': ['call_emergency_services', 'notify_contacts', 'alert_dispatch']
        },
        'medical_emergency': {
            'severity': 'critical',
            'response_time': 5,
            'auto_actions': ['call_emergency_services', 'notify_contacts']
        },
        'vehicle_breakdown': {
            'severity': 'medium',
            'response_time': 300,
            'auto_actions': ['notify_contacts', 'arrange_assistance']
        },
        'harassment': {
            'severity': 'high',
            'response_time': 60,
            'auto_actions': ['notify_contacts', 'alert_dispatch', 'record_incident']
        },
        'unsafe_driving': {
            'severity': 'medium',
            'response_time': 120,
            'auto_actions': ['notify_instructor', 'record_incident']
        }
    }
    
    @staticmethod
    def trigger_emergency(lesson_id: int, emergency_type: str, 
                         description: str, location: Tuple[float, float] = None) -> bool:
        """Trigger emergency protocol"""
        from app import db
        from models import SafetyIncident, Lesson, Student, User
        
        try:
            lesson = Lesson.query.get(lesson_id)
            if not lesson:
                logger.error(f"Lesson {lesson_id} not found for emergency")
                return False
            
            # Create safety incident
            incident = SafetyIncident()
            incident.lesson_id = lesson_id
            incident.instructor_id = lesson.instructor_id
            incident.student_id = lesson.student_id
            incident.incident_type = emergency_type
            incident.description = description
            incident.severity = EmergencyProtocol.EMERGENCY_TYPES[emergency_type]['severity']
            
            if location:
                incident.latitude, incident.longitude = location
                incident.address = EmergencyProtocol._get_address_from_coords(location)
            
            db.session.add(incident)
            db.session.flush()  # Get incident ID
            
            # Execute emergency protocol
            protocol = EmergencyProtocol.EMERGENCY_TYPES[emergency_type]
            for action in protocol['auto_actions']:
                EmergencyProtocol._execute_emergency_action(action, incident, lesson)
            
            # Update lesson status
            lesson.emergency_contact_notified = True
            
            db.session.commit()
            
            logger.critical(f"Emergency triggered: {emergency_type} for lesson {lesson_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error triggering emergency: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def _execute_emergency_action(action: str, incident, lesson):
        """Execute specific emergency action"""
        try:
            if action == 'call_emergency_services':
                EmergencyProtocol._call_emergency_services(incident)
            elif action == 'notify_contacts':
                EmergencyProtocol._notify_emergency_contacts(incident, lesson)
            elif action == 'alert_dispatch':
                EmergencyProtocol._alert_dispatch_center(incident)
            elif action == 'arrange_assistance':
                EmergencyProtocol._arrange_roadside_assistance(incident)
            elif action == 'notify_instructor':
                EmergencyProtocol._notify_instructor(incident, lesson)
            elif action == 'record_incident':
                EmergencyProtocol._record_detailed_incident(incident)
                
        except Exception as e:
            logger.error(f"Error executing emergency action {action}: {str(e)}")
    
    @staticmethod
    def _call_emergency_services(incident):
        """Call emergency services (911/local emergency number)"""
        # In real implementation, would integrate with emergency services API
        logger.critical(f"EMERGENCY SERVICES CALLED for incident {incident.id}")
        
        incident.emergency_services_called = True
        
        # Mock emergency call log
        call_log = {
            'incident_id': incident.id,
            'service': '911',
            'call_time': datetime.now().isoformat(),
            'location': f"{incident.latitude}, {incident.longitude}" if incident.latitude else "Unknown",
            'description': incident.description
        }
        
        # In production, would send to emergency dispatch system
        logger.critical(f"Emergency call log: {json.dumps(call_log)}")
    
    @staticmethod
    def _notify_emergency_contacts(incident, lesson):
        """Notify student and instructor emergency contacts"""
        from models import Student, User
        
        try:
            student = Student.query.get(lesson.student_id)
            instructor = User.query.get(lesson.instructor_id)
            
            contacts_to_notify = []
            
            # Student emergency contacts
            if student and student.emergency_contact:
                contacts_to_notify.append({
                    'name': student.emergency_contact_name or 'Emergency Contact',
                    'phone': student.emergency_contact,
                    'relation': 'Student Emergency Contact'
                })
            
            # Instructor emergency contacts
            if instructor and instructor.emergency_contact:
                contacts_to_notify.append({
                    'name': instructor.emergency_contact_name or 'Emergency Contact', 
                    'phone': instructor.emergency_contact,
                    'relation': 'Instructor Emergency Contact'
                })
            
            # Send notifications
            for contact in contacts_to_notify:
                EmergencyProtocol._send_emergency_notification(contact, incident)
            
            incident.emergency_contacts_notified = True
            logger.info(f"Emergency contacts notified for incident {incident.id}")
            
        except Exception as e:
            logger.error(f"Error notifying emergency contacts: {str(e)}")
    
    @staticmethod
    def _send_emergency_notification(contact: Dict, incident):
        """Send emergency notification to contact"""
        message = (
            f"🚨 EMERGENCY ALERT - DriveLink\n\n"
            f"Incident Type: {incident.incident_type.replace('_', ' ').title()}\n"
            f"Time: {incident.reported_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"Location: {incident.address or 'Location being determined'}\n"
            f"Severity: {incident.severity.upper()}\n\n"
            f"Emergency services have been contacted if required.\n"
            f"We will keep you updated on the situation.\n\n"
            f"For immediate assistance, call DriveLink Emergency: 1-800-DRIVE-911"
        )
        
        # In real implementation, would send SMS via Twilio
        logger.critical(f"Emergency SMS to {contact['name']} ({contact['phone']}): {message}")
    
    @staticmethod
    def _alert_dispatch_center(incident):
        """Alert DriveLink dispatch center"""
        dispatch_alert = {
            'incident_id': incident.id,
            'type': incident.incident_type,
            'severity': incident.severity,
            'location': {
                'lat': incident.latitude,
                'lng': incident.longitude,
                'address': incident.address
            },
            'time': incident.reported_at.isoformat(),
            'lesson_id': incident.lesson_id,
            'requires_immediate_response': incident.severity in ['critical', 'high']
        }
        
        # In production, would send to dispatch system
        logger.warning(f"Dispatch alert: {json.dumps(dispatch_alert)}")
    
    @staticmethod
    def _arrange_roadside_assistance(incident):
        """Arrange roadside assistance for vehicle issues"""
        assistance_request = {
            'incident_id': incident.id,
            'service_type': 'roadside_assistance',
            'location': incident.address or f"{incident.latitude}, {incident.longitude}",
            'description': incident.description,
            'priority': 'high' if incident.severity == 'high' else 'normal'
        }
        
        # In production, would integrate with roadside assistance service
        logger.info(f"Roadside assistance requested: {json.dumps(assistance_request)}")
    
    @staticmethod
    def _notify_instructor(incident, lesson):
        """Notify instructor of incident"""
        from models import User
        
        instructor = User.query.get(lesson.instructor_id)
        if instructor:
            message = (
                f"Safety Alert - Lesson {lesson.id}\n\n"
                f"Type: {incident.incident_type.replace('_', ' ').title()}\n"
                f"Description: {incident.description}\n"
                f"Time: {incident.reported_at.strftime('%H:%M')}\n\n"
                f"Please check on your student and report to DriveLink support."
            )
            
            # In real implementation, would send via WhatsApp/SMS
            logger.warning(f"Instructor notification for {instructor.name}: {message}")
    
    @staticmethod
    def _record_detailed_incident(incident):
        """Record detailed incident information"""
        incident_details = {
            'detailed_report': True,
            'requires_follow_up': True,
            'investigation_needed': incident.severity in ['high', 'critical'],
            'documented_at': datetime.now().isoformat()
        }
        
        # Store additional details
        logger.info(f"Detailed incident record created for incident {incident.id}")
    
    @staticmethod
    def _get_address_from_coords(location: Tuple[float, float]) -> str:
        """Get address from GPS coordinates"""
        # In real implementation, would use reverse geocoding API
        lat, lng = location
        return f"Location: {lat:.6f}, {lng:.6f}"

class PanicButtonSystem:
    """Panic button functionality and response"""
    
    @staticmethod
    def activate_panic_button(lesson_id: int, location: Tuple[float, float] = None) -> bool:
        """Activate panic button during lesson"""
        try:
            # Trigger emergency protocol
            success = EmergencyProtocol.trigger_emergency(
                lesson_id=lesson_id,
                emergency_type='panic_button',
                description='Panic button activated by student',
                location=location
            )
            
            if success:
                # Start enhanced tracking
                RealTimeTracker.enable_emergency_tracking(lesson_id)
                
                # Send immediate alerts
                PanicButtonSystem._send_immediate_alerts(lesson_id)
                
                logger.critical(f"PANIC BUTTON ACTIVATED for lesson {lesson_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error activating panic button: {str(e)}")
            return False
    
    @staticmethod
    def _send_immediate_alerts(lesson_id: int):
        """Send immediate alerts for panic button activation"""
        from models import Lesson
        
        lesson = Lesson.query.get(lesson_id)
        if not lesson:
            return
        
        # Priority alert to dispatch
        alert = {
            'type': 'PANIC_BUTTON_ACTIVATION',
            'lesson_id': lesson_id,
            'priority': 'CRITICAL',
            'timestamp': datetime.now().isoformat(),
            'requires_immediate_response': True
        }
        
        logger.critical(f"PANIC BUTTON ALERT: {json.dumps(alert)}")

class RealTimeTracker:
    """Real-time location and safety tracking"""
    
    @staticmethod
    def start_lesson_tracking(lesson_id: int) -> bool:
        """Start real-time tracking for lesson"""
        from app import db
        from models import LocationTracker, Lesson
        
        try:
            lesson = Lesson.query.get(lesson_id)
            if not lesson:
                return False
            
            # Create or update tracker
            tracker = LocationTracker.query.filter_by(lesson_id=lesson_id).first()
            if not tracker:
                tracker = LocationTracker()
                tracker.lesson_id = lesson_id
                tracker.instructor_id = lesson.instructor_id
                tracker.student_id = lesson.student_id
                db.session.add(tracker)
            
            tracker.tracking_status = 'active'
            tracker.latitude = 0.0  # Will be updated via GPS
            tracker.longitude = 0.0
            tracker.timestamp = datetime.now()
            
            # Enable lesson tracking
            lesson.lesson_tracking_active = True
            
            db.session.commit()
            logger.info(f"Started tracking for lesson {lesson_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting lesson tracking: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def update_location(lesson_id: int, latitude: float, longitude: float, 
                       speed: float = None, heading: float = None) -> bool:
        """Update real-time location during lesson"""
        from app import db
        from models import LocationTracker
        
        try:
            tracker = LocationTracker.query.filter_by(
                lesson_id=lesson_id,
                tracking_status='active'
            ).first()
            
            if not tracker:
                logger.warning(f"No active tracker found for lesson {lesson_id}")
                return False
            
            # Update location
            tracker.latitude = latitude
            tracker.longitude = longitude
            tracker.speed = speed
            tracker.heading = heading
            tracker.timestamp = datetime.now()
            
            # Check for safety concerns
            RealTimeTracker._check_safety_concerns(tracker)
            
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating location: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def _check_safety_concerns(tracker):
        """Check for safety concerns based on tracking data"""
        concerns = []
        
        # Speed concerns
        if tracker.speed and tracker.speed > 120:  # km/h
            concerns.append('excessive_speed')
        
        # Location concerns (simplified)
        # In real implementation, would check against safe driving areas
        
        # Time concerns
        lesson_duration = datetime.now() - tracker.timestamp
        if lesson_duration > timedelta(hours=3):
            concerns.append('extended_lesson_time')
        
        if concerns:
            logger.warning(f"Safety concerns for lesson {tracker.lesson_id}: {concerns}")
    
    @staticmethod
    def enable_emergency_tracking(lesson_id: int):
        """Enable enhanced tracking during emergency"""
        from app import db
        from models import LocationTracker
        
        try:
            tracker = LocationTracker.query.filter_by(lesson_id=lesson_id).first()
            if tracker:
                tracker.emergency_triggered = True
                tracker.tracking_status = 'emergency'
                db.session.commit()
                
                logger.critical(f"Emergency tracking enabled for lesson {lesson_id}")
        
        except Exception as e:
            logger.error(f"Error enabling emergency tracking: {str(e)}")
    
    @staticmethod
    def stop_lesson_tracking(lesson_id: int):
        """Stop tracking when lesson ends"""
        from app import db
        from models import LocationTracker, Lesson
        
        try:
            tracker = LocationTracker.query.filter_by(lesson_id=lesson_id).first()
            if tracker:
                tracker.tracking_status = 'ended'
                tracker.timestamp = datetime.now()
            
            lesson = Lesson.query.get(lesson_id)
            if lesson:
                lesson.lesson_tracking_active = False
            
            db.session.commit()
            logger.info(f"Stopped tracking for lesson {lesson_id}")
            
        except Exception as e:
            logger.error(f"Error stopping lesson tracking: {str(e)}")

class SafetyReporting:
    """Safety reporting and analytics"""
    
    @staticmethod
    def generate_safety_report(instructor_id: int = None, 
                             date_range: Tuple[datetime, datetime] = None) -> Dict:
        """Generate comprehensive safety report"""
        from models import SafetyIncident, Lesson, User
        
        try:
            query = SafetyIncident.query
            
            if instructor_id:
                query = query.filter_by(instructor_id=instructor_id)
            
            if date_range:
                start_date, end_date = date_range
                query = query.filter(
                    SafetyIncident.reported_at >= start_date,
                    SafetyIncident.reported_at <= end_date
                )
            
            incidents = query.all()
            
            # Calculate statistics
            total_incidents = len(incidents)
            critical_incidents = len([i for i in incidents if i.severity == 'critical'])
            resolved_incidents = len([i for i in incidents if i.resolved])
            
            # Incident breakdown by type
            incident_types = {}
            for incident in incidents:
                incident_types[incident.incident_type] = incident_types.get(incident.incident_type, 0) + 1
            
            # Response time analysis
            response_times = []
            for incident in incidents:
                if incident.resolved_at:
                    response_time = (incident.resolved_at - incident.reported_at).total_seconds() / 60
                    response_times.append(response_time)
            
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            return {
                'total_incidents': total_incidents,
                'critical_incidents': critical_incidents,
                'resolved_incidents': resolved_incidents,
                'resolution_rate': resolved_incidents / total_incidents if total_incidents > 0 else 100,
                'incident_types': incident_types,
                'avg_response_time_minutes': avg_response_time,
                'safety_score': SafetyReporting._calculate_safety_score(incidents),
                'recommendations': SafetyReporting._generate_recommendations(incidents)
            }
            
        except Exception as e:
            logger.error(f"Error generating safety report: {str(e)}")
            return {}
    
    @staticmethod
    def _calculate_safety_score(incidents: List) -> int:
        """Calculate overall safety score (0-100)"""
        if not incidents:
            return 100
        
        # Base score
        base_score = 100
        
        # Deductions based on incident severity
        for incident in incidents:
            if incident.severity == 'critical':
                base_score -= 20
            elif incident.severity == 'high':
                base_score -= 10
            elif incident.severity == 'medium':
                base_score -= 5
            else:
                base_score -= 2
        
        return max(0, base_score)
    
    @staticmethod
    def _generate_recommendations(incidents: List) -> List[str]:
        """Generate safety recommendations based on incident patterns"""
        recommendations = []
        
        # Analyze incident patterns
        incident_types = {}
        for incident in incidents:
            incident_types[incident.incident_type] = incident_types.get(incident.incident_type, 0) + 1
        
        # Generate targeted recommendations
        if incident_types.get('panic_button', 0) > 2:
            recommendations.append("Consider additional safety training for instructors")
        
        if incident_types.get('vehicle_breakdown', 0) > 1:
            recommendations.append("Implement more frequent vehicle maintenance checks")
        
        if incident_types.get('accident', 0) > 0:
            recommendations.append("Review driving routes and avoid high-risk areas")
        
        if not recommendations:
            recommendations.append("Maintain current safety protocols - good safety record")
        
        return recommendations

# Global safety system instance
safety_system = {
    'emergency': EmergencyProtocol(),
    'panic_button': PanicButtonSystem(),
    'tracker': RealTimeTracker(),
    'reporting': SafetyReporting()
}