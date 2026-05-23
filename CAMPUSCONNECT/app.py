# Python 3.14 compatibility patch
import sys
import typing
if sys.version_info >= (3, 14):
    # Patch for Python 3.14 typing compatibility
    typing_orig_init_subclass = typing._generic_init_subclass
    def patched_init_subclass(cls, *args, **kwargs):
        # Remove problematic attributes before calling original
        old_attrs = {}
        for attr in ['__static_attributes__', '__firstlineno__']:
            if hasattr(cls, attr):
                old_attrs[attr] = getattr(cls, attr)
                try:
                    delattr(cls, attr)
                except AttributeError:
                    pass
        try:
            return typing_orig_init_subclass(cls, *args, **kwargs)
        except AssertionError:
            # Restore attributes if needed
            for attr, val in old_attrs.items():
                try:
                    setattr(cls, attr, val)
                except:
                    pass
            raise
    typing._generic_init_subclass = patched_init_subclass

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_session import Session
from functools import wraps
from datetime import datetime, timedelta, date, time
from sqlalchemy import inspect, text
import os
from models import db, User, Student, Teacher, Lab, LabBooking, InteractiveClass, InteractiveClassBooking, Message, SystemLog
from tasks import start_scheduler
import secrets

app = Flask(__name__, instance_relative_config=True)

# Ensure instance folder exists and use a fixed SQLite file there
os.makedirs(app.instance_path, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)
Session(app)

# Start APScheduler
start_scheduler(app)


# ============= AUTHENTICATION DECORATORS =============

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            user = User.query.get(session['user_id'])
            if user.role != role:
                flash(f'You need to be a {role} to access this page', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============= HOME & AUTH ROUTES =============

@app.route('/')
def index():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user.role == 'student':
            return redirect(url_for('student_dashboard'))
        elif user.role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        full_name = data.get('full_name')
        role = data.get('role')  # student or teacher

        # Validate VVCE email
        if not email.endswith('@vvce.ac.in'):
            return jsonify({'success': False, 'message': 'Email must end with @vvce.ac.in'}), 400

        # Check if user exists
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Email already registered'}), 400

        if password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

        try:
            if role == 'student':
                user = Student(email=email, full_name=full_name)
            elif role == 'teacher':
                user = Teacher(email=email, full_name=full_name)
            else:
                return jsonify({'success': False, 'message': 'Invalid role'}), 400

            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            # Log the action
            log = SystemLog(action='user_registration', user_id=user.id, details=f'{role} registered: {email}')
            db.session.add(log)
            db.session.commit()

            return jsonify({'success': True, 'message': 'Registration successful! Please log in.'}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password) and user.is_active:
            session['user_id'] = user.id
            session['email'] = user.email
            session['role'] = user.role
            session['full_name'] = user.full_name

            # Log the action
            log = SystemLog(action='user_login', user_id=user.id, details=f'User logged in: {email}')
            db.session.add(log)
            db.session.commit()

            return jsonify({'success': True, 'role': user.role}), 200
        else:
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

    return render_template('login.html')


@app.route('/logout')
def logout():
    log = SystemLog(action='user_logout', user_id=session.get('user_id'))
    db.session.add(log)
    db.session.commit()
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))


# ============= ADMIN DASHBOARD =============

@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    total_users = User.query.count()
    total_students = Student.query.count()
    total_teachers = Teacher.query.count()
    total_labs = Lab.query.count()
    active_bookings = LabBooking.query.filter_by(status='pending').count()
    
    stats = {
        'total_users': total_users,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_labs': total_labs,
        'active_bookings': active_bookings
    }
    
    return render_template('admin_dash.html', stats=stats)


@app.route('/api/admin/users')
@role_required('admin')
def get_users():
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'email': u.email,
        'full_name': u.full_name,
        'role': u.role,
        'is_active': u.is_active,
        'created_at': u.created_at.strftime('%Y-%m-%d %H:%M')
    } for u in users])


@app.route('/api/admin/labs', methods=['GET', 'POST'])
@role_required('admin')
def manage_labs():
    if request.method == 'POST':
        data = request.get_json()
        lab = Lab(
            name=data['name'],
            location=data['location'],
            capacity=data.get('capacity', 30),
            description=data.get('description', '')
        )
        db.session.add(lab)
        db.session.commit()
        return jsonify({'success': True, 'lab_id': lab.id}), 201

    labs = Lab.query.all()
    return jsonify([{
        'id': l.id,
        'name': l.name,
        'location': l.location,
        'capacity': l.capacity,
        'status': l.status
    } for l in labs])


