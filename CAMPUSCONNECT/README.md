# 🏫 CAMPUSCONNECT - Smart Campus Management System

**CAMPUSCONNECT** is a comprehensive campus management system designed for Vidyavardhaka College of Engineering (VVCE). It seamlessly integrates teacher tracking, lab booking automation, and real-time student-teacher communication.

---

## 🚀 Quick Start Guide

### 1. **Prerequisites**
- Python 3.8 or higher
- pip (Python package installer)
- Git (optional)

### 2. **Clone/Download the Project**
```bash
cd CAMPUSCONNECT
```

### 3. **Create a Virtual Environment**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. **Install Dependencies**
```bash
pip install -r requirements.txt
```

### 5. **Initialize the Database**
```bash
# This will create database.db and add sample data
python app.py
# Then press Ctrl+C after server starts
```

Or run in Python shell:
```python
from app import app
with app.app_context():
    from models import db
    db.create_all()
    print("Database initialized!")
```

### 6. **Run the Application**
```bash
python app.py
```

The application will be available at: **http://localhost:5000**

---

## 📋 Default Credentials

### Admin Account
- **Email:** `admin@vvce.ac.in`
- **Password:** `admin123`

### Test Accounts (Create via Registration)
- **Student:** Register with any `@vvce.ac.in` email
- **Teacher:** Register with any `@vvce.ac.in` email

---

## 🎯 Core Features

### 👨‍💼 Admin Dashboard
- ✅ User management (add, edit, delete students/teachers)
- ✅ Lab and interactive class management
- ✅ System analytics and monitoring
- ✅ View all bookings and logs

### 👨‍🎓 Student Dashboard
- ✅ 🔍 Smart search to find teachers by name, subject, or department
- ✅ 📍 Real-time teacher location and availability tracking
- ✅ 💬 Direct messaging with teachers
- ✅ 🧪 View available labs and interactive classes

### 👩‍🏫 Teacher Dashboard
- ✅ 👤 Profile management (subject, department, cabin location, timetable)
- ✅ 🟢 Live status updates (Free, Busy, Away, In Class)
- ✅ 💬 Inbox for student messages
- ✅ 📅 Smart lab booking system
- ✅ ⏰ 10-minute & 15-minute automated notifications

---

## ⏰ Smart Lab Booking System (The Magic!)

### How It Works:

**Example Scenario:** A teacher books the AI Lab for **11:30 AM**

#### Step 1: Pre-Booking (11:20 AM)
- Python APScheduler checks all upcoming bookings
- Teacher receives **10-minute warning**: "🔔 Your lab class is about to start in 10 mins. Please confirm the booking."

#### Step 2: Class Starts (11:30 AM)
- Python sends **start notification**: "⏰ Your lab class has started. Please confirm the lab is engaged."

#### Step 3: Confirmation (11:30 AM - 11:45 AM)
- Teacher has **exactly 15 minutes** to click "Confirm & Engage"
  - ✅ **If Clicked:** Lab status turns **Red (Engaged)** - reserved for that teacher
  - ❌ **If Ignored:** At **11:45 AM**, Python **automatically cancels** the booking and frees the lab for others

---

## 📁 Project Structure

```
CAMPUSCONNECT/
│
├── app.py                    # Main Flask application with all routes
├── models.py                 # SQLAlchemy database models
├── tasks.py                  # APScheduler background jobs
├── requirements.txt          # Python dependencies
├── database.db              # SQLite database (created after first run)
│
├── templates/               # HTML templates
│   ├── login.html          # Login & Registration page
│   ├── admin_dash.html     # Admin dashboard
│   ├── student_dash.html   # Student dashboard
│   └── teacher_dash.html   # Teacher dashboard
│
└── static/                  # Frontend assets
    ├── css/
    │   └── style.css       # Global styles & Bootstrap overrides
    ├── js/
    │   └── script.js       # Utility functions & helpers
    └── uploads/            # Teacher profile photos (created dynamically)
```

---

## 🔐 Security Features

### Authentication
- ✅ Password hashing with Werkzeug
- ✅ Session management with Flask-Session
- ✅ Role-based access control (Admin, Student, Teacher)
- ✅ VVCE email validation (`@vvce.ac.in` required)

