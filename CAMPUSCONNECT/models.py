from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    """Base User model"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, student, teacher
    department = db.Column(db.String(100))
    profile_photo = db.Column(db.String(255), default=None)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    __mapper_args__ = {
        'polymorphic_on': role,
        'polymorphic_identity': 'user'
    }


class Student(User):
    """Student model inheriting from User"""
    semester = db.Column(db.Integer)
    roll_number = db.Column(db.String(50), unique=True)
    
    messages_sent = db.relationship('Message', backref='sender', lazy=True, foreign_keys='Message.sender_id')
    messages_received = db.relationship('Message', backref='recipient', lazy=True, foreign_keys='Message.recipient_id')

    __mapper_args__ = {
        'polymorphic_identity': 'student'
    }


class Teacher(User):
    """Teacher model inheriting from User"""
    subject = db.Column(db.String(120))
    cabin_location = db.Column(db.String(255))  # Legacy: full location string
    cabin_block = db.Column(db.String(50))  # e.g., "Block A"
    cabin_floor = db.Column(db.String(50))  # e.g., "Floor 2"
    cabin_room = db.Column(db.String(50))  # e.g., "Room 201"
    timetable = db.Column(db.Text)  # JSON format
    status = db.Column(db.String(20), default='free')  # free, busy, away, in_class
    status_updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    lab_bookings = db.relationship('LabBooking', backref='teacher', lazy=True)
    interactive_bookings = db.relationship('InteractiveClassBooking', backref='teacher', lazy=True)
    messages_sent = db.relationship('Message', backref='teacher_sender', lazy=True, foreign_keys='Message.sender_id')
    messages_received = db.relationship('Message', backref='teacher_recipient', lazy=True, foreign_keys='Message.recipient_id')

    __mapper_args__ = {
        'polymorphic_identity': 'teacher'
    }


class Admin(User):
    """Admin model inheriting from User"""

    __mapper_args__ = {
        'polymorphic_identity': 'admin'
    }


class Lab(db.Model):
    """Lab model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    capacity = db.Column(db.Integer)
    status = db.Column(db.String(20), default='free')  # free, engaged, maintenance
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    bookings = db.relationship('LabBooking', backref='lab', lazy=True, cascade='all, delete-orphan')


class LabBooking(db.Model):
    """Lab Booking model"""
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lab_id = db.Column(db.Integer, db.ForeignKey('lab.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    booking_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, engaged, cancelled
    warning_sent = db.Column(db.Boolean, default=False)
    started_sent = db.Column(db.Boolean, default=False)
    confirmed_at = db.Column(db.DateTime)
    engaged_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<LabBooking {self.id} - {self.lab.name} at {self.booking_time}>'


class InteractiveClass(db.Model):
    """Interactive Class model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    capacity = db.Column(db.Integer)
    status = db.Column(db.String(20), default='free')  # free, engaged, maintenance
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    bookings = db.relationship('InteractiveClassBooking', backref='interactive_class', lazy=True, cascade='all, delete-orphan')


class InteractiveClassBooking(db.Model):
    """Interactive Class Booking model"""
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    interactive_class_id = db.Column(db.Integer, db.ForeignKey('interactive_class.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    booking_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, engaged, cancelled
    warning_sent = db.Column(db.Boolean, default=False)
    started_sent = db.Column(db.Boolean, default=False)
    confirmed_at = db.Column(db.DateTime)
    engaged_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Message(db.Model):
    """Message model for student-teacher communication"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(255))
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    
    replies = db.relationship('Message', backref=db.backref('original_message', remote_side=[id]), lazy=True)


class Notification(db.Model):
    """Notification model for teacher booking reminders"""
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_type = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(255), default='')
    body = db.Column(db.Text, nullable=False)
    data = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SystemLog(db.Model):
    """System logging for admin analytics"""
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
