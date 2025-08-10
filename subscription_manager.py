"""
Subscription Management Service for DriveLink
Handles instructor subscriptions, payments, and commission tracking
"""
import os
import stripe
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func
from app import db
from models import (
    User, InstructorSubscription, CommissionRecord, SubscriptionPlan, 
    InstructorPayout, SUBSCRIPTION_ACTIVE, SUBSCRIPTION_EXPIRED,
    PAYMENT_COMPLETED, PAYMENT_FAILED, SUBSCRIPTION_CANCELLED
)

# Configure Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

class SubscriptionManager:
    """Service for managing instructor subscriptions"""
    
    @staticmethod
    def create_subscription_plans():
        """Initialize default subscription plans"""
        plans = [
            {
                'name': 'Basic Plan',
                'code': 'basic',
                'monthly_price': 29.00,
                'yearly_price': 290.00,
                'student_limit': 10,
                'commission_rate': 0.15,
                'priority_support': False,
                'analytics_access': False,
                'custom_branding': False,
                'description': 'Perfect for new instructors getting started',
                'features': ['Up to 10 students', '15% commission rate', 'Basic support', 'WhatsApp integration']
            },
            {
                'name': 'Premium Plan',
                'code': 'premium',
                'monthly_price': 49.00,
                'yearly_price': 490.00,
                'student_limit': 25,
                'commission_rate': 0.12,
                'priority_support': True,
                'analytics_access': True,
                'custom_branding': False,
                'description': 'Best for growing driving schools',
                'features': ['Up to 25 students', '12% commission rate', 'Priority support', 'Analytics dashboard', 'Advanced reporting']
            },
            {
                'name': 'Pro Plan',
                'code': 'pro',
                'monthly_price': 99.00,
                'yearly_price': 990.00,
                'student_limit': None,
                'commission_rate': 0.08,
                'priority_support': True,
                'analytics_access': True,
                'custom_branding': True,
                'description': 'For established driving schools',
                'features': ['Unlimited students', '8% commission rate', 'VIP support', 'Full analytics suite', 'Custom branding', 'API access']
            }
        ]
        
        for plan_data in plans:
            existing = SubscriptionPlan.query.filter_by(code=plan_data['code']).first()
            if not existing:
                plan = SubscriptionPlan()
                for key, value in plan_data.items():
                    if key == 'features':
                        import json
                        plan.features = json.dumps(value)
                    else:
                        setattr(plan, key, value)
                db.session.add(plan)
        
        db.session.commit()
    
    @staticmethod
    def create_stripe_customer(user):
        """Create a Stripe customer for the instructor"""
        try:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.get_full_name(),
                metadata={
                    'user_id': user.id,
                    'role': 'instructor'
                }
            )
            return customer.id
        except stripe.error.StripeError as e:
            print(f"Stripe error creating customer: {e}")
            return None
    
    @staticmethod
    def create_subscription(user, plan_code, payment_method_id=None):
        """Create a new subscription for an instructor"""
        plan = SubscriptionPlan.query.filter_by(code=plan_code, is_active=True).first()
        if not plan:
            return None, "Invalid subscription plan"
        
        try:
            # Create or get Stripe customer
            if not hasattr(user, 'stripe_customer_id') or not user.stripe_customer_id:
                customer_id = SubscriptionManager.create_stripe_customer(user)
                if not customer_id:
                    return None, "Failed to create payment customer"
                # You would save this to user model in a real implementation
            
            # Create subscription period
            start_date = datetime.now()
            end_date = start_date + timedelta(days=30)
            
            # Create subscription record
            subscription = InstructorSubscription()
            subscription.instructor_id = user.id
            subscription.plan = plan_code
            subscription.start_date = start_date
            subscription.end_date = end_date
            subscription.amount = plan.monthly_price
            subscription.payment_status = PAYMENT_COMPLETED
            subscription.auto_renew = True
            
            db.session.add(subscription)
            
            # Update user subscription fields
            user.subscription_plan = plan_code
            user.subscription_status = SUBSCRIPTION_ACTIVE
            user.subscription_start_date = start_date
            user.subscription_end_date = end_date
            
            db.session.commit()
            
            return subscription, "Subscription created successfully"
            
        except Exception as e:
            db.session.rollback()
            return None, f"Failed to create subscription: {str(e)}"
    
    @staticmethod
    def process_lesson_commission(lesson, instructor, student):
        """Process commission for a completed lesson"""
        if lesson.status != 'completed':
            return None
        
        # Get lesson price
        lesson_price = Decimal(lesson.duration_minutes * 0.5)  # Example pricing
        commission_rate = instructor.get_commission_rate()
        commission_amount = lesson_price * Decimal(commission_rate)
        instructor_earning = lesson_price - commission_amount
        
        # Create commission record
        commission = CommissionRecord()
        commission.instructor_id = instructor.id
        commission.lesson_id = lesson.id
        commission.lesson_amount = lesson_price
        commission.commission_rate = commission_rate
        commission.commission_amount = commission_amount
        commission.instructor_earning = instructor_earning
        
        db.session.add(commission)
        
        # Update instructor totals
        instructor.total_earnings += instructor_earning
        instructor.commission_paid += commission_amount
        instructor.total_lessons_taught += 1
        
        db.session.commit()
        return commission
    
    @staticmethod
    def check_subscription_expiry():
        """Check for expired subscriptions and update status"""
        expired_subscriptions = InstructorSubscription.query.filter(
            InstructorSubscription.end_date < datetime.now(),
            InstructorSubscription.status == SUBSCRIPTION_ACTIVE
        ).all()
        
        for subscription in expired_subscriptions:
            if subscription.auto_renew:
                # Try to renew
                success = SubscriptionManager.renew_subscription(subscription)
                if not success:
                    SubscriptionManager.expire_subscription(subscription)
            else:
                SubscriptionManager.expire_subscription(subscription)
    
    @staticmethod
    def expire_subscription(subscription):
        """Mark subscription as expired"""
        subscription.status = SUBSCRIPTION_EXPIRED
        
        # Update user
        user = User.query.get(subscription.instructor_id)
        user.subscription_status = SUBSCRIPTION_EXPIRED
        
        db.session.commit()
    
    @staticmethod
    def renew_subscription(subscription):
        """Attempt to renew a subscription"""
        try:
            # Create new billing period
            new_start = subscription.end_date
            new_end = new_start + timedelta(days=30)
            
            # Create new subscription record
            new_subscription = InstructorSubscription()
            new_subscription.instructor_id = subscription.instructor_id
            new_subscription.plan = subscription.plan
            new_subscription.start_date = new_start
            new_subscription.end_date = new_end
            new_subscription.amount = subscription.amount
            new_subscription.payment_status = PAYMENT_COMPLETED
            new_subscription.auto_renew = subscription.auto_renew
            
            db.session.add(new_subscription)
            
            # Update user
            user = User.query.get(subscription.instructor_id)
            user.subscription_end_date = new_end
            
            db.session.commit()
            return True
            
        except Exception as e:
            print(f"Failed to renew subscription: {e}")
            return False
    
    @staticmethod
    def get_instructor_analytics(instructor_id):
        """Get analytics for an instructor"""
        instructor = User.query.get(instructor_id)
        if not instructor:
            return None
        
        # Calculate monthly earnings
        current_month = datetime.now().replace(day=1)
        monthly_commissions = db.session.query(func.sum(CommissionRecord.instructor_earning)).filter(
            CommissionRecord.instructor_id == instructor_id,
            CommissionRecord.created_at >= current_month
        ).scalar() or 0
        
        # Student count
        student_count = len(instructor.instructor_students)
        
        # Monthly lessons
        monthly_lessons = db.session.query(func.count(CommissionRecord.id)).filter(
            CommissionRecord.instructor_id == instructor_id,
            CommissionRecord.created_at >= current_month
        ).scalar() or 0
        
        return {
            'monthly_earnings': float(monthly_commissions),
            'total_earnings': float(instructor.total_earnings),
            'student_count': student_count,
            'monthly_lessons': monthly_lessons,
            'average_rating': instructor.average_rating,
            'total_lessons': instructor.total_lessons_taught
        }

