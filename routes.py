from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import current_user, login_user, logout_user
from sqlalchemy import or_, and_

from app import app, db
from models import User, Student, Lesson, WhatsAppSession, SystemConfig, Vehicle, Payment, LessonPricing, LESSON_SCHEDULED, LESSON_COMPLETED, LESSON_CANCELLED, ROLE_INSTRUCTOR, ROLE_ADMIN, ROLE_SUPER_ADMIN
from auth import require_login, require_role
# WhatsApp functionality will be imported when needed

# WhatsApp bot initialization - moved to app context block in app.py

# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.active:
            remember_me = bool(request.form.get('remember'))
            login_user(user, remember=remember_me)
            next_page = session.pop('next_url', None)
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@require_login
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        first_name = request.form.get('first_name', '')
        last_name = request.form.get('last_name', '')
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return render_template('register.html')
        
        # Create new user
        user = User()
        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.role = ROLE_INSTRUCTOR
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/dashboard')
@require_login
def dashboard():
    """Main dashboard that routes to role-specific dashboards"""
    if current_user.is_super_admin():
        return redirect(url_for('super_admin_dashboard'))
    elif current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('instructor_dashboard'))

@app.route('/instructor')
@require_login
def instructor_dashboard():
    """Instructor dashboard showing assigned students and lessons"""
    if not current_user.is_instructor() and not current_user.is_admin() and not current_user.is_super_admin():
        flash('Access denied. Instructor privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Get instructor's students
    students = Student.query.filter_by(instructor_id=current_user.id, is_active=True).all()
    
    # Get upcoming lessons for this instructor
    upcoming_lessons = Lesson.query.filter(
        and_(
            Lesson.instructor_id == current_user.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.now()
        )
    ).order_by(Lesson.scheduled_date).limit(10).all()
    
    # Get recent completed lessons
    recent_lessons = Lesson.query.filter(
        and_(
            Lesson.instructor_id == current_user.id,
            Lesson.status == LESSON_COMPLETED
        )
    ).order_by(Lesson.completed_date.desc()).limit(5).all()
    
    stats = {
        'total_students': len(students),
        'upcoming_lessons': len(upcoming_lessons),
        'completed_today': Lesson.query.filter(
            and_(
                Lesson.instructor_id == current_user.id,
                Lesson.status == LESSON_COMPLETED,
                Lesson.completed_date >= datetime.now().date()
            )
        ).count()
    }
    
    return render_template('instructor_dashboard.html', 
                         students=students, 
                         upcoming_lessons=upcoming_lessons,
                         recent_lessons=recent_lessons,
                         stats=stats)

@app.route('/admin')
@require_role('admin')
def admin_dashboard():
    """Admin dashboard for managing school operations"""
    # Get all students
    students = Student.query.filter_by(is_active=True).all()
    
    # Get all instructors with vehicle assignments
    instructors = User.query.filter_by(role='instructor').all()
    for instructor in instructors:
        instructor.assigned_vehicles = Vehicle.query.filter_by(instructor_id=instructor.id, is_active=True).all()
    
    # Get vehicles
    vehicles = Vehicle.query.filter_by(is_active=True).all()
    
    # Get recent payments
    recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(5).all()
    
    # Get today's lessons
    today_lessons = Lesson.query.filter(
        Lesson.scheduled_date >= datetime.now().date(),
        Lesson.scheduled_date < datetime.now().date() + timedelta(days=1)
    ).all()
    
    # Get pending lessons
    pending_lessons = Lesson.query.filter_by(status=LESSON_SCHEDULED).count()
    
    stats = {
        'total_students': len(students),
        'total_instructors': len(instructors),
        'todays_lessons': len(today_lessons),
        'pending_lessons': pending_lessons,
        'completed_lessons': Lesson.query.filter_by(status=LESSON_COMPLETED).count()
    }
    
    return render_template('admin_dashboard.html', 
                         students=students[:10],  # Show first 10
                         instructors=instructors,
                         vehicles=vehicles,
                         recent_payments=recent_payments,
                         today_lessons=today_lessons,
                         stats=stats)

@app.route('/super-admin')
@require_role('super_admin')
def super_admin_dashboard():
    """Super Admin dashboard for system configuration"""
    # Get all users
    all_users = User.query.all()
    
    # Get system statistics
    stats = {
        'total_users': len(all_users),
        'instructors': len([u for u in all_users if u.is_instructor()]),
        'admins': len([u for u in all_users if u.is_admin()]),
        'super_admins': len([u for u in all_users if u.is_super_admin()]),
        'total_students': Student.query.count(),
        'total_lessons': Lesson.query.count(),
        'active_whatsapp_sessions': WhatsAppSession.query.filter_by(is_active=True).count()
    }
    
    # Get system configurations
    configs = SystemConfig.query.all()
    
    return render_template('super_admin_dashboard.html', 
                         users=all_users,
                         stats=stats,
                         configs=configs)

@app.route('/students')
@require_login
def students():
    """Student management page"""
    if current_user.is_instructor():
        # Instructors can only see their assigned students
        students_list = Student.query.filter_by(instructor_id=current_user.id, is_active=True).all()
    else:
        # Admins and Super Admins can see all students
        students_list = Student.query.filter_by(is_active=True).all()
    
    instructors = User.query.filter_by(role='instructor').all() if not current_user.is_instructor() else []
    
    return render_template('students.html', students=students_list, instructors=instructors)

@app.route('/students/add', methods=['POST'])
@require_role('admin')
def add_student():
    """Add a new student"""
    try:
        instructor_id = request.form.get('instructor_id')
        if not instructor_id:
            flash('Instructor assignment is required.', 'error')
            return redirect(url_for('students'))
        
        student = Student()
        student.name = request.form['name']
        student.phone = request.form['phone']
        student.email = request.form.get('email')
        student.address = request.form.get('address')
        student.license_type = request.form.get('license_type', 'Class 4')
        student.instructor_id = int(instructor_id)
        student.total_lessons_required = int(request.form.get('total_lessons_required', 20))
        
        db.session.add(student)
        db.session.commit()
        flash(f'Student {student.name} added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding student: {str(e)}', 'error')
    
    return redirect(url_for('students'))

@app.route('/students/<int:student_id>/assign', methods=['POST'])
@require_role('admin')
def assign_instructor(student_id):
    """Assign an instructor to a student"""
    student = Student.query.get_or_404(student_id)
    instructor_id = request.form.get('instructor_id')
    
    if instructor_id:
        instructor = User.query.get(instructor_id)
        if instructor and instructor.is_instructor():
            student.instructor_id = instructor_id
            db.session.commit()
            flash(f'Instructor assigned to {student.name} successfully!', 'success')
        else:
            flash('Invalid instructor selected.', 'error')
    else:
        student.instructor_id = None
        db.session.commit()
        flash(f'Instructor unassigned from {student.name}.', 'info')
    
    return redirect(url_for('students'))

@app.route('/lessons')
@require_login
def lessons():
    """Lesson management page"""
    if current_user.is_instructor():
        # Instructors see only their lessons
        lessons_list = Lesson.query.filter_by(instructor_id=current_user.id).order_by(Lesson.scheduled_date.desc()).all()
        # Get instructor's assigned vehicles
        current_user.assigned_vehicles = Vehicle.query.filter_by(instructor_id=current_user.id, is_active=True).all()
    else:
        # Admins and Super Admins see all lessons
        lessons_list = Lesson.query.order_by(Lesson.scheduled_date.desc()).all()
    
    # Get students for lesson booking (based on user role)
    if current_user.is_instructor():
        students_list = Student.query.filter_by(instructor_id=current_user.id, is_active=True).all()
    else:
        students_list = Student.query.filter_by(is_active=True).all()
    
    # Get all vehicles for admins
    vehicles = Vehicle.query.filter_by(is_active=True).all() if not current_user.is_instructor() else []
    
    return render_template('lessons.html', lessons=lessons_list, students=students_list, vehicles=vehicles)

@app.route('/api/check_lesson_limit')
@require_login
def check_lesson_limit():
    """Check if student has reached daily lesson limit"""
    student_id = request.args.get('student_id')
    date_str = request.args.get('date')
    
    if not student_id or not date_str:
        return jsonify({'error': 'Missing parameters'}), 400
    
    try:
        lesson_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Count lessons for this student on this date
        lesson_count = Lesson.query.filter(
            and_(
                Lesson.student_id == student_id,
                Lesson.scheduled_date >= datetime.combine(lesson_date, datetime.min.time()),
                Lesson.scheduled_date < datetime.combine(lesson_date, datetime.min.time()) + timedelta(days=1),
                Lesson.status != LESSON_CANCELLED
            )
        ).count()
        
        return jsonify({'lesson_count': lesson_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lessons/add', methods=['POST'])
@require_login
def add_lesson():
    """Add a new lesson with validation for time constraints and balance checking"""
    try:
        student_id = request.form['student_id']
        student = Student.query.get(student_id)
        
        # Verify instructor can schedule for this student
        if current_user.is_instructor() and student.instructor_id != current_user.id:
            flash('You can only schedule lessons for your assigned students.', 'error')
            return redirect(url_for('lessons'))
        
        scheduled_date = datetime.strptime(request.form['scheduled_date'], '%Y-%m-%dT%H:%M')
        duration_minutes = int(request.form.get('duration_minutes', 30))
        
        # Check if student has sufficient balance
        if not student.has_sufficient_balance(duration_minutes):
            lesson_price = student.get_lesson_price(duration_minutes)
            flash(f'Student has insufficient balance. Lesson costs ${lesson_price:.2f}, current balance: ${student.account_balance:.2f}', 'error')
            return redirect(url_for('lessons'))
        
        # Validate time constraints (6 AM to 4 PM)
        if scheduled_date.hour < 6 or scheduled_date.hour >= 16:
            flash('Lessons can only be scheduled between 6:00 AM and 4:00 PM', 'error')
            return redirect(url_for('lessons'))
        
        # Validate 30-minute intervals
        if scheduled_date.minute not in [0, 30]:
            flash('Lessons must start at :00 or :30 minutes', 'error')
            return redirect(url_for('lessons'))
        
        # Validate not in the past
        if scheduled_date <= datetime.now():
            flash('Cannot schedule lessons in the past', 'error')
            return redirect(url_for('lessons'))
        
        # Check daily lesson limit (max 2 per day)
        lesson_date = scheduled_date.date()
        existing_lessons = Lesson.query.filter(
            and_(
                Lesson.student_id == student_id,
                Lesson.scheduled_date >= datetime.combine(lesson_date, datetime.min.time()),
                Lesson.scheduled_date < datetime.combine(lesson_date, datetime.min.time()) + timedelta(days=1),
                Lesson.status != LESSON_CANCELLED
            )
        ).count()
        
        if existing_lessons >= 2:
            flash('Student already has maximum 2 lessons scheduled for this day', 'error')
            return redirect(url_for('lessons'))
        
        lesson = Lesson()
        lesson.student_id = student_id
        lesson.instructor_id = student.instructor_id or current_user.id
        lesson.scheduled_date = scheduled_date
        lesson.duration_minutes = duration_minutes
        lesson.lesson_type = request.form.get('lesson_type', 'practical')
        lesson.location = request.form.get('location')
        lesson.cost = student.get_lesson_price(duration_minutes)
        
        # Assign vehicle if specified
        vehicle_id = request.form.get('vehicle_id')
        if vehicle_id:
            lesson.vehicle_id = int(vehicle_id)
        
        db.session.add(lesson)
        db.session.commit()
        
        # WhatsApp confirmation would be sent in production
        
        flash('Lesson scheduled successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error scheduling lesson: {str(e)}', 'error')
    
    return redirect(url_for('lessons'))

@app.route('/vehicles/add', methods=['POST'])
@require_role('admin')
def add_vehicle():
    """Add a new vehicle"""
    try:
        vehicle = Vehicle()
        vehicle.registration_number = request.form['registration_number']
        vehicle.make = request.form['make']
        vehicle.model = request.form['model']
        vehicle.year = int(request.form['year'])
        vehicle.license_class = request.form['license_class']
        
        db.session.add(vehicle)
        db.session.commit()
        flash(f'Vehicle {vehicle.registration_number} added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding vehicle: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/vehicles/<int:vehicle_id>/assign', methods=['POST'])
@require_role('admin')
def assign_vehicle(vehicle_id):
    """Assign a vehicle to an instructor"""
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    instructor_id = request.form.get('instructor_id')
    
    if instructor_id:
        instructor = User.query.get(instructor_id)
        if instructor and instructor.is_instructor():
            vehicle.instructor_id = instructor_id
            flash(f'Vehicle {vehicle.registration_number} assigned to {instructor.get_full_name()}!', 'success')
        else:
            flash('Invalid instructor selected.', 'error')
    else:
        vehicle.instructor_id = None
        flash(f'Vehicle {vehicle.registration_number} unassigned.', 'info')
    
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/payments/add', methods=['POST'])
@require_role('admin')
def add_payment():
    """Record a new payment"""
    try:
        student_id = request.form['student_id']
        amount = float(request.form['amount'])
        
        student = Student.query.get(student_id)
        if not student:
            flash('Student not found.', 'error')
            return redirect(url_for('admin_dashboard'))
        
        payment = Payment()
        payment.student_id = student_id
        payment.amount = amount
        payment.payment_type = request.form['payment_type']
        payment.payment_method = request.form.get('payment_method')
        payment.reference_number = request.form.get('reference_number')
        payment.processed_by = current_user.id
        
        # Update student's account balance
        student.account_balance = float(student.account_balance) + amount
        
        db.session.add(payment)
        db.session.commit()
        flash(f'Payment of ${amount:.2f} recorded for {student.name}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error recording payment: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/payments')
@require_role('admin')
def payments():
    """Payment management page"""
    payments_list = Payment.query.order_by(Payment.created_at.desc()).all()
    students_list = Student.query.filter_by(is_active=True).all()
    
    return render_template('payments.html', payments=payments_list, students=students_list)

@app.route('/pricing')
@require_role('admin')
def pricing():
    """Lesson pricing management page"""
    pricing_list = LessonPricing.query.all()
    
    return render_template('pricing.html', pricing=pricing_list)

@app.route('/pricing/add', methods=['POST'])
@require_role('admin')
def add_pricing():
    """Add new lesson pricing"""
    try:
        license_class = request.form['license_class']
        
        # Check if pricing already exists for this license class
        existing = LessonPricing.query.filter_by(license_class=license_class).first()
        if existing:
            flash(f'Pricing for {license_class} already exists. Use edit to update.', 'error')
            return redirect(url_for('pricing'))
        
        pricing = LessonPricing()
        pricing.license_class = license_class
        pricing.price_per_30min = float(request.form['price_per_30min'])
        pricing.price_per_60min = float(request.form['price_per_60min'])
        
        db.session.add(pricing)
        db.session.commit()
        flash(f'Pricing added for {license_class} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding pricing: {str(e)}', 'error')
    
    return redirect(url_for('pricing'))

@app.route('/pricing/<int:pricing_id>/update', methods=['POST'])
@require_role('admin')
def update_pricing(pricing_id):
    """Update existing lesson pricing"""
    try:
        pricing = LessonPricing.query.get_or_404(pricing_id)
        
        pricing.price_per_30min = float(request.form['price_per_30min'])
        pricing.price_per_60min = float(request.form['price_per_60min'])
        pricing.updated_at = datetime.now()
        
        db.session.commit()
        flash(f'Pricing updated for {pricing.license_class} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating pricing: {str(e)}', 'error')
    
    return redirect(url_for('pricing'))

@app.route('/pricing/<int:pricing_id>/delete', methods=['POST'])
@require_role('super_admin')
def delete_pricing(pricing_id):
    """Delete lesson pricing (Super Admin only)"""
    try:
        pricing = LessonPricing.query.get_or_404(pricing_id)
        license_class = pricing.license_class
        
        db.session.delete(pricing)
        db.session.commit()
        flash(f'Pricing deleted for {license_class} successfully!', 'success')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/lessons/<int:lesson_id>/complete', methods=['POST'])
@require_login
def complete_lesson(lesson_id):
    """Mark a lesson as completed"""
    lesson = Lesson.query.get_or_404(lesson_id)
    
    # Verify instructor can complete this lesson
    if current_user.is_instructor() and lesson.instructor_id != current_user.id:
        flash('You can only complete your own lessons.', 'error')
        return redirect(url_for('lessons'))
    
    try:
        lesson.mark_completed(
            notes=request.form.get('notes'),
            feedback=request.form.get('feedback'),
            rating=int(request.form['rating']) if request.form.get('rating') else None
        )
        db.session.commit()
        flash('Lesson marked as completed!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error completing lesson: {str(e)}', 'error')
    
    return redirect(url_for('lessons'))

@app.route('/whatsapp-bot')
@require_role('admin')
def whatsapp_bot():
    """WhatsApp bot interface for demonstration and monitoring"""
    return whatsapp_bot_interface()

@app.route('/whatsapp-bot-interface')
@require_role('admin')
def whatsapp_bot_interface():
    """WhatsApp bot interface for demonstration and monitoring"""
    # Get recent WhatsApp sessions
    sessions = WhatsAppSession.query.order_by(WhatsAppSession.last_activity.desc()).limit(20).all()
    
    # Get students for simulation
    students_list = Student.query.filter_by(is_active=True).all()
    
    # Get Twilio configuration status
    configs = {config.key: config.value for config in SystemConfig.query.all()}
    
    return render_template('whatsapp_bot.html', sessions=sessions, students=students_list, config=configs)

@app.route('/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages from Twilio"""
    from whatsappbot import webhook_handler
    return webhook_handler()

@app.route('/whatsapp-bot/simulate', methods=['POST'])
@require_role('admin')
def simulate_whatsapp():
    """Simulate a WhatsApp interaction"""
    try:
        student_id = request.form['student_id']
        message = request.form['message']
        
        student = Student.query.get(student_id)
        if not student:
            flash('Student not found.', 'error')
            return redirect(url_for('whatsapp_bot'))
        
        # Create or update WhatsApp session
        session_id = f"whatsapp_{student.phone}_{datetime.now().strftime('%Y%m%d')}"
        whatsapp_session = WhatsAppSession.query.filter_by(session_id=session_id).first()
        
        if not whatsapp_session:
            whatsapp_session = WhatsAppSession()
            whatsapp_session.student_id = student_id
            whatsapp_session.session_id = session_id
            db.session.add(whatsapp_session)
        
        whatsapp_session.last_message = message
        whatsapp_session.last_activity = datetime.now()
        
        db.session.commit()
        flash(f'WhatsApp message simulated for {student.name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error simulating WhatsApp: {str(e)}', 'error')
    
    return redirect(url_for('whatsapp_bot'))

@app.route('/users/<user_id>/role', methods=['POST'])
@require_role('super_admin')
def update_user_role(user_id):
    """Update user role (Super Admin only)"""
    user = User.query.get_or_404(user_id)
    new_role = request.form['role']
    
    if new_role in ['instructor', 'admin', 'super_admin']:
        user.role = new_role
        db.session.commit()
        flash(f'Role updated for {user.get_full_name()}', 'success')
    else:
        flash('Invalid role specified.', 'error')
    
    return redirect(url_for('super_admin_dashboard'))

@app.route('/config/update', methods=['POST'])
@require_role('super_admin')
def update_config():
    """Update system configuration"""
    try:
        # Handle Twilio configuration specially
        if 'whatsapp_number' in request.form:
            # Update Twilio Account SID
            account_sid = request.form['value']
            SystemConfig.set_config('TWILIO_ACCOUNT_SID', account_sid, 'Twilio Account SID for WhatsApp API')
            
            # Update Auth Token if provided
            auth_token = request.form.get('auth_token')
            if auth_token:
                SystemConfig.set_config('TWILIO_AUTH_TOKEN', auth_token, 'Twilio Auth Token for WhatsApp API')
            
            # Update WhatsApp Number
            whatsapp_number = request.form['whatsapp_number']
            SystemConfig.set_config('TWILIO_WHATSAPP_NUMBER', whatsapp_number, 'Twilio WhatsApp Phone Number')
            
            # Reinitialize Twilio client
            from whatsappbot import whatsapp_bot
            whatsapp_bot.initialize_twilio()
            
            flash('Twilio configuration updated successfully!', 'success')
        else:
            # Handle regular configuration
            key = request.form['key']
            value = request.form['value']
            description = request.form.get('description')
            
            SystemConfig.set_config(key, value, description)
            flash(f'Configuration {key} updated successfully!', 'success')
            
    except Exception as e:
        flash(f'Error updating configuration: {str(e)}', 'error')
    
    return redirect(url_for('super_admin_dashboard'))

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(error):
    return render_template('403.html'), 404
