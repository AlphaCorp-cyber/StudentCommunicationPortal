"""
Instructor Onboarding Routes for DriveLink
Handles new instructor registration and verification process
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date
import json
import os
from app import db
from models import User, SubscriptionPlan, SUBSCRIPTION_ACTIVE
from subscription_manager import SubscriptionManager
from auth import require_role

# Create blueprint for onboarding routes
onboarding_bp = Blueprint('onboarding', __name__, url_prefix='/onboarding')

@onboarding_bp.route('/instructor')
@onboarding_bp.route('/instructor/<int:step>')
@login_required
@require_role('instructor')
def instructor_onboarding(step=1):
    """Multi-step instructor onboarding process"""
    
    # Check if instructor is already verified
    if current_user.is_verified:
        flash('You have already completed the onboarding process.', 'info')
        return redirect(url_for('subscription.subscription_dashboard'))
    
    # Validate step
    if step < 1 or step > 4:
        step = 1
    
    # Get subscription plans for step 4
    plans = SubscriptionPlan.query.filter_by(is_active=True).all()
    
    return render_template('instructor_onboarding.html', step=step, plans=plans)

@onboarding_bp.route('/instructor/<int:step>', methods=['POST'])
@login_required
@require_role('instructor')
def instructor_onboarding_post(step):
    """Handle onboarding form submissions"""
    
    if current_user.is_verified:
        flash('You have already completed the onboarding process.', 'info')
        return redirect(url_for('subscription.subscription_dashboard'))
    
    try:
        if step == 1:
            # Step 1: Personal Information
            current_user.first_name = request.form.get('first_name', '').strip()
            current_user.last_name = request.form.get('last_name', '').strip()
            current_user.phone = request.form.get('phone', '').strip()
            current_user.bio = request.form.get('bio', '').strip()
            current_user.experience_years = int(request.form.get('experience_years', 0))
            
            db.session.commit()
            flash('Personal information saved successfully!', 'success')
            return redirect(url_for('onboarding.instructor_onboarding', step=2))
            
        elif step == 2:
            # Step 2: Licenses & Certification
            current_user.license_number = request.form.get('license_number', '').strip()
            license_expiry_str = request.form.get('license_expiry', '')
            if license_expiry_str:
                current_user.license_expiry = datetime.strptime(license_expiry_str, '%Y-%m-%d').date()
            
            # Handle file upload for license document
            license_file = request.files.get('license_document')
            if license_file and license_file.filename:
                # In a real implementation, you would save this to cloud storage
                # For now, we'll just mark that a document was uploaded
                documents = []
                if current_user.certification_documents:
                    try:
                        documents = json.loads(current_user.certification_documents)
                    except:
                        documents = []
                
                documents.append({
                    'type': 'license',
                    'filename': license_file.filename,
                    'uploaded_at': datetime.now().isoformat()
                })
                current_user.certification_documents = json.dumps(documents)
            
            db.session.commit()
            flash('License information saved successfully!', 'success')
            return redirect(url_for('onboarding.instructor_onboarding', step=3))
            
        elif step == 3:
            # Step 3: Vehicle & Service Areas
            current_user.vehicle_owned = bool(request.form.get('vehicle_owned'))
            current_user.base_location = request.form.get('base_location', '').strip()
            current_user.service_areas = request.form.get('service_areas', '').strip()
            
            # Pricing
            current_user.hourly_rate_30min = float(request.form.get('hourly_rate_30min', 25))
            current_user.hourly_rate_60min = float(request.form.get('hourly_rate_60min', 40))
            
            db.session.commit()
            flash('Vehicle and service information saved successfully!', 'success')
            return redirect(url_for('onboarding.instructor_onboarding', step=4))
            
        elif step == 4:
            # Step 4: Subscription Plan
            subscription_plan = request.form.get('subscription_plan', 'basic')
            
            # Create subscription
            subscription, message = SubscriptionManager.create_subscription(
                current_user, subscription_plan
            )
            
            if subscription:
                # Mark instructor as verified (in a real app, this would require admin approval)
                current_user.is_verified = True
                db.session.commit()
                
                flash('Congratulations! Your instructor account has been set up successfully!', 'success')
                flash('You can now start accepting students and teaching lessons.', 'info')
                return redirect(url_for('subscription.subscription_dashboard'))
            else:
                flash(f'Subscription setup failed: {message}', 'error')
                return redirect(url_for('onboarding.instructor_onboarding', step=4))
                
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('onboarding.instructor_onboarding', step=step))

@onboarding_bp.route('/welcome')
@login_required
@require_role('instructor')
def welcome():
    """Welcome page after successful onboarding"""
    if not current_user.is_verified:
        return redirect(url_for('onboarding.instructor_onboarding'))
    
    return render_template('onboarding_welcome.html')

@onboarding_bp.route('/status')
@login_required
@require_role('instructor')
def onboarding_status():
    """Check onboarding completion status"""
    status = {
        'personal_info_complete': bool(current_user.first_name and current_user.last_name and current_user.phone),
        'license_info_complete': bool(current_user.license_number and current_user.license_expiry),
        'service_info_complete': bool(current_user.base_location and current_user.hourly_rate_30min),
        'subscription_active': current_user.subscription_status == SUBSCRIPTION_ACTIVE,
        'is_verified': current_user.is_verified
    }
    
    # Calculate completion percentage
    completed_steps = sum(1 for v in status.values() if v)
    completion_percentage = (completed_steps / len(status)) * 100
    
    status['completion_percentage'] = completion_percentage
    status['next_step'] = get_next_onboarding_step(status)
    
    return status

def get_next_onboarding_step(status):
    """Determine the next step in onboarding"""
    if not status['personal_info_complete']:
        return 1
    elif not status['license_info_complete']:
        return 2
    elif not status['service_info_complete']:
        return 3
    elif not status['subscription_active']:
        return 4
    else:
        return None  # Onboarding complete