@app.route('/api/admin/interactive-classes', methods=['GET', 'POST'])
@role_required('admin')
def manage_interactive_classes():
    if request.method == 'POST':
        data = request.get_json()
        ic = InteractiveClass(
            name=data['name'],
            location=data['location'],
            capacity=data.get('capacity', 50),
            description=data.get('description', '')
        )
        db.session.add(ic)
        db.session.commit()
        return jsonify({'success': True, 'class_id': ic.id}), 201

    classes = InteractiveClass.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'location': c.location,
        'capacity': c.capacity,
        'status': c.status
    } for c in classes])


@app.route('/api/admin/delete-user/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False}), 404
    
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})


# ============= STUDENT DASHBOARD =============

@app.route('/student')
@role_required('student')
def student_dashboard():
    student = Student.query.get(session['user_id'])
    unread_messages = Message.query.filter_by(recipient_id=student.id, is_read=False).count()
    
    return render_template('student_dash.html', unread_messages=unread_messages)


@app.route('/api/student/search-teachers')
@role_required('student')
def search_teachers():
    query = request.args.get('q', '')
    
    teachers = Teacher.query.filter(
        (Teacher.full_name.ilike(f'%{query}%')) |
        (Teacher.subject.ilike(f'%{query}%')) |
        (Teacher.department.ilike(f'%{query}%'))
    ).all()
    
    return jsonify([{
        'id': t.id,
        'full_name': t.full_name,
        'subject': t.subject,
        'department': t.department,
        'cabin_location': t.cabin_location,
        'status': t.status,
        'status_updated_at': t.status_updated_at.strftime('%Y-%m-%d %H:%M') if t.status_updated_at else None
    } for t in teachers])


@app.route('/api/student/message', methods=['POST'])
@role_required('student')
def send_message():
    data = request.get_json()
    student = Student.query.get(session['user_id'])
    
    message = Message(
        sender_id=student.id,
        recipient_id=data['recipient_id'],
        subject=data.get('subject', 'No Subject'),
        body=data['body']
    )
    db.session.add(message)
    db.session.commit()
    
    return jsonify({'success': True, 'message_id': message.id}), 201


@app.route('/api/student/messages')
@role_required('student')
def get_student_messages():
    student = Student.query.get(session['user_id'])
    messages = Message.query.filter_by(recipient_id=student.id).order_by(Message.created_at.desc()).all()
    
    return jsonify([{
        'id': m.id,
        'sender_name': m.sender.full_name,
        'subject': m.subject,
        'body': m.body,
        'is_read': m.is_read,
        'created_at': m.created_at.strftime('%Y-%m-%d %H:%M')
    } for m in messages])


@app.route('/api/student/labs')
@role_required('student')
def get_student_labs():
    labs = Lab.query.all()
    return jsonify([{
        'id': l.id,
        'name': l.name,
        'location': l.location,
        'capacity': l.capacity,
        'status': l.status
    } for l in labs])


@app.route('/api/student/interactive-classes')
@role_required('student')
def get_student_interactive():
    classes = InteractiveClass.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'location': c.location,
        'capacity': c.capacity,
        'status': c.status
    } for c in classes])


# ============= TEACHER DASHBOARD =============

@app.route('/teacher')
@role_required('teacher')
def teacher_dashboard():
    teacher = Teacher.query.get(session['user_id'])
    pending_bookings = LabBooking.query.filter_by(teacher_id=teacher.id, status='pending').count()
    unread_messages = Message.query.filter_by(recipient_id=teacher.id, is_read=False).count()
    
    return render_template('teacher_dash.html', 
                         pending_bookings=pending_bookings,
                         unread_messages=unread_messages)


@app.route('/api/teacher/profile', methods=['GET', 'PUT'])
@role_required('teacher')
def teacher_profile():
    teacher = Teacher.query.get(session['user_id'])
    
    if request.method == 'PUT':
        data = request.get_json()
        teacher.subject = data.get('subject', teacher.subject)
        teacher.department = data.get('department', teacher.department)
        teacher.cabin_location = data.get('cabin_location', teacher.cabin_location)
        teacher.timetable = data.get('timetable', teacher.timetable)
        db.session.commit()
        return jsonify({'success': True}), 200
    
    return jsonify({
        'full_name': teacher.full_name,
        'email': teacher.email,
        'subject': teacher.subject,
        'department': teacher.department,
        'cabin_location': teacher.cabin_location,
        'timetable': teacher.timetable,
        'profile_photo': teacher.profile_photo
    })


