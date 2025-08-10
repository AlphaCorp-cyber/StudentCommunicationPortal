from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import current_user, login_user, logout_user
from sqlalchemy import or_, and_

from app import app, db
from models import User, Student, Lesson, WhatsAppSession, SystemConfig, Vehicle, Payment, LessonPricing, LESSON_SCHEDULED, LESSON_COMPLETED, LESSON_CANCELLED, ROLE_INSTRUCTOR, ROLE_ADMIN, ROLE_SUPER_ADMIN, InstructorSubscription, SubscriptionPlan, SUBSCRIPTION_ACTIVE
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
    return render_template('landing.html')

@app.route('/demo')
def demo():
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
    
    # Get vehicles with instructor relationships loaded
    vehicles = Vehicle.query.options(db.joinedload(Vehicle.instructor)).filter_by(is_active=True).all()
    
    # Get recent payments
    recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(5).all()
    
    # Get today's lessons
    today_lessons = Lesson.query.filter(
        Lesson.scheduled_date >= datetime.now().date(),
        Lesson.scheduled_date < datetime.now().date() + timedelta(days=1)
    ).all()
    
    # Get pending lessons
    pending_lessons = Lesson.query.filter_by(status=LESSON_SCHEDULED).count()
    
    # Revenue calculations
    from sqlalchemy import func
    total_revenue = db.session.query(func.sum(Payment.amount)).scalar() or 0
    
    # This month's revenue
    current_month = datetime.now().month
    current_year = datetime.now().year
    this_month_revenue = db.session.query(func.sum(Payment.amount)).filter(
        func.extract('month', Payment.created_at) == current_month,
        func.extract('year', Payment.created_at) == current_year
    ).scalar() or 0
    
    # Outstanding balances (negative account balances)
    outstanding_balance = db.session.query(func.sum(Student.account_balance)).filter(
        Student.account_balance < 0
    ).scalar() or 0
    outstanding_balance = abs(outstanding_balance)
    
    # Total account credits (positive balances)
    total_credits = db.session.query(func.sum(Student.account_balance)).filter(
        Student.account_balance > 0
    ).scalar() or 0
    
    # Revenue by payment method this month
    payment_methods = db.session.query(
        Payment.payment_method,
        func.sum(Payment.amount).label('total')
    ).filter(
        func.extract('month', Payment.created_at) == current_month,
        func.extract('year', Payment.created_at) == current_year
    ).group_by(Payment.payment_method).all()
    
    stats = {
        'total_students': len(students),
        'total_instructors': len(instructors),
        'todays_lessons': len(today_lessons),
        'pending_lessons': pending_lessons,
        'completed_lessons': Lesson.query.filter_by(status=LESSON_COMPLETED).count(),
        'total_revenue': total_revenue,
        'this_month_revenue': this_month_revenue,
        'outstanding_balance': outstanding_balance,
        'total_credits': total_credits
    }
    
    return render_template('admin_dashboard.html', 
                         students=students[:10],  # Show first 10
                         instructors=instructors,
                         vehicles=vehicles,
                         recent_payments=recent_payments,
                         today_lessons=today_lessons,
                         payment_methods=payment_methods,
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
    """Add a new student with auto-assignment of instructor"""
    try:
        license_type = request.form.get('license_type', 'Class 4')
        
        # Auto-assign instructor based on license class and vehicle availability
        from sqlalchemy import func
        
        # First, try to find instructor with vehicles for this license class
        available_instructor = db.session.query(User).join(Vehicle, User.id == Vehicle.instructor_id).filter(
            User.role == 'instructor',
            User.active == True,
            Vehicle.license_class == license_type,
            Vehicle.is_active == True
        ).first()
        
        if not available_instructor:
            # Fallback: find instructor with least students regardless of vehicle
            available_instructor = db.session.query(User).outerjoin(Student, User.id == Student.instructor_id).filter(
                User.role == 'instructor',
                User.active == True
            ).group_by(User.id).order_by(func.count(Student.id)).first()
        
        if not available_instructor:
            flash('No active instructors available. Please create an instructor first.', 'error')
            return redirect(url_for('admin_dashboard'))
        
        # Format phone number with +263 prefix
        phone = request.form['phone'].strip()
        if not phone.startswith('+'):
            # Remove any leading zeros or spaces
            phone = phone.lstrip('0').strip()
            phone = f'+263{phone}'
        
        # Check if phone number already exists
        existing_student = Student.query.filter_by(phone=phone).first()
        if existing_student:
            flash(f'A student with phone number {phone} already exists.', 'error')
            return redirect(url_for('admin_dashboard'))
        
        student = Student()
        student.name = request.form['name'].strip()
        student.phone = phone
        student.email = request.form.get('email', '').strip() or None
        student.address = request.form.get('address', '').strip() or None
        student.license_type = license_type
        student.current_location = request.form.get('current_location', '').strip() or None
        student.instructor_id = None  # Will be assigned when student selects instructor
        student.total_lessons_required = int(request.form.get('total_lessons_required', 20))
        
        db.session.add(student)
        db.session.commit()
        
        flash(f'Student {student.name} added successfully! Auto-assigned to instructor: {available_instructor.get_full_name()} ({license_type})', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding student: {str(e)}")  # For debugging
        flash(f'Error adding student: Please check all required fields are filled correctly.', 'error')
    
    return redirect(url_for('admin_dashboard'))

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

@app.route('/students/<int:student_id>/delete', methods=['POST'])
@require_role('admin')
def delete_student(student_id):
    """Delete a student and all associated records"""
    try:
        student = Student.query.get_or_404(student_id)
        student_name = student.name
        
        # Mark student as inactive instead of hard delete to preserve data integrity
        student.is_active = False
        db.session.commit()
        
        flash(f'Student {student_name} has been deactivated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'error')
    
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

@app.route('/api/available_timeslots')
@require_login
def get_available_timeslots():
    """Get available timeslots for an instructor"""
    student_id = request.args.get('student_id')
    days_ahead = int(request.args.get('days_ahead', 7))
    
    if not student_id:
        return jsonify({'error': 'Student ID required'}), 400
    
    try:
        student = Student.query.get(student_id)
        if not student or not student.instructor:
            return jsonify({'error': 'Student or instructor not found'}), 400
        
        instructor = student.instructor
        available_slots = get_instructor_available_timeslots(instructor, days_ahead)
        
        return jsonify({'timeslots': available_slots})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_instructor_available_timeslots(instructor, days_ahead=2):
    """Get available timeslots for an instructor (excluding booked slots)"""
    available_slots = []
    current_time = datetime.now()
    start_date = current_time.date()
    
    # Define working hours (6 AM to 4 PM, Monday to Saturday)
    working_hours = {
        0: (6, 16),   # Monday
        1: (6, 16),   # Tuesday  
        2: (6, 16),   # Wednesday
        3: (6, 16),   # Thursday
        4: (6, 16),   # Friday
        5: (6, 16),   # Saturday
        6: None       # Sunday (closed)
    }
    
    # Only check today and tomorrow (max 2 days)
    for day_offset in range(min(days_ahead, 2)):
        check_date = start_date + timedelta(days=day_offset)
        weekday = check_date.weekday()
        
        # Skip if no working hours for this day
        if weekday not in working_hours or working_hours[weekday] is None:
            continue
        
        start_hour, end_hour = working_hours[weekday]
        
        # Get existing lessons for this instructor on this date
        existing_lessons = Lesson.query.filter(
            Lesson.instructor_id == instructor.id,
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= datetime.combine(check_date, datetime.min.time()),
            Lesson.scheduled_date < datetime.combine(check_date + timedelta(days=1), datetime.min.time())
        ).all()
        
        # Create list of busy time slots
        busy_slots = set()
        for lesson in existing_lessons:
            start_time = lesson.scheduled_date
            # Block both 30-minute slots for any lesson
            busy_slots.add(start_time.replace(second=0, microsecond=0))
            if lesson.duration_minutes > 30:
                busy_slots.add((start_time + timedelta(minutes=30)).replace(second=0, microsecond=0))
        
        # Generate 30-minute time slots
        for hour in range(start_hour, end_hour):
            for minute in [0, 30]:
                slot_time = datetime.combine(check_date, datetime.min.time().replace(hour=hour, minute=minute))
                
                # Skip if slot is in the past
                if slot_time <= current_time:
                    continue
                
                # Skip if slot is busy
                if slot_time in busy_slots:
                    continue
                
                available_slots.append({
                    'datetime': slot_time.isoformat(),
                    'display': slot_time.strftime('%A, %B %d - %I:%M %p'),
                    'date': slot_time.strftime('%Y-%m-%d'),
                    'time': slot_time.strftime('%H:%M'),
                    'day_name': slot_time.strftime('%A')
                })
    
    return available_slots

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
        
        # Handle datetime with or without seconds
        scheduled_date_str = request.form['scheduled_date']
        try:
            scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%dT%H:%M')
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
        
        # Validate booking time rules
        current_time = datetime.now()
        lesson_date = scheduled_date.date()
        current_date = current_time.date()
        
        # Check if trying to book in the past
        if scheduled_date <= current_time:
            flash('Cannot schedule lessons in the past', 'error')
            return redirect(url_for('lessons'))
        
        # Different rules for admin vs WhatsApp bot bookings
        # Admins can book for tomorrow anytime
        if current_user.is_admin() or current_user.is_super_admin():
            # Admins: Allow booking for today or tomorrow anytime
            if lesson_date > (current_date + timedelta(days=1)):
                flash('Lessons can only be booked for today or tomorrow', 'error')
                return redirect(url_for('lessons'))
        else:
            # Instructors and WhatsApp bot: More restrictive rules
            # Only allow booking for today or tomorrow
            if lesson_date > (current_date + timedelta(days=1)):
                flash('Lessons can only be booked for today or tomorrow', 'error')
                return redirect(url_for('lessons'))
            
            # For tomorrow bookings, check time restrictions (WhatsApp bot rule)
            if lesson_date == (current_date + timedelta(days=1)):
                # Can only book tomorrow if it's after 6 PM today or before 3:30 PM tomorrow
                if current_time.hour < 18 and current_date < lesson_date:
                    flash('Next day lessons can only be booked after 6:00 PM', 'error')
                    return redirect(url_for('lessons'))
                elif current_date == lesson_date and current_time.hour >= 15 and current_time.minute >= 30:
                    flash('Booking for tomorrow closes at 3:30 PM', 'error')
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
def pricing():
    """Public pricing page"""
    return render_template('pricing.html')

@app.route('/pricing/admin')
@require_role('admin')
def pricing_admin():
    """Lesson pricing management page"""
    pricing_list = LessonPricing.query.all()
    
    return render_template('pricing_old.html', pricing=pricing_list)

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
            return redirect(url_for('pricing_admin'))
        
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
    
    return redirect(url_for('pricing_admin'))

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
    
    return redirect(url_for('pricing_admin'))

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
    
    # Verify user has permission to complete this lesson
    if current_user.is_instructor() and lesson.instructor_id != current_user.id:
        flash('You can only complete your own lessons.', 'error')
        return redirect(url_for('lessons'))
    elif not (current_user.is_instructor() or current_user.is_admin() or current_user.is_super_admin()):
        flash('Access denied.', 'error')
        return redirect(url_for('lessons'))
    


@app.route('/api/send-lesson-reminders')
@require_role('admin')
def send_lesson_reminders():
    """Send automated lesson reminders"""
    from whatsappbot import whatsapp_bot
    from datetime import timedelta
    
    try:
        # Initialize bot
        whatsapp_bot.initialize_twilio()
        
        current_time = datetime.now()
        
        # 24-hour reminders
        tomorrow_start = current_time + timedelta(hours=24)
        tomorrow_end = tomorrow_start + timedelta(hours=1)
        
        lessons_24h = Lesson.query.filter(
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= tomorrow_start,
            Lesson.scheduled_date <= tomorrow_end
        ).all()
        
        # 2-hour reminders
        soon_start = current_time + timedelta(hours=2)
        soon_end = soon_start + timedelta(minutes=30)
        
        lessons_2h = Lesson.query.filter(
            Lesson.status == LESSON_SCHEDULED,
            Lesson.scheduled_date >= soon_start,
            Lesson.scheduled_date <= soon_end
        ).all()
        
        sent_count = 0
        
        # Send 24-hour reminders
        for lesson in lessons_24h:
            if whatsapp_bot.send_lesson_reminder_24h(lesson):
                sent_count += 1
        
        # Send 2-hour reminders (student and instructor)
        for lesson in lessons_2h:
            if whatsapp_bot.send_lesson_reminder_2h(lesson):
                sent_count += 1
            if whatsapp_bot.send_instructor_lesson_reminder(lesson):
                sent_count += 1
        
        return jsonify({
            'success': True,
            'message': f'Sent {sent_count} reminders',
            'lessons_24h': len(lessons_24h),
            'lessons_2h': len(lessons_2h)
        })
        
    except Exception as e:
        logger.error(f"Error sending reminders: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/check-low-balances')
@require_role('admin')
def check_low_balances():
    """Check and warn students with low balances"""
    from whatsappbot import whatsapp_bot
    
    try:
        whatsapp_bot.initialize_twilio()
        
        students = Student.query.filter_by(is_active=True).all()
        warned_count = 0
        
        for student in students:
            if whatsapp_bot.check_and_warn_low_balance(student):
                warned_count += 1
        
        return jsonify({
            'success': True,
            'message': f'Warned {warned_count} students about low balance',
            'total_students': len(students)
        })
        
    except Exception as e:
        logger.error(f"Error checking balances: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


    try:
        rating_value = None
        if request.form.get('rating') and request.form.get('rating').strip():
            rating_value = int(request.form['rating'])
        
        lesson.mark_completed(
            notes=request.form.get('notes', '').strip() or None,
            feedback=request.form.get('feedback', '').strip() or None,
            rating=rating_value
        )
        db.session.commit()
        flash(f'Lesson for {lesson.student.name} marked as completed!', 'success')
    except ValueError as e:
        db.session.rollback()
        flash('Invalid rating value provided.', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Error completing lesson: {str(e)}', 'error')
    
    return redirect(url_for('lessons'))

@app.route('/lessons/<int:lesson_id>/delete', methods=['POST'])
@require_login
def delete_lesson(lesson_id):
    """Delete a scheduled lesson"""
    lesson = Lesson.query.get_or_404(lesson_id)
    
    # Verify user has permission to delete this lesson
    if current_user.is_instructor() and lesson.instructor_id != current_user.id:
        flash('You can only delete your own lessons.', 'error')
        return redirect(url_for('lessons'))
    elif not (current_user.is_instructor() or current_user.is_admin() or current_user.is_super_admin()):
        flash('Access denied.', 'error')
        return redirect(url_for('lessons'))
    
    # Only allow deletion of scheduled lessons
    if lesson.status != LESSON_SCHEDULED:
        flash('Only scheduled lessons can be deleted.', 'error')
        return redirect(url_for('lessons'))
    
    try:
        student_name = lesson.student.name
        lesson_date = lesson.scheduled_date.strftime('%Y-%m-%d %H:%M')
        
        db.session.delete(lesson)
        db.session.commit()
        
        flash(f'Lesson for {student_name} on {lesson_date} has been deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting lesson: {str(e)}', 'error')
    
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

@app.route('/api/whatsapp-simulate', methods=['POST'])
@require_role('admin')
def api_simulate_whatsapp():
    """API endpoint for live WhatsApp chat simulation"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        message = data.get('message')
        
        if not student_id or not message:
            return jsonify({'success': False, 'error': 'Missing student_id or message'}), 400
        
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        # Initialize bot if needed
        from whatsappbot import whatsapp_bot
        if not whatsapp_bot.twilio_client:
            whatsapp_bot.initialize_twilio()
        
        # Process the message through the WhatsApp bot
        bot_response = whatsapp_bot.process_message(student.phone, message)
        
        return jsonify({
            'success': True, 
            'response': bot_response,
            'student_name': student.name,
            'message_sent': message
        })
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in API WhatsApp simulation: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/whatsapp-bot/simulate', methods=['POST'])
@require_role('admin')
def simulate_whatsapp():
    """Simulate a WhatsApp interaction (legacy form-based)"""
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

@app.route('/settings')
@require_login
def account_settings():
    """Account settings page"""
    users = []
    if current_user.is_admin() or current_user.is_super_admin():
        users = User.query.all()
    
    return render_template('account_settings.html', users=users)

@app.route('/add-user', methods=['POST'])
@require_role('admin')
def add_user():
    """Add a new user"""
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    role = request.form.get('role')
    
    if not all([username, email, password, role]):
        flash('All required fields must be filled.', 'error')
        return redirect(url_for('account_settings'))
    
    # Check if username or email already exists
    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'error')
        return redirect(url_for('account_settings'))
    
    if User.query.filter_by(email=email).first():
        flash('Email already exists.', 'error')
        return redirect(url_for('account_settings'))
    
    try:
        new_user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash(f'User "{username}" added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding user: {str(e)}', 'error')
    
    return redirect(url_for('account_settings'))

@app.route('/change-password', methods=['POST'])
@require_login
def change_password():
    """Change user password"""
    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    current_password = request.form.get('current_password')
    
    if not new_password or not confirm_password:
        flash('New password and confirmation are required.', 'error')
        return redirect(url_for('account_settings'))
    
    if new_password != confirm_password:
        flash('Password confirmation does not match.', 'error')
        return redirect(url_for('account_settings'))
    
    # If changing own password, verify current password
    if not user_id or int(user_id) == current_user.id:
        if not current_password or not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('account_settings'))
        user = current_user
    else:
        # Admin changing another user's password
        if not (current_user.is_admin() or current_user.is_super_admin()):
            flash('Access denied.', 'error')
            return redirect(url_for('account_settings'))
        user = User.query.get(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('account_settings'))
    
    try:
        user.set_password(new_password)
        db.session.commit()
        flash('Password changed successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error changing password: {str(e)}', 'error')
    
    return redirect(url_for('account_settings'))

@app.route('/deactivate-user/<int:user_id>', methods=['POST'])
@require_role('admin')
def deactivate_user(user_id):
    """Deactivate a user account"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('account_settings'))
    
    try:
        user.active = False
        db.session.commit()
        flash(f'User "{user.username}" deactivated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deactivating user: {str(e)}', 'error')
    
    return redirect(url_for('account_settings'))

@app.route('/activate-user/<int:user_id>', methods=['POST'])
@require_role('admin')
def activate_user(user_id):
    """Activate a user account"""
    user = User.query.get_or_404(user_id)
    
    try:
        user.active = True
        db.session.commit()
        flash(f'User "{user.username}" activated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error activating user: {str(e)}', 'error')
    
    return redirect(url_for('account_settings'))

@app.route('/test-twilio-config')
@require_role('admin')
def test_twilio_config():
    """Test Twilio configuration and Quick Reply setup"""
    import os
    from whatsappbot import WhatsAppBot
    bot = WhatsAppBot()
    
    config_status = {
        'twilio_client': bool(bot.twilio_client),
        'account_sid': bool(os.getenv('TWILIO_ACCOUNT_SID')),
        'auth_token': bool(os.getenv('TWILIO_AUTH_TOKEN')),
        'phone_number': os.getenv('TWILIO_PHONE_NUMBER', 'Not set'),
        'template_sid': os.getenv('TWILIO_TEMPLATE_SID', 'Not set'),
        'mode': 'LIVE' if bot.twilio_client else 'MOCK'
    }
    
    return render_template('whatsapp_bot.html', 
                         config_status=config_status,
                         show_config_test=True)

@app.route('/create-whatsapp-template')
@require_role('admin')
def create_whatsapp_template():
    """Create a Quick Reply template for testing"""
    import os
    from whatsappbot import WhatsAppBot
    
    try:
        bot = WhatsAppBot()
        bot.initialize_twilio()
        
        if not bot.twilio_client:
            flash('Twilio not configured. Please set up your credentials first.', 'error')
            return redirect(url_for('test_twilio_config'))
        
        # Create a test template
        template_sid = bot.create_quick_reply_template(
            template_name="drivelink_menu",
            body_text="Welcome to DriveLink! How can I help you today?",
            button_texts=["View Lessons", "Book Lesson", "Check Progress"]
        )
        
        if template_sid:
            flash(f'Template created successfully! SID: {template_sid}', 'success')
            flash(f'Add this to your .env file: TWILIO_TEMPLATE_SID={template_sid}', 'info')
        else:
            flash('Failed to create template. Check logs for details.', 'error')
            
    except Exception as e:
        flash(f'Error creating template: {str(e)}', 'error')
    
    return redirect(url_for('test_twilio_config'))

@app.route('/whatsapp-auth-management')
@require_role('admin')
def whatsapp_auth_management():
    """Manage WhatsApp authentication states"""
    from models import SystemConfig
    
    # Get all authentication-related configs
    auth_configs = SystemConfig.query.filter(
        or_(
            SystemConfig.key.like('authenticated_%'),
            SystemConfig.key.like('auth_state_%')
        )
    ).order_by(SystemConfig.updated_at.desc()).all()
    
    active_sessions = []
    pending_auths = []
    
    for config in auth_configs:
        if config.key.startswith('authenticated_'):
            phone = config.key.replace('authenticated_', '')
            # Find associated user
            user = User.query.filter_by(phone=phone).first()
            student = Student.query.filter_by(phone=phone).first()
            
            active_sessions.append({
                'phone': phone,
                'user_type': 'instructor' if user else 'student',
                'name': user.get_full_name() if user else (student.name if student else 'Unknown'),
                'last_activity': config.updated_at,
                'config_id': config.id
            })
        elif config.key.startswith('auth_state_'):
            phone = config.key.replace('auth_state_', '')
            user = User.query.filter_by(phone=phone).first()
            student = Student.query.filter_by(phone=phone).first()
            
            pending_auths.append({
                'phone': phone,
                'user_type': 'instructor' if user else 'student',
                'name': user.get_full_name() if user else (student.name if student else 'Unknown'),
                'timestamp': config.updated_at,
                'config_id': config.id
            })
    
    return render_template('whatsapp_auth.html', 
                         active_sessions=active_sessions, 
                         pending_auths=pending_auths)

@app.route('/clear-whatsapp-auth/<int:config_id>', methods=['POST'])
@require_role('admin')
def clear_whatsapp_auth(config_id):
    """Clear a specific WhatsApp authentication"""
    try:
        config = SystemConfig.query.get_or_404(config_id)
        phone = config.key.replace('authenticated_', '').replace('auth_state_', '')
        
        db.session.delete(config)
        db.session.commit()
        
        flash(f'Authentication cleared for {phone}', 'success')
    except Exception as e:
        flash(f'Error clearing authentication: {str(e)}', 'error')
    
    return redirect(url_for('whatsapp_auth_management'))

@app.route('/clear-all-whatsapp-auth', methods=['POST'])
@require_role('admin')
def clear_all_whatsapp_auth():
    """Clear all WhatsApp authentications"""
    try:
        auth_configs = SystemConfig.query.filter(
            or_(
                SystemConfig.key.like('authenticated_%'),
                SystemConfig.key.like('auth_state_%')
            )
        ).all()
        
        count = len(auth_configs)
        for config in auth_configs:
            db.session.delete(config)
        
        db.session.commit()
        flash(f'Cleared {count} authentication sessions', 'success')
    except Exception as e:
        flash(f'Error clearing all authentications: {str(e)}', 'error')
    
    return redirect(url_for('whatsapp_auth_management'))

# Student Portal Routes
@app.route('/student-login', methods=['GET', 'POST'])
def student_login():
    """Student login with phone number and PIN"""
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        pin = request.form['pin'].strip()
        
        # Clean phone number format
        if not phone.startswith('+'):
            if phone.startswith('0'):
                phone = '+263' + phone[1:]
            elif phone.startswith('263'):
                phone = '+' + phone
            else:
                phone = '+263' + phone
        
        # Find student by phone
        student = Student.query.filter_by(phone=phone, is_active=True).first()
        
        if student and student.check_pin(pin):
            # Store student login in session
            session['student_id'] = student.id
            session['student_logged_in'] = True
            
            remember = bool(request.form.get('remember'))
            if remember:
                session.permanent = True
            
            flash(f'Welcome back, {student.name}!', 'success')
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid phone number or PIN.', 'error')
    
    return render_template('student_login.html')

@app.route('/student-register', methods=['GET', 'POST'])
def student_register():
    """Student PIN setup"""
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        pin = request.form['pin'].strip()
        confirm_pin = request.form['confirm_pin'].strip()
        
        # Validate PIN
        if len(pin) != 4 or not pin.isdigit():
            flash('PIN must be exactly 4 digits.', 'error')
            return render_template('student_register.html')
        
        if pin != confirm_pin:
            flash('PINs do not match.', 'error')
            return render_template('student_register.html')
        
        # Clean phone number format
        if not phone.startswith('+'):
            if phone.startswith('0'):
                phone = '+263' + phone[1:]
            elif phone.startswith('263'):
                phone = '+' + phone
            else:
                phone = '+263' + phone
        
        # Find student by phone
        student = Student.query.filter_by(phone=phone, is_active=True).first()
        
        if not student:
            flash('Phone number not found. Please contact your driving school to register first.', 'error')
            return render_template('student_register.html')
        
        if student.pin_hash:
            flash('PIN already set for this number. Use the login page instead.', 'error')
            return redirect(url_for('student_login'))
        
        # Set PIN
        student.set_pin(pin)
        db.session.commit()
        
        flash('PIN set successfully! You can now log in.', 'success')
        return redirect(url_for('student_login'))
    
    return render_template('student_register.html')

@app.route('/student-dashboard')
def student_dashboard():
    """Student dashboard"""
    if not session.get('student_logged_in') or not session.get('student_id'):
        flash('Please log in to access your dashboard.', 'error')
        return redirect(url_for('student_login'))
    
    student = Student.query.get(session['student_id'])
    if not student or not student.is_active:
        session.clear()
        flash('Student account not found or inactive.', 'error')
        return redirect(url_for('student_login'))
    
    # Get upcoming lessons
    upcoming_lessons = Lesson.query.filter(
        Lesson.student_id == student.id,
        Lesson.status == LESSON_SCHEDULED,
        Lesson.scheduled_date >= datetime.now()
    ).order_by(Lesson.scheduled_date).limit(5).all()
    
    # Get recent completed lessons
    recent_lessons = Lesson.query.filter(
        Lesson.student_id == student.id,
        Lesson.status == LESSON_COMPLETED
    ).order_by(Lesson.completed_date.desc()).limit(5).all()
    
    return render_template('student_dashboard.html', 
                         student=student,
                         upcoming_lessons=upcoming_lessons,
                         recent_lessons=recent_lessons)

@app.route('/student-logout')
def student_logout():
    """Student logout"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('student_login'))

@app.route('/student-lessons')
def student_lessons():
    """Student lessons page"""
    if not session.get('student_logged_in') or not session.get('student_id'):
        return redirect(url_for('student_login'))
    
    student = Student.query.get(session['student_id'])
    if not student:
        return redirect(url_for('student_login'))
    
    # Get all student lessons
    all_lessons = Lesson.query.filter_by(student_id=student.id).order_by(Lesson.scheduled_date.desc()).all()
    
    return render_template('student_lessons.html', student=student, lessons=all_lessons)

@app.route('/student-progress')
def student_progress():
    """Student progress page"""
    if not session.get('student_logged_in') or not session.get('student_id'):
        return redirect(url_for('student_login'))
    
    student = Student.query.get(session['student_id'])
    if not student:
        return redirect(url_for('student_login'))
    
    # Get completed lessons with details
    completed_lessons = Lesson.query.filter(
        Lesson.student_id == student.id,
        Lesson.status == LESSON_COMPLETED
    ).order_by(Lesson.completed_date.desc()).all()
    
    return render_template('student_progress.html', student=student, completed_lessons=completed_lessons)

@app.route('/student-profile')
def student_profile():
    """Student profile page"""
    if not session.get('student_logged_in') or not session.get('student_id'):
        return redirect(url_for('student_login'))
    
    student = Student.query.get(session['student_id'])
    if not student:
        return redirect(url_for('student_login'))
    
    return render_template('student_profile.html', student=student)

@app.route('/student-payments')
def student_payments():
    """Student payments page"""
    if not session.get('student_logged_in') or not session.get('student_id'):
        return redirect(url_for('student_login'))
    
    student = Student.query.get(session['student_id'])
    if not student:
        return redirect(url_for('student_login'))
    
    # Get payment history
    payments = Payment.query.filter_by(student_id=student.id).order_by(Payment.created_at.desc()).all()
    
    return render_template('student_payments.html', student=student, payments=payments)

@app.route('/cancel-student-lesson/<int:lesson_id>', methods=['POST'])
def cancel_student_lesson(lesson_id):
    """Cancel a student lesson"""
    if not session.get('student_logged_in') or not session.get('student_id'):
        return redirect(url_for('student_login'))
    
    student = Student.query.get(session['student_id'])
    lesson = Lesson.query.filter_by(id=lesson_id, student_id=student.id).first()
    
    if not lesson:
        flash('Lesson not found.', 'error')
        return redirect(url_for('student_dashboard'))
    
    if lesson.status != LESSON_SCHEDULED:
        flash('Only scheduled lessons can be cancelled.', 'error')
        return redirect(url_for('student_dashboard'))
    
    # Check if cancellation is allowed (at least 2 hours before)
    time_until_lesson = lesson.scheduled_date - datetime.now()
    if time_until_lesson.total_seconds() < 7200:  # 2 hours
        flash('Cannot cancel lessons less than 2 hours before the scheduled time.', 'error')
        return redirect(url_for('student_dashboard'))
    
    lesson.status = LESSON_CANCELLED
    lesson.updated_at = datetime.now()
    db.session.commit()
    
    flash('Lesson cancelled successfully.', 'success')
    return redirect(url_for('student_dashboard'))

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html'), 403

@app.errorhandler(404)
def not_found(error):
    return render_template('403.html'), 404
