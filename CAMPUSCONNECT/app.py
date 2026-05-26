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

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, Response
import os
# Ensure site-packages is preferred on sys.path so installed packages aren't shadowed
import site
try:
    site_pkgs = site.getsitepackages()
except Exception:
    site_pkgs = []
for sp in site_pkgs:
    if os.path.isdir(sp) and sp not in sys.path:
        sys.path.insert(0, sp)
        break
# Import Session; handle local-folder shadowing of package by trying a site-packages fallback
try:
    from flask_session import Session
    # If the imported module is local (folder in project), prefer installed package
    try:
        _fs_mod = __import__('flask_session')
        _fs_file = getattr(_fs_mod, '__file__', '') or ''
        if 'flask_session' in _fs_file and ('CAMPUSCONNECT' in _fs_file or 'flask_session' in _fs_file.split(os.sep)[0]):
            raise ImportError('Local flask_session detected; using fallback')
    except Exception:
        pass
except Exception:
    import importlib, site
    Session = None
    # Try to find flask_session inside site-packages and load it explicitly
    try:
        site_paths = []
        try:
            site_paths.extend(site.getsitepackages())
        except Exception:
            pass
        try:
            site_paths.append(site.getusersitepackages())
        except Exception:
            pass
        for sp in site_paths:
            candidate = os.path.join(sp, 'flask_session')
            if os.path.isdir(candidate):
                try:
                    spec = importlib.util.spec_from_file_location('flask_session', os.path.join(candidate, '__init__.py'))
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    Session = getattr(mod, 'Session', None)
                    break
                except Exception:
                    continue
    except Exception:
        Session = None
    if Session is None:
        raise ImportError("flask_session import failed: a local 'flask_session' directory in the project is shadowing the installed Flask-Session package. Please rename or remove the local folder 'flask_session' so the installed package can be imported.")
from functools import wraps
from datetime import datetime, timedelta, date, time
from sqlalchemy import inspect, text, or_
from werkzeug.utils import secure_filename
import os
import json
from models import db, User, Student, Teacher, Lab, LabBooking, InteractiveClass, InteractiveClassBooking, Message, Notification, SystemLog
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


def allowed_file(filename):
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


# ============= TIMETABLE & STATUS LOGIC =============

def parse_timetable(timetable_json):
    """Parse and validate teacher timetable JSON format"""
    if not timetable_json:
        return None
    try:
        if isinstance(timetable_json, str):
            import json
            return json.loads(timetable_json)
        return timetable_json
    except:
        return None


def resolve_timetable_location_resource(location):
    """Resolve a timetable location to a lab or interactive class resource."""
    if not location or not isinstance(location, str):
        return None

    try:
        lab = Lab.query.filter(or_(
            Lab.name.ilike(f'%{location}%'),
            Lab.location.ilike(f'%{location}%')
        )).first()
        if lab:
            return {
                'resource_type': 'lab',
                'resource_id': lab.id,
                'resource_name': lab.name,
                'resource_location': lab.location
            }

        interactive = InteractiveClass.query.filter(or_(
            InteractiveClass.name.ilike(f'%{location}%'),
            InteractiveClass.location.ilike(f'%{location}%')
        )).first()
        if interactive:
            return {
                'resource_type': 'interactive_class',
                'resource_id': interactive.id,
                'resource_name': interactive.name,
                'resource_location': interactive.location
            }

        return None
    except:
        return None


def enrich_timetable_entries(timetable):
    """Enrich timetable entries with linked lab or interactive class details."""
    if not timetable or not isinstance(timetable, dict):
        return timetable

    enriched = {}
    for day, entries in timetable.items():
        if isinstance(entries, list):
            enriched[day] = []
            for cls in entries:
                entry = dict(cls) if isinstance(cls, dict) else {}
                resource = resolve_timetable_location_resource(entry.get('location'))
                if resource:
                    entry.update(resource)
                enriched[day].append(entry)
        else:
            enriched[day] = entries
    return enriched