@app.route('/api/teacher/status', methods=['PUT'])
@role_required('teacher')
def update_teacher_status():
    data = request.get_json()
    teacher = Teacher.query.get(session['user_id'])
    
    valid_statuses = ['free', 'busy', 'away', 'in_class']
    if data['status'] not in valid_statuses:
        return jsonify({'success': False}), 400
    
    teacher.status = data['status']
    teacher.status_updated_at = datetime.utcnow()
    db.session.commit()
    
    log = SystemLog(action='status_update', user_id=teacher.id, 
                   details=f'Status changed to: {data["status"]}')
    db.session.add(log)
    db.session.commit()
    
    return jsonify({'success': True}), 200


@app.route('/api/teacher/book-lab', methods=['POST'])
@role_required('teacher')
def book_lab():
    data = request.get_json()
    teacher = Teacher.query.get(session['user_id'])
    
    # Check if lab exists
    lab = Lab.query.get(data['lab_id'])
    if not lab:
        return jsonify({'success': False, 'message': 'Lab not found'}), 404
    
    # Create booking
    booking_time = datetime.strptime(data['booking_time'], '%H:%M').time()
    booking = LabBooking(
        teacher_id=teacher.id,
        lab_id=lab.id,
        booking_date=datetime.strptime(data['booking_date'], '%Y-%m-%d').date(),
        booking_time=booking_time,
        status='pending'
    )
    
    db.session.add(booking)
    db.session.commit()
    
    log = SystemLog(action='lab_booking', user_id=teacher.id, 
                   details=f'Lab booking created: {booking.id}')
    db.session.add(log)
    db.session.commit()
    
    return jsonify({'success': True, 'booking_id': booking.id}), 201


@app.route('/api/teacher/book-interactive', methods=['POST'])
@role_required('teacher')
def book_interactive_class():
    data = request.get_json()
    teacher = Teacher.query.get(session['user_id'])
    ic = InteractiveClass.query.get(data['interactive_class_id'])
    if not ic:
        return jsonify({'success': False, 'message': 'Interactive class not found'}), 404

    booking = InteractiveClassBooking(
        teacher_id=teacher.id,
        interactive_class_id=ic.id,
        booking_date=datetime.strptime(data['booking_date'], '%Y-%m-%d').date(),
        booking_time=datetime.strptime(data['booking_time'], '%H:%M').time(),
        status='pending'
    )

    db.session.add(booking)
    db.session.commit()

    log = SystemLog(action='interactive_booking', user_id=teacher.id,
                   details=f'Interactive class booking created: {booking.id}')
    db.session.add(log)
    db.session.commit()

    return jsonify({'success': True, 'booking_id': booking.id}), 201


@app.route('/api/teacher/confirm-interactive-booking/<int:booking_id>', methods=['PUT'])
@role_required('teacher')
def confirm_interactive_booking(booking_id):
    booking = InteractiveClassBooking.query.get(booking_id)
    if not booking or booking.teacher_id != session['user_id']:
        return jsonify({'success': False}), 403

    booking.status = 'engaged'
    booking.engaged_at = datetime.utcnow()
    booking.interactive_class.status = 'engaged'

    db.session.commit()

    log = SystemLog(action='interactive_booking_confirmed', user_id=booking.teacher_id,
                   details=f'Interactive class booking {booking_id} confirmed as engaged')
    db.session.add(log)
    db.session.commit()

    return jsonify({'success': True}), 200


@app.route('/api/teacher/interactive-bookings')
@role_required('teacher')
def get_teacher_interactive_bookings():
    teacher = Teacher.query.get(session['user_id'])
    bookings = InteractiveClassBooking.query.filter_by(teacher_id=teacher.id).order_by(InteractiveClassBooking.created_at.desc()).all()

    return jsonify([{
        'id': b.id,
        'class_name': b.interactive_class.name,
        'booking_date': b.booking_date.strftime('%Y-%m-%d'),
        'booking_time': b.booking_time.strftime('%H:%M'),
        'status': b.status,
        'created_at': b.created_at.strftime('%Y-%m-%d %H:%M')
    } for b in bookings])


