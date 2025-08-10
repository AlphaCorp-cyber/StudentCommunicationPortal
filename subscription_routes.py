"""
Subscription Routes for DriveLink
Handles subscription management, billing, and marketplace features
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import json
from app import db
from models import (
    User, Student, InstructorSubscription, SubscriptionPlan, CommissionRecord,
    MarketplaceBooking, InstructorReview, SUBSCRIPTION_ACTIVE
)
from subscription_manager import SubscriptionManager, MarketplaceManager
from auth import require_role

# Create blueprint for subscription routes
subscription_bp = Blueprint('subscription', __name__, url_prefix='/subscription')

@subscription_bp.route('/plans')
def subscription_plans():
    """Display available subscription plans"""
    plans = SubscriptionPlan.query.filter_by(is_active=True).all()
    return render_template('subscription_plans.html', plans=plans)

@subscription_bp.route('/dashboard')
@login_required
@require_role('instructor')
def subscription_dashboard():
    """Instructor subscription dashboard"""
    instructor = current_user
    
    # Get current subscription
    current_subscription = InstructorSubscription.query.filter_by(
        instructor_id=instructor.id,
        status=SUBSCRIPTION_ACTIVE
    ).first()
    
    # Get analytics
    analytics = SubscriptionManager.get_instructor_analytics(instructor.id)
    
    # Get recent commission records
    recent_commissions = CommissionRecord.query.filter_by(
        instructor_id=instructor.id
    ).order_by(CommissionRecord.created_at.desc()).limit(10).all()
    
    # Get subscription history
    subscription_history = InstructorSubscription.query.filter_by(
        instructor_id=instructor.id
    ).order_by(InstructorSubscription.created_at.desc()).all()
    
    return render_template('subscription_dashboard.html',
                         subscription=current_subscription,
                         analytics=analytics,
                         recent_commissions=recent_commissions,
                         subscription_history=subscription_history)

@subscription_bp.route('/upgrade', methods=['GET', 'POST'])
@login_required
@require_role('instructor')
def upgrade_subscription():
    """Handle subscription upgrades"""
    if request.method == 'POST':
        plan_code = request.form.get('plan')
        payment_method = request.form.get('payment_method')
        
        subscription, message = SubscriptionManager.create_subscription(
            current_user, plan_code, payment_method
        )
        
        if subscription:
            flash('Subscription upgraded successfully!', 'success')
            return redirect(url_for('subscription.subscription_dashboard'))
        else:
            flash(f'Upgrade failed: {message}', 'error')
    
    plans = SubscriptionPlan.query.filter_by(is_active=True).all()
    return render_template('subscription_upgrade.html', plans=plans)

@subscription_bp.route('/marketplace')
def marketplace():
    """Public marketplace for students to find instructors"""
    # Get available instructors
    instructors = User.query.filter(
        User.role == 'instructor',
        User.is_verified == True,
        User.subscription_status == SUBSCRIPTION_ACTIVE
    ).all()
    
    # Add additional info to each instructor
    for instructor in instructors:
        instructor.student_count = len(instructor.instructor_students)
        instructor.reviews_count = len(instructor.reviews)
        instructor.can_accept_students = instructor.can_take_students()
    
    return render_template('marketplace.html', instructors=instructors)

@subscription_bp.route('/marketplace/book', methods=['POST'])
def marketplace_book():
    """Handle marketplace booking requests"""
    data = request.get_json()
    
    # For now, return success without authentication
    # In production, you'd want to handle student registration/login
    booking_data = {
        'location': data.get('location'),
        'lesson_type': data.get('lesson_type'),
        'duration': data.get('duration'),
        'date': datetime.strptime(data.get('date'), '%Y-%m-%d').date(),
        'time': datetime.strptime(data.get('time'), '%H:%M').time(),
        'max_price': data.get('max_price'),
        'notes': data.get('notes')
    }
    
    # Find available instructors
    instructors = MarketplaceManager.find_nearby_instructors(
        data.get('location'), 
        radius_km=data.get('radius', 10),
        lesson_type=data.get('lesson_type')
    )
    
    return jsonify({
        'success': True,
        'message': f'Found {len(instructors)} available instructors',
        'instructors': [
            {
                'id': inst.id,
                'name': inst.get_full_name(),
                'rating': inst.average_rating,
                'hourly_rate_60min': float(inst.hourly_rate_60min or 0),
                'bio': inst.bio,
                'experience_years': inst.experience_years
            } for inst in instructors
        ]
    })

@subscription_bp.route('/instructor/<int:instructor_id>')
def instructor_profile(instructor_id):
    """Display instructor profile"""
    instructor = User.query.get_or_404(instructor_id)
    
    if instructor.role != 'instructor':
        flash('Invalid instructor profile', 'error')
        return redirect(url_for('subscription.marketplace'))
    
    # Get instructor reviews
    reviews = InstructorReview.query.filter_by(
        instructor_id=instructor_id
    ).order_by(InstructorReview.created_at.desc()).limit(10).all()
    
    return render_template('instructor_profile.html', 
                         instructor=instructor, 
                         reviews=reviews)

@subscription_bp.route('/admin/subscriptions')
@login_required
@require_role('admin')
def admin_subscriptions():
    """Admin view of all subscriptions"""
    subscriptions = InstructorSubscription.query.order_by(
        InstructorSubscription.created_at.desc()
    ).all()
    
    # Calculate revenue metrics
    total_revenue = sum(sub.amount for sub in subscriptions if sub.payment_status == 'completed')
    active_subscriptions = len([sub for sub in subscriptions if sub.status == SUBSCRIPTION_ACTIVE])
    
    return render_template('admin_subscriptions.html',
                         subscriptions=subscriptions,
                         total_revenue=total_revenue,
                         active_subscriptions=active_subscriptions)

@subscription_bp.route('/admin/commission-reports')
@login_required
@require_role('admin')
def commission_reports():
    """Admin commission reports and analytics"""
    from sqlalchemy import func
    
    # Get commission summary
    commission_data = db.session.query(
        func.sum(CommissionRecord.commission_amount).label('total_commission'),
        func.sum(CommissionRecord.instructor_earning).label('total_instructor_earnings'),
        func.count(CommissionRecord.id).label('total_lessons')
    ).first()
    
    # Monthly breakdown
    monthly_commissions = db.session.query(
        func.extract('month', CommissionRecord.created_at).label('month'),
        func.extract('year', CommissionRecord.created_at).label('year'),
        func.sum(CommissionRecord.commission_amount).label('commission'),
        func.count(CommissionRecord.id).label('lessons')
    ).group_by(
        func.extract('month', CommissionRecord.created_at),
        func.extract('year', CommissionRecord.created_at)
    ).order_by('year', 'month').all()
    
    # Top earning instructors
    top_instructors = db.session.query(
        User.id,
        User.first_name,
        User.last_name,
        func.sum(CommissionRecord.instructor_earning).label('total_earnings'),
        func.count(CommissionRecord.id).label('total_lessons')
    ).join(CommissionRecord).group_by(
        User.id, User.first_name, User.last_name
    ).order_by('total_earnings desc').limit(10).all()
    
    return render_template('commission_reports.html',
                         commission_data=commission_data,
                         monthly_commissions=monthly_commissions,
                         top_instructors=top_instructors)

@subscription_bp.route('/api/instructor-stats/<int:instructor_id>')
@login_required
def instructor_stats_api(instructor_id):
    """API endpoint for instructor statistics"""
    if current_user.id != instructor_id and not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    
    analytics = SubscriptionManager.get_instructor_analytics(instructor_id)
    return jsonify(analytics)