def find_current_timetable_entry(teacher):
    """Return the current timetable entry if the teacher is in class now."""
    timetable = parse_timetable(teacher.timetable)
    if not timetable:
        return None

    try:
        now = datetime.now()
        current_day = now.strftime('%A').lower()
        current_time = now.time()

        if current_day in timetable:
            classes = timetable[current_day]
            if not isinstance(classes, list):
                return None

            for cls in classes:
                start_str = cls.get('start', '')
                end_str = cls.get('end', '')
                if start_str and end_str:
                    start_time = datetime.strptime(start_str, '%H:%M').time()
                    end_time = datetime.strptime(end_str, '%H:%M').time()
                    if start_time <= current_time < end_time:
                        entry = dict(cls)
                        resource = resolve_timetable_location_resource(entry.get('location'))
                        if resource:
                            entry.update(resource)
                        return entry

        return None
    except:
        return None


def get_current_status_from_timetable(teacher):
    """Auto-calculate teacher status based on timetable and current time."""
    timetable = parse_timetable(teacher.timetable)
    if not timetable:
        return teacher.status

    try:
        now = datetime.now()
        current_day = now.strftime('%A').lower()
        current_time = now.time()

        if current_day in timetable:
            classes = timetable[current_day]
            if not isinstance(classes, list):
                return teacher.status

            for cls in classes:
                start_str = cls.get('start', '')
                end_str = cls.get('end', '')
                if start_str and end_str:
                    start_time = datetime.strptime(start_str, '%H:%M').time()
                    end_time = datetime.strptime(end_str, '%H:%M').time()
                    if start_time <= current_time < end_time:
                        return 'in_class'

        # If a teacher manually set busy/away outside scheduled classes, keep that.
        if teacher.status in ['busy', 'away']:
            return teacher.status

        return 'free'
    except:
        return teacher.status


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
    total_interactive_classes = InteractiveClass.query.count()
    active_lab_bookings = LabBooking.query.filter_by(status='pending').count()
    active_interactive_bookings = InteractiveClassBooking.query.filter_by(status='pending').count()
    
    stats = {
        'total_users': total_users,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_labs': total_labs,
        'total_interactive_classes': total_interactive_classes,
        'active_bookings': active_lab_bookings + active_interactive_bookings
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
        'created_at': u.created_at.strftime('%Y-%m-%d %H:%M'),
        'profile_photo': u.profile_photo,
        'profile_photo_url': url_for('static', filename=u.profile_photo) if u.profile_photo else None,
        'cabin_block': getattr(u, 'cabin_block', None),
        'cabin_floor': getattr(u, 'cabin_floor', None),
        'cabin_room': getattr(u, 'cabin_room', None),
        'cabin_location': getattr(u, 'cabin_location', None)
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


@app.route('/api/admin/delete-lab/<int:lab_id>', methods=['DELETE'])
@role_required('admin')
def delete_lab(lab_id):
    lab = Lab.query.get(lab_id)
    if not lab:
        return jsonify({'success': False, 'message': 'Lab not found'}), 404
    db.session.delete(lab)
    db.session.commit()
    return jsonify({'success': True}), 200


@app.route('/api/admin/delete-interactive-class/<int:class_id>', methods=['DELETE'])
@role_required('admin')
def delete_interactive_class(class_id):
    interactive_class = InteractiveClass.query.get(class_id)
    if not interactive_class:
        return jsonify({'success': False, 'message': 'Interactive class not found'}), 404
    db.session.delete(interactive_class)
    db.session.commit()
    return jsonify({'success': True}), 200


@app.route('/api/admin/delete-user/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False}), 404
    
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/logs')
@role_required('admin')
def get_system_logs():
    logs = SystemLog.query.order_by(SystemLog.created_at.desc()).limit(100).all()
    return jsonify([{
        'id': log.id,
        'action': log.action,
        'user_id': log.user_id,
        'details': log.details,
        'created_at': log.created_at.strftime('%Y-%m-%d %H:%M')
    } for log in logs])


@app.route('/api/admin/export-logs')
@role_required('admin')
def export_logs():
    logs = SystemLog.query.order_by(SystemLog.created_at.desc()).all()
    from io import StringIO
    import csv

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['id', 'created_at', 'action', 'user_id', 'details'])
    for log in logs:
        writer.writerow([
            log.id,
            log.created_at.strftime('%Y-%m-%d %H:%M'),
            log.action,
            log.user_id or '',
            (log.details or '').replace('\n', ' ')
        ])

    output = si.getvalue()
    return Response(output, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=system_logs.csv'})


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
        'cabin_block': t.cabin_block,
        'cabin_floor': t.cabin_floor,
        'cabin_room': t.cabin_room,
        'cabin_location': t.cabin_location,  # legacy field
        'profile_photo': t.profile_photo,
        'profile_photo_url': url_for('static', filename=t.profile_photo) if t.profile_photo else None,
        'status': get_current_status_from_timetable(t),
        'timetable': enrich_timetable_entries(parse_timetable(t.timetable)) if t.timetable else None,
        'current_class': find_current_timetable_entry(t),
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
    for message in messages:
        if not message.is_read:
            message.is_read = True
    db.session.commit()
    
    return jsonify([{
        'id': m.id,
        'sender_name': m.sender.full_name,
        'subject': m.subject,
        'body': m.body,
        'is_read': m.is_read,
        'created_at': m.created_at.strftime('%Y-%m-%d %H:%M')
    } for m in messages])


@app.route('/api/student/labs')
@login_required
def get_student_labs():
    labs = Lab.query.all()
    # Provide minimal information to students and teachers
    return jsonify([{
        'id': l.id,
        'name': l.name,
        'status': l.status
    } for l in labs])


@app.route('/api/student/interactive-classes')
@login_required
def get_student_interactive():
    classes = InteractiveClass.query.all()
    # Provide minimal information to students and teachers
    return jsonify([{
        'id': c.id,
        'name': c.name,
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
        teacher.cabin_block = data.get('cabin_block', teacher.cabin_block)
        teacher.cabin_floor = data.get('cabin_floor', teacher.cabin_floor)
        teacher.cabin_room = data.get('cabin_room', teacher.cabin_room)
        # Build legacy cabin_location for backward compatibility
        if teacher.cabin_block or teacher.cabin_floor or teacher.cabin_room:
            parts = [p for p in [teacher.cabin_block, teacher.cabin_floor, teacher.cabin_room] if p]
            teacher.cabin_location = ', '.join(parts) if parts else None
        teacher.timetable = data.get('timetable', teacher.timetable)
        db.session.commit()
        return jsonify({'success': True}), 200
    
    return jsonify({
        'full_name': teacher.full_name,
        'email': teacher.email,
        'subject': teacher.subject,
        'department': teacher.department,
        'cabin_block': teacher.cabin_block,
        'cabin_floor': teacher.cabin_floor,
        'cabin_room': teacher.cabin_room,
        'cabin_location': teacher.cabin_location,
        'timetable': enrich_timetable_entries(parse_timetable(teacher.timetable)) if teacher.timetable else None,
        'current_class': find_current_timetable_entry(teacher),
        'profile_photo': teacher.profile_photo,
        'profile_photo_url': url_for('static', filename=teacher.profile_photo) if teacher.profile_photo else None,
        'manual_status': teacher.status,
        'auto_status': get_current_status_from_timetable(teacher)
    })


@app.route('/api/teacher/upload-photo', methods=['POST'])
@role_required('teacher')
def upload_teacher_photo():
    if 'photo' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400

    file = request.files['photo']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Unsupported file type'}), 400

    teacher = Teacher.query.get(session['user_id'])
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = secure_filename(f"teacher_{teacher.id}_{secrets.token_hex(8)}.{ext}")
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    teacher.profile_photo = f'uploads/{filename}'
    db.session.commit()
    
    return jsonify({'success': True, 'profile_photo': teacher.profile_photo}), 200


@app.route('/api/admin/teacher/<int:teacher_id>/upload-photo', methods=['POST'])
@role_required('admin')
def admin_upload_teacher_photo(teacher_id):
    if 'photo' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400

    file = request.files['photo']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Unsupported file type'}), 400

    teacher = Teacher.query.get(teacher_id)
    if not teacher:
        return jsonify({'success': False, 'message': 'Teacher not found'}), 404

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = secure_filename(f"teacher_{teacher.id}_{secrets.token_hex(8)}.{ext}")
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    teacher.profile_photo = f'uploads/{filename}'
    db.session.commit()

    log = SystemLog(action='admin_update_teacher_photo', user_id=session['user_id'], details=f'Admin updated photo for teacher {teacher.email}')
    db.session.add(log)
    db.session.commit()

    return jsonify({'success': True, 'profile_photo': teacher.profile_photo}), 200


@app.route('/api/teacher/timetable', methods=['GET', 'POST'])
@role_required('teacher')
def manage_timetable():
    """Upload/update teacher timetable (JSON format)"""
    teacher = Teacher.query.get(session['user_id'])
    
    if request.method == 'POST':
        data = request.get_json()
        timetable = data.get('timetable')
        
        # Validate timetable format
        if timetable:
            parsed = parse_timetable(timetable)
            if not parsed:
                return jsonify({'success': False, 'message': 'Invalid timetable format. Must be valid JSON.'}), 400
        
        teacher.timetable = timetable if isinstance(timetable, str) else str(timetable) if timetable else None
        db.session.commit()
        
        log = SystemLog(action='timetable_upload', user_id=teacher.id, 
                       details=f'Teacher {teacher.email} uploaded/updated timetable')
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Timetable updated successfully'}), 200
    
    # GET: Return current timetable with linked resources and available location options
    return jsonify({
        'timetable': enrich_timetable_entries(parse_timetable(teacher.timetable)) if teacher.timetable else None,
        'current_status': get_current_status_from_timetable(teacher),
        'labs': [{
            'id': l.id,
            'name': l.name,
            'location': l.location,
            'status': l.status
        } for l in Lab.query.all()],
        'interactive_classes': [{
            'id': c.id,
            'name': c.name,
            'location': c.location,
            'status': c.status
        } for c in InteractiveClass.query.all()]
    })


@app.route('/api/teacher/auto-status', methods=['GET'])
@role_required('teacher')
def get_auto_status():
    """Get auto-calculated status based on current timetable"""
    teacher = Teacher.query.get(session['user_id'])
    status = get_current_status_from_timetable(teacher)
    return jsonify({'status': status, 'auto_calculated': True})


@app.route('/api/teacher/notifications', methods=['GET'])
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
    """Allow logged-in users to change their email (VVCE-only)."""
    data = request.get_json() or {}
    new_email = data.get('email', '').strip()

    if not new_email or not new_email.endswith('@vvce.ac.in'):
        return jsonify({'success': False, 'message': 'Email must end with @vvce.ac.in'}), 400

    existing = User.query.filter_by(email=new_email).first()
    if existing and existing.id != session.get('user_id'):
        return jsonify({'success': False, 'message': 'Email already in use'}), 400

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    user.email = new_email
    db.session.commit()

    # Update session and log
    session['email'] = new_email
    log = SystemLog(action='email_change', user_id=user.id, details=f'Email changed to: {new_email}')
    db.session.add(log)
    db.session.commit()

    return jsonify({'success': True, 'email': new_email}), 200


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
    for message in messages:
        if not message.is_read:
            message.is_read = True
    db.session.commit()
    
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

            teacher = Teacher(
                email='teacher1@vvce.ac.in',
                full_name='Prof. Priya Sharma',
                subject='Computer Science',
                department='CSE',
                cabin_location='Block A, Room 101'
            )
            teacher.set_password('teacher123')
            db.session.add(teacher)
            
            # Add sample labs
            lab1 = Lab(name='AI Lab', location='Block A, Floor 2', capacity=30)
            lab2 = Lab(name='Database Lab', location='Block B, Floor 1', capacity=25)
            
            # Add sample interactive classes
            ic1 = InteractiveClass(name='Interactive Classroom 1', location='Block C, Floor 1', capacity=60)
            
            db.session.add_all([lab1, lab2, ic1])
            db.session.commit()
            print("Sample data added! Admin and teacher accounts created.")


def ensure_db_schema():
    inspector = inspect(db.engine)

    if 'lab_booking' in inspector.get_table_names():
        lab_columns = [col['name'] for col in inspector.get_columns('lab_booking')]
        if 'warning_sent' not in lab_columns:
            db.session.execute(text('ALTER TABLE lab_booking ADD COLUMN warning_sent BOOLEAN DEFAULT 0'))
            db.session.commit()
        if 'started_sent' not in lab_columns:
            db.session.execute(text('ALTER TABLE lab_booking ADD COLUMN started_sent BOOLEAN DEFAULT 0'))
            db.session.commit()

    if 'interactive_class_booking' in inspector.get_table_names():
        interactive_columns = [col['name'] for col in inspector.get_columns('interactive_class_booking')]
        if 'warning_sent' not in interactive_columns:
            db.session.execute(text('ALTER TABLE interactive_class_booking ADD COLUMN warning_sent BOOLEAN DEFAULT 0'))
            db.session.commit()
        if 'started_sent' not in interactive_columns:
            db.session.execute(text('ALTER TABLE interactive_class_booking ADD COLUMN started_sent BOOLEAN DEFAULT 0'))
            db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_db_schema()
    app.run(debug=True, host='0.0.0.0', port=5000)