@app.route('/api/teacher/confirm-booking/<int:booking_id>', methods=['PUT'])
@role_required('teacher')
def confirm_booking(booking_id):
    booking = LabBooking.query.get(booking_id)
    if not booking or booking.teacher_id != session['user_id']:
        return jsonify({'success': False}), 403
    
    booking.status = 'engaged'
    booking.engaged_at = datetime.utcnow()
    booking.lab.status = 'engaged'
    
    db.session.commit()
    
    log = SystemLog(action='booking_confirmed', user_id=booking.teacher_id,
                   details=f'Lab booking {booking_id} confirmed as engaged')
    db.session.add(log)
    db.session.commit()
    
    return jsonify({'success': True}), 200


@app.route('/api/teacher/bookings')
@role_required('teacher')
def get_teacher_bookings():
    teacher = Teacher.query.get(session['user_id'])
    bookings = LabBooking.query.filter_by(teacher_id=teacher.id).order_by(LabBooking.created_at.desc()).all()
    
    return jsonify([{
        'id': b.id,
        'lab_name': b.lab.name,
        'booking_date': b.booking_date.strftime('%Y-%m-%d'),
        'booking_time': b.booking_time.strftime('%H:%M'),
        'status': b.status,
        'created_at': b.created_at.strftime('%Y-%m-%d %H:%M')
    } for b in bookings])


@app.route('/api/teacher/messages')
@role_required('teacher')
def get_teacher_messages():
    teacher = Teacher.query.get(session['user_id'])
    messages = Message.query.filter_by(recipient_id=teacher.id).order_by(Message.created_at.desc()).all()
    
    return jsonify([{
        'id': m.id,
        'sender_name': m.sender.full_name,
        'subject': m.subject,
        'body': m.body,
        'is_read': m.is_read,
        'created_at': m.created_at.strftime('%Y-%m-%d %H:%M')
    } for m in messages])


@app.route('/api/teacher/reply-message/<int:message_id>', methods=['POST'])
@role_required('teacher')
def reply_message(message_id):
    data = request.get_json()
    original_message = Message.query.get(message_id)
    
    if not original_message or original_message.recipient_id != session['user_id']:
        return jsonify({'success': False}), 403
    
    reply = Message(
        sender_id=session['user_id'],
        recipient_id=original_message.sender_id,
        subject=f"Re: {original_message.subject}",
        body=data['body'],
        reply_to_id=message_id
    )
    
    db.session.add(reply)
    db.session.commit()
    
    return jsonify({'success': True}), 201


# ============= ERROR HANDLERS =============

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500


# ============= DATABASE INITIALIZATION =============

@app.cli.command()
def init_db():
    """Initialize the database"""
    with app.app_context():
        db.create_all()
        print("Database initialized!")
        
        # Create sample data
        if User.query.filter_by(email='admin@vvce.ac.in').first() is None:
            admin = User(email='admin@vvce.ac.in', full_name='Admin User', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            
            # Add sample labs
            lab1 = Lab(name='AI Lab', location='Block A, Floor 2', capacity=30)
            lab2 = Lab(name='Database Lab', location='Block B, Floor 1', capacity=25)
            
            # Add sample interactive classes
            ic1 = InteractiveClass(name='Interactive Classroom 1', location='Block C, Floor 1', capacity=60)
            
            db.session.add_all([lab1, lab2, ic1])
            db.session.commit()
            print("Sample data added!")


def ensure_db_schema():
    inspector = inspect(db.engine)

    if 'lab_booking' in inspector.get_table_names():
        lab_columns = [col['name'] for col in inspector.get_columns('lab_booking')]
        if 'warning_sent' not in lab_columns:
            db.session.execute(text('ALTER TABLE lab_booking ADD COLUMN warning_sent BOOLEAN DEFAULT 0'))
            db.session.commit()

    if 'interactive_class_booking' in inspector.get_table_names():
        interactive_columns = [col['name'] for col in inspector.get_columns('interactive_class_booking')]
        if 'warning_sent' not in interactive_columns:
            db.session.execute(text('ALTER TABLE interactive_class_booking ADD COLUMN warning_sent BOOLEAN DEFAULT 0'))
            db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_db_schema()
    app.run(debug=True, host='0.0.0.0', port=5000)