class MarketplaceManager:
    """Service for managing marketplace bookings and instructor matching"""
    
    @staticmethod
    def find_nearby_instructors(location, radius_km=10, lesson_type='Class 4'):
        """Find instructors near a location"""
        # This would use geospatial queries in a real implementation
        instructors = User.query.filter(
            User.role == 'instructor',
            User.is_verified == True,
            User.subscription_status == SUBSCRIPTION_ACTIVE
        ).all()
        
        # Filter by availability and subscription limits
        available_instructors = []
        for instructor in instructors:
            if instructor.can_take_students():
                available_instructors.append(instructor)
        
        return available_instructors
    
    @staticmethod
    def create_marketplace_booking(student, booking_data):
        """Create a new marketplace booking request"""
        from models import MarketplaceBooking
        from datetime import date, time
        
        booking = MarketplaceBooking()
        booking.student_id = student.id
        booking.preferred_location = booking_data.get('location')
        booking.lesson_type = booking_data.get('lesson_type', 'Class 4')
        booking.duration_minutes = booking_data.get('duration', 60)
        booking.preferred_date = booking_data.get('date', date.today())
        booking.preferred_time = booking_data.get('time', time(9, 0))
        booking.max_price = booking_data.get('max_price')
        booking.special_notes = booking_data.get('notes')
        booking.expires_at = datetime.now() + timedelta(hours=24)
        
        db.session.add(booking)
        db.session.commit()
        
        return booking