### Data Protection
- ✅ SQLite database with SQLAlchemy ORM
- ✅ Input validation on all forms
- ✅ CSRF protection via session tokens
- ✅ Secure password requirements (min 6 characters)

---

## 🎨 UI/UX Design

### Color Scheme
- **Primary:** Deep Royal Blue (#1e3a8a)
- **Accent:** Emerald Green (#10b981)
- **Secondary:** Slate Gray (#475569)
- **Background:** Light Sky (#f8fafc)

### Modern Features
- ✅ Glassmorphism cards with soft drop shadows
- ✅ Smooth animations and transitions
- ✅ Responsive design (mobile, tablet, desktop)
- ✅ Clean collapsible sidebars
- ✅ Glowing status indicators

---

## 📊 API Endpoints

### Authentication
- `POST /register` - Register new student/teacher
- `POST /login` - Login user
- `GET /logout` - Logout user

### Admin
- `GET /admin` - Admin dashboard
- `GET /api/admin/users` - Get all users
- `POST /api/admin/labs` - Create new lab
- `GET /api/admin/labs` - Get all labs
- `DELETE /api/admin/delete-user/<id>` - Delete user

### Student
- `GET /student` - Student dashboard
- `GET /api/student/search-teachers` - Search teachers
- `GET /api/student/labs` - Get available labs
- `POST /api/student/message` - Send message to teacher
- `GET /api/student/messages` - Get student's messages

### Teacher
- `GET /teacher` - Teacher dashboard
- `GET /api/teacher/profile` - Get profile
- `PUT /api/teacher/profile` - Update profile
- `PUT /api/teacher/status` - Update status (free, busy, away, in_class)
- `POST /api/teacher/book-lab` - Book a lab
- `GET /api/teacher/bookings` - Get all bookings
- `PUT /api/teacher/confirm-booking/<id>` - Confirm booking as engaged
- `GET /api/teacher/messages` - Get messages from students
- `POST /api/teacher/reply-message/<id>` - Reply to message

---

## 🛠️ Background Tasks (APScheduler)

The system runs **4 automated background jobs** that check every minute:

1. **Lab Warning Notification (10 mins before)**
   - Sends "Your class starts in 10 minutes" alert
   
2. **Lab Start Notification (at exact booking time)**
   - Sends "Class has started, confirm engagement" alert

3. **Auto-Cancel Unconfirmed Labs (15 mins after start)**
   - Automatically cancels booking if teacher didn't confirm
   - Frees the lab for other bookings

4. **Auto-Cancel Interactive Classes**
   - Same logic for interactive classroom bookings

---

## 🧪 Testing the Lab Booking System

### Simulate a Booking:

1. **Login as Teacher**
2. **Go to "Book Lab" Tab**
3. **Select "AI Lab"** from dropdown
4. **Set date to today and time to** `11:30 AM`
5. **Click "Book Lab"** ✅

### See Notifications in Action:

Uncomment this line in `teacher_dash.html` (line ~450):
```javascript
// Uncomment to test notifications
setTimeout(() => showBookingNotification('warning', '🔔 Your lab class is about to start in 10 minutes...', 1), 5000);
setTimeout(() => showBookingNotification('started', '⏰ Your lab class has started...', 1), 20000);
```

This will show mock notifications after 5 and 20 seconds.

---

## 📱 Responsive Design

The system works perfectly on:
- ✅ Desktop computers (1920x1080, 1366x768)
- ✅ Tablets (iPad, Samsung Tab)
- ✅ Mobile phones (iPhone, Android)

Bootstrap 5 ensures automatic responsiveness.

---

## 🐛 Troubleshooting

### "Module not found" error
```bash
pip install -r requirements.txt
```

### "Address already in use" error
```bash
# Change port in app.py
app.run(port=5001)  # Use a different port
```

### "Database locked" error
- Delete `database.db` and restart
- Or close other instances of the app

### APScheduler not working
- Make sure app runs with `python app.py`
- Check console for scheduler startup message

---

## 📞 Support & Documentation

For more information:
- Check inline code comments
- Review API endpoint implementations
- Test with sample data in admin panel

---

## 📝 License

This project is designed for VVCE. All rights reserved.

---

## 🎉 Happy Coding!

**CAMPUSCONNECT** - Making campus management smart, automated, and efficient!

Questions? Check the code comments or review the blueprint document.
