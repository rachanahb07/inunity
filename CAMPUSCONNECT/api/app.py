import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, Response
from functools import wraps
from datetime import datetime, timedelta, date, time
from sqlalchemy import inspect, text, or_
from werkzeug.utils import secure_filename
import json
import secrets

from models import db, User, Student, Teacher, Lab, LabBooking, InteractiveClass, InteractiveClassBooking, Message, Notification, SystemLog
import tasks

app = Flask(__name__, instance_relative_config=True, template_folder='../templates', static_folder='../static')

# Database configuration
db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'database.db')
os.makedirs(os.path.dirname(db_path), exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads')

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)

try:
    from flask_session import Session
    Session(app)
except Exception:
    pass

# Initialize scheduler if not in production
if os.environ.get('VERCEL') != '1':
    try:
        tasks.start_scheduler(app)
    except Exception as e:
        print(f"Scheduler init warning: {e}")


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
            if not user or user.role != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============= HELPER FUNCTIONS =============

def parse_timetable(timetable_json):
    """Parse and validate teacher timetable JSON format"""
    if not timetable_json:
        return []
    try:
        return json.loads(timetable_json)
    except:
        return []


def resolve_timetable_location_resource(location):
    """Map a timetable location string to an actual Lab or InteractiveClass resource"""
    if not location:
        return None, None
    lab = Lab.query.filter_by(location=location).first()
    if lab:
        return 'lab', lab
    ic = InteractiveClass.query.filter_by(location=location).first()
    if ic:
        return 'interactive_class', ic
    return None, None


def enrich_timetable_entries(timetable_entries):
    """Enhance timetable entries with resource type and name"""
    enriched = []
    for entry in timetable_entries:
        resource_type, resource = resolve_timetable_location_resource(entry.get('location'))
        entry['resource_type'] = resource_type
        entry['resource_name'] = resource.name if resource else entry.get('location')
        enriched.append(entry)
    return enriched


def find_current_timetable_entry(teacher):
    """Return the current timetable entry if the teacher is in class now."""
    timetable = parse_timetable(teacher.timetable)
    if not timetable:
        return None
    now = datetime.now()
    weekday = now.weekday()
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    current_day = day_names[weekday]
    current_time = now.time()
    for entry in timetable:
        if entry.get('day') == current_day:
            try:
                start = datetime.strptime(entry.get('start_time', ''), '%H:%M').time()
                end = datetime.strptime(entry.get('end_time', ''), '%H:%M').time()
                if start <= current_time <= end:
                    entry['resource_type'], entry['resource_name'] = resolve_timetable_location_resource(entry.get('location'))
                    return entry
            except:
                continue
    return None


def get_current_status_from_timetable(teacher):
    """Auto-calculate teacher status based on timetable and current time."""
    timetable = parse_timetable(teacher.timetable)
    if not timetable:
        return teacher.status
    now = datetime.now()
    weekday = now.weekday()
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    current_day = day_names[weekday]
    current_time = now.time()
    for entry in timetable:
        if entry.get('day') == current_day:
            try:
                start = datetime.strptime(entry.get('start_time', ''), '%H:%M').time()
                end = datetime.strptime(entry.get('end_time', ''), '%H:%M').time()
                if start <= current_time <= end:
                    return 'in_class'
            except:
                continue
    if teacher.status in ['busy', 'away']:
        return teacher.status
    return 'free'


# ============= DATABASE INITIALIZATION =============

@app.cli.command()
def init_db():
    """Initialize the database"""
    with app.app_context():
        db.create_all()
        print("Database initialized!")
        
        if User.query.filter_by(email='admin@vvce.ac.in').first() is None:
            admin = User(email='admin@vvce.ac.in', full_name='Admin User', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)

            teacher = Teacher(
                email='teacher1@vvce.ac.in',
                full_name='Prof. Priya Sharma',
                subject='Computer Science',
                department='CSE',
                cabin_location='Block A, Room 101'
            )
            teacher.set_password('teacher123')
            db.session.add(teacher)
            
            lab1 = Lab(name='AI Lab', location='Block A, Floor 2', capacity=30)
            lab2 = Lab(name='Database Lab', location='Block B, Floor 1', capacity=25)
            ic1 = InteractiveClass(name='Interactive Classroom 1', location='Block C, Floor 1', capacity=60)
            
            db.session.add_all([lab1, lab2, ic1])
            db.session.commit()
            print("Sample data added!")


def ensure_db_schema():
    """Ensure database schema is up to date"""
    with app.app_context():
        try:
            db.create_all()
            inspector = inspect(db.engine)
            booking_columns = [col['name'] for col in inspector.get_columns('lab_booking')]
            if 'warning_sent' not in booking_columns:
                db.session.execute(text('ALTER TABLE lab_booking ADD COLUMN warning_sent BOOLEAN DEFAULT 0'))
                db.session.commit()
            if 'started_sent' not in booking_columns:
                db.session.execute(text('ALTER TABLE lab_booking ADD COLUMN started_sent BOOLEAN DEFAULT 0'))
                db.session.commit()
            interactive_columns = [col['name'] for col in inspector.get_columns('interactive_class_booking')]
            if 'warning_sent' not in interactive_columns:
                db.session.execute(text('ALTER TABLE interactive_class_booking ADD COLUMN warning_sent BOOLEAN DEFAULT 0'))
                db.session.commit()
            if 'started_sent' not in interactive_columns:
                db.session.execute(text('ALTER TABLE interactive_class_booking ADD COLUMN started_sent BOOLEAN DEFAULT 0'))
                db.session.commit()
        except Exception as e:
            print(f"Schema ensure warning: {e}")


@app.before_request
def ensure_db_before_request():
    """Initialize DB before first request"""
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        with app.app_context():
            db.create_all()


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
        data = request.get_json() or {}
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        role = data.get('role')

        if not email or not password or not full_name or not role:
            return jsonify({'error': 'Missing fields'}), 400

        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400

        if len(password) < 6:
            return jsonify({'error': 'Password too short'}), 400

        if role == 'student':
            user = Student(email=email, full_name=full_name)
        elif role == 'teacher':
            user = Teacher(email=email, full_name=full_name)
        else:
            return jsonify({'error': 'Invalid role'}), 400

        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'message': 'Registration successful'}), 201

    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() or {}
        email = data.get('email')
        password = data.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            log = SystemLog(action='user_login', user_id=user.id, details=f'User logged in: {email}')
            db.session.add(log)
            db.session.commit()
            return jsonify({'redirect': url_for('index')}), 200
        return jsonify({'error': 'Invalid credentials'}), 401

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============= ADMIN DASHBOARD =============

@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    total_students = Student.query.count()
    total_teachers = Teacher.query.count()
    total_labs = Lab.query.count()
    total_interactive_classes = InteractiveClass.query.count()
    active_bookings = LabBooking.query.filter_by(status='confirmed').count()
    active_bookings += InteractiveClassBooking.query.filter_by(status='confirmed').count()
    stats = {
        'total_users': User.query.count(),
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_labs': total_labs,
        'total_interactive_classes': total_interactive_classes,
        'active_bookings': active_bookings
    }
    return render_template('admin_dash.html', stats=stats)


@app.route('/api/admin/users')
@role_required('admin')
def get_admin_users():
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'email': u.email,
        'full_name': u.full_name,
        'role': u.role,
        'created_at': u.created_at.isoformat() if u.created_at else None
    } for u in users])


@app.route('/api/admin/labs', methods=['GET', 'POST'])
@role_required('admin')
def manage_labs():
    if request.method == 'POST':
        data = request.get_json()
        lab = Lab(name=data['name'], location=data['location'], capacity=data['capacity'])
        db.session.add(lab)
        db.session.commit()
        return jsonify({'id': lab.id}), 201

    labs = Lab.query.all()
    return jsonify([{'id': l.id, 'name': l.name, 'location': l.location, 'capacity': l.capacity} for l in labs])


@app.route('/api/admin/interactive-classes', methods=['GET', 'POST'])
@role_required('admin')
def manage_interactive_classes():
    if request.method == 'POST':
        data = request.get_json()
        ic = InteractiveClass(name=data['name'], location=data['location'], capacity=data['capacity'])
        db.session.add(ic)
        db.session.commit()
        return jsonify({'id': ic.id}), 201

    ics = InteractiveClass.query.all()
    return jsonify([{'id': i.id, 'name': i.name, 'location': i.location, 'capacity': i.capacity} for i in ics])


@app.route('/api/admin/delete-lab/<int:lab_id>', methods=['DELETE'])
@role_required('admin')
def delete_lab(lab_id):
    lab = Lab.query.get_or_404(lab_id)
    db.session.delete(lab)
    db.session.commit()
    return jsonify({'message': 'Lab deleted'}), 200


@app.route('/api/admin/delete-interactive-class/<int:class_id>', methods=['DELETE'])
@role_required('admin')
def delete_interactive_class(class_id):
    ic = InteractiveClass.query.get_or_404(class_id)
    db.session.delete(ic)
    db.session.commit()
    return jsonify({'message': 'Interactive class deleted'}), 200


@app.route('/api/admin/delete-user/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'}), 200


@app.route('/api/admin/logs')
@role_required('admin')
def get_admin_logs():
    logs = SystemLog.query.order_by(SystemLog.created_at.desc()).limit(100).all()
    return jsonify([{'id': l.id, 'action': l.action, 'user_id': l.user_id, 'details': l.details, 'created_at': l.created_at.isoformat()} for l in logs])


@app.route('/api/admin/export-logs')
@role_required('admin')
def export_logs():
    logs = SystemLog.query.all()
    log_data = [{'id': l.id, 'action': l.action, 'user_id': l.user_id, 'details': l.details, 'created_at': str(l.created_at)} for l in logs]
    csv_content = "ID,Action,User ID,Details,Created At\n"
    for log in log_data:
        csv_content += f"{log['id']},{log['action']},{log['user_id']},{log['details']},{log['created_at']}\n"
    return Response(csv_content, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=logs.csv'})


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
    ).limit(20).all()
    return jsonify([{
        'id': t.id,
        'full_name': t.full_name,
        'subject': t.subject,
        'department': t.department,
        'cabin_location': t.cabin_location,
        'status': t.status
    } for t in teachers])


@app.route('/api/student/message', methods=['POST'])
@role_required('student')
def send_message():
    data = request.get_json()
    student = Student.query.get(session['user_id'])
    msg = Message(sender_id=student.id, recipient_id=data['recipient_id'], content=data['content'])
    db.session.add(msg)
    db.session.commit()
    return jsonify({'id': msg.id}), 201


@app.route('/api/student/messages')
@role_required('student')
def get_student_messages():
    student = Student.query.get(session['user_id'])
    messages = Message.query.filter_by(recipient_id=student.id).order_by(Message.created_at.desc()).all()
    for msg in messages:
        msg.is_read = True
    db.session.commit()
    return jsonify([{'id': m.id, 'sender_id': m.sender_id, 'content': m.content, 'created_at': m.created_at.isoformat()} for m in messages])


@app.route('/api/student/labs')
@login_required
def get_student_labs():
    labs = Lab.query.all()
    return jsonify([{'id': l.id, 'name': l.name, 'location': l.location, 'capacity': l.capacity} for l in labs])


@app.route('/api/student/interactive-classes')
@login_required
def get_student_interactive():
    classes = InteractiveClass.query.all()
    return jsonify([{'id': c.id, 'name': c.name, 'location': c.location, 'capacity': c.capacity} for c in classes])


# ============= TEACHER DASHBOARD =============

@app.route('/teacher')
@role_required('teacher')
def teacher_dashboard():
    teacher = Teacher.query.get(session['user_id'])
    pending_bookings = LabBooking.query.filter_by(teacher_id=teacher.id, status='pending').count()
    unread_messages = Message.query.filter_by(recipient_id=teacher.id, is_read=False).count()
    return render_template('teacher_dash.html', pending_bookings=pending_bookings, unread_messages=unread_messages)


@app.route('/api/teacher/profile', methods=['GET', 'PUT'])
@role_required('teacher')
def teacher_profile():
    teacher = Teacher.query.get(session['user_id'])
    if request.method == 'GET':
        return jsonify({
            'full_name': teacher.full_name,
            'email': teacher.email,
            'subject': teacher.subject,
            'department': teacher.department,
            'cabin_location': teacher.cabin_location,
            'timetable': enrich_timetable_entries(parse_timetable(teacher.timetable)) if teacher.timetable else None,
            'current_class': find_current_timetable_entry(teacher),
            'profile_photo_url': url_for('static', filename=teacher.profile_photo) if teacher.profile_photo else None,
            'manual_status': teacher.status,
            'auto_status': get_current_status_from_timetable(teacher)
        })
    elif request.method == 'PUT':
        data = request.get_json()
        teacher.subject = data.get('subject', teacher.subject)
        teacher.department = data.get('department', teacher.department)
        teacher.cabin_location = data.get('cabin_location', teacher.cabin_location)
        teacher.timetable = data.get('timetable', teacher.timetable)
        db.session.commit()
        return jsonify({'message': 'Profile updated'}), 200


@app.route('/api/teacher/upload-photo', methods=['POST'])
@role_required('teacher')
def upload_teacher_photo():
    if 'photo' not in request.files:
        return jsonify({'error': 'No photo'}), 400
    file = request.files['photo']
    if file.filename == '':
        return jsonify({'error': 'No file'}), 400
    if file and file.filename.rsplit('.', 1)[1].lower() in ['jpg', 'jpeg', 'png', 'gif']:
        teacher = Teacher.query.get(session['user_id'])
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"teacher_{teacher.id}_{secrets.token_hex(8)}.{ext}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        teacher.profile_photo = f'uploads/{filename}'
        db.session.commit()
        return jsonify({'photo_url': url_for('static', filename=teacher.profile_photo)}), 200
    return jsonify({'error': 'Invalid file'}), 400


@app.route('/api/teacher/bookings')
@role_required('teacher')
def get_teacher_bookings():
    teacher = Teacher.query.get(session['user_id'])
    bookings = LabBooking.query.filter_by(teacher_id=teacher.id).all()
    return jsonify([{
        'id': b.id,
        'lab_id': b.lab_id,
        'lab_name': b.lab.name if b.lab else '',
        'date': b.booking_date.isoformat() if b.booking_date else None,
        'start_time': str(b.start_time) if b.start_time else None,
        'end_time': str(b.end_time) if b.end_time else None,
        'status': b.status
    } for b in bookings])


@app.route('/api/teacher/interactive-bookings')
@role_required('teacher')
def get_teacher_interactive_bookings():
    teacher = Teacher.query.get(session['user_id'])
    bookings = InteractiveClassBooking.query.filter_by(teacher_id=teacher.id).all()
    return jsonify([{
        'id': b.id,
        'class_id': b.class_id,
        'class_name': b.interactive_class.name if b.interactive_class else '',
        'date': b.booking_date.isoformat() if b.booking_date else None,
        'start_time': str(b.start_time) if b.start_time else None,
        'end_time': str(b.end_time) if b.end_time else None,
        'status': b.status
    } for b in bookings])


@app.route('/api/teacher/book-lab', methods=['POST'])
@role_required('teacher')
def book_lab():
    data = request.get_json()
    teacher = Teacher.query.get(session['user_id'])
    booking = LabBooking(
        teacher_id=teacher.id,
        lab_id=data['lab_id'],
        booking_date=datetime.strptime(data['date'], '%Y-%m-%d'),
        start_time=datetime.strptime(data['start_time'], '%H:%M').time(),
        end_time=datetime.strptime(data['end_time'], '%H:%M').time(),
        status='pending'
    )
    db.session.add(booking)
    db.session.commit()
    return jsonify({'id': booking.id}), 201


@app.route('/api/teacher/book-interactive', methods=['POST'])
@role_required('teacher')
def book_interactive():
    data = request.get_json()
    teacher = Teacher.query.get(session['user_id'])
    booking = InteractiveClassBooking(
        teacher_id=teacher.id,
        class_id=data['class_id'],
        booking_date=datetime.strptime(data['date'], '%Y-%m-%d'),
        start_time=datetime.strptime(data['start_time'], '%H:%M').time(),
        end_time=datetime.strptime(data['end_time'], '%H:%M').time(),
        status='pending'
    )
    db.session.add(booking)
    db.session.commit()
    return jsonify({'id': booking.id}), 201


@app.route('/api/teacher/confirm-booking/<int:booking_id>', methods=['PUT'])
@role_required('teacher')
def confirm_lab_booking(booking_id):
    booking = LabBooking.query.get_or_404(booking_id)
    booking.status = 'confirmed'
    db.session.commit()
    return jsonify({'message': 'Booking confirmed'}), 200


@app.route('/api/teacher/cancel-booking/<int:booking_id>', methods=['DELETE'])
@role_required('teacher')
def cancel_lab_booking(booking_id):
    booking = LabBooking.query.get_or_404(booking_id)
    booking.status = 'cancelled'
    db.session.commit()
    return jsonify({'message': 'Booking cancelled'}), 200


@app.route('/api/teacher/messages')
@role_required('teacher')
def get_teacher_messages():
    teacher = Teacher.query.get(session['user_id'])
    messages = Message.query.filter_by(recipient_id=teacher.id).order_by(Message.created_at.desc()).all()
    for msg in messages:
        msg.is_read = True
    db.session.commit()
    return jsonify([{'id': m.id, 'sender_id': m.sender_id, 'content': m.content, 'created_at': m.created_at.isoformat()} for m in messages])


@app.route('/api/teacher/notifications')
@role_required('teacher')
def get_teacher_notifications():
    teacher = Teacher.query.get(session['user_id'])
    notifications = Notification.query.filter_by(recipient_id=teacher.id, is_read=False).order_by(Notification.created_at.desc()).all()
    payload = []
    for note in notifications:
        data = {}
        try:
            data = json.loads(note.data) if note.data else {}
        except:
            data = {}
        payload.append({
            'id': note.id,
            'type': note.message_type,
            'title': note.title,
            'message': note.body,
            'data': data,
            'booking_id': data.get('booking_id')
        })
        note.is_read = True
    db.session.commit()
    return jsonify(payload)


@app.route('/api/teacher/notifications/count', methods=['GET'])
@role_required('teacher')
def get_teacher_notification_count():
    teacher = Teacher.query.get(session['user_id'])
    unread_count = Notification.query.filter_by(recipient_id=teacher.id, is_read=False).count()
    return jsonify({'unread': unread_count})


@app.route('/api/user/change-email', methods=['PUT'])
@login_required
def change_email():
    data = request.get_json()
    new_email = data.get('new_email')
    if User.query.filter_by(email=new_email).first():
        return jsonify({'error': 'Email already in use'}), 400
    user = User.query.get(session['user_id'])
    user.email = new_email
    db.session.commit()
    return jsonify({'message': 'Email updated'}), 200


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Server error'}), 500


# Vercel: expose the WSGI app directly — no handler wrapper needed.
# @vercel/python finds the `app` variable automatically.
with app.app_context():
    ensure_db_schema()


if __name__ == '__main__':
    with app.app_context():
        ensure_db_schema()
    app.run(debug=False, port=5000)
