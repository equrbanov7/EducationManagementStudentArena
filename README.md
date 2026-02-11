# 🎓 EMS Arena - Educational Management System

**EMS Arena** is a comprehensive Django-based Learning Management System (LMS) designed for universities and educational institutions. It provides tools for course management, exam administration, assignments, lab work, blog content, and real-time live quizzes.

---

## ✨ Features

### 📚 **Course Management**
- Create and manage courses with topics and resources
- Organize content by weeks/modules
- Upload course materials (PDFs, videos, links)
- Track student enrollment and groups

### 📝 **Exam System**
- **Test Exams**: Multiple choice questions with auto-grading
- **Written Exams**: Essay/practical questions with teacher review
- Question bank with bulk import (Word/PDF/TXT)
- Random question selection
- Time limits and attempt tracking
- Anonymous grading mode
- Paint/drawing tool for problem-solving questions

### 📋 **Assignments & Projects**
- Create assignments with deadlines
- Multiple attempt support
- File upload and link submission
- Teacher grading and feedback
- Group-based assignment distribution

### 🧪 **Lab Work Management**
- Create lab exercises with question blocks
- Random question assignment per student
- Deterministic shuffle (same questions on refresh)
- Time limits per block
- File and text submissions
- Teacher grading interface

### 🎮 **Live Exam (Kahoot-style)**
- Real-time multiplayer quizzes
- QR code lobby system
- Leaderboards and scoring
- WebSocket-powered updates
- Host controls (question flow, reveal answers)

### 📰 **Blog & Content**
- Create and publish blog posts
- Category management
- Comments and ratings
- Subscription system with email verification

### 👥 **User Management**
- Role-based access (Teacher, Student, Assistant, Moderator)
- Email verification (OTP)
- Student groups and bulk enrollment
- Password reset

---

## 🛠️ Technology Stack

### **Backend**
- **Django 5.2+** - Web framework
- **PostgreSQL** - Database (with pgAdmin support)
- **Redis** - WebSocket & caching
- **Django Channels** - WebSocket support
- **Celery** - Background tasks (optional)

### **Frontend**
- **Bootstrap 5** - UI framework
- **Font Awesome** - Icons
- **Vanilla JavaScript** - Interactive features
- **AJAX** - Dynamic updates

### **Additional Libraries**
- `python-docx` - Word document processing
- `pypdf` - PDF parsing
- `Pillow` - Image processing
- `qrcode` - QR code generation
- `python-dotenv` - Environment management
- `whitenoise` - Static file serving
- `gunicorn` - Production server

---

## 🚀 Quick Start

### **Prerequisites**

- Python 3.11.6
- PostgreSQL 16+
- Redis Server
- Git

---

### **1. Clone the Repository**

```bash
git clone https://github.com/your-username/emsarena.git
cd emsarena
```

---

### **2. Set Up Python Environment**

#### **Option A: Using pyenv (Recommended)**

```bash
pyenv install 3.11.6
pyenv local 3.11.6
```

#### **Option B: Using system Python**

```bash
python --version  # Should be 3.11+
```

---

### **3. Create Virtual Environment**

```bash
python -m venv venv
```

Activate it:

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

---

### **4. Install Dependencies**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### **5. Set Up Environment Variables**

Create a `.env` file in the project root:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# Database (PostgreSQL)
DATABASE_URL=postgresql://username:password@localhost:5432/emsarena

# Redis (for WebSockets)
REDIS_URL=redis://127.0.0.1:6379

# Email Configuration (Gmail SMTP example)
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com

# Network (LAN access - optional)
LAN_HOST=192.168.1.100:8000
CSRF_TRUSTED_ORIGINS=http://192.168.1.100:8000,http://localhost:8000

# Site URL
SITE_URL=http://127.0.0.1:8000
```

**⚠️ Security Note:** Never commit `.env` to version control!

---

### **6. Set Up PostgreSQL Database**

#### **Option A: Using Docker (Recommended)**

```bash
# Start PostgreSQL + pgAdmin containers
docker-compose up -d
```

Default credentials:
- **PostgreSQL**: `localhost:5432` (user: `admin`, password: `admin`, db: `emsarena`)
- **pgAdmin**: `http://localhost:5050` (email: `admin@admin.com`, password: `admin`)

#### **Option B: Manual PostgreSQL Setup**

```bash
# Create database
createdb emsarena

# Or via psql
psql -U postgres
CREATE DATABASE emsarena;
\q
```

---

### **7. Set Up Redis**

#### **Using Docker:**

```bash
docker run -d -p 6379:6379 --name emsarena-redis redis:alpine
```

#### **Using Homebrew (macOS):**

```bash
brew install redis
brew services start redis
```

#### **Verify Redis:**

```bash
redis-cli ping
# Should return: PONG
```

---

### **8. Run Migrations**

```bash
python manage.py makemigrations
python manage.py migrate
```

---

### **9. Create Superuser**

```bash
python manage.py createsuperuser
```

Follow the prompts to set username, email, and password.

---

### **10. Create User Groups (Required)**

```bash
python manage.py shell
```

```python
from django.contrib.auth.models import Group

# Create groups
Group.objects.create(name='teacher')
Group.objects.create(name='student')
Group.objects.create(name='assistant_teacher')
Group.objects.create(name='moderator')

exit()
```

---

### **11. Run the Development Server**

```bash
python manage.py runserver
```

**Access the application:**
- Frontend: http://127.0.0.1:8000/
- Admin Panel: http://127.0.0.1:8000/admin/

---

### **12. (Optional) Run on LAN Network**

To access from other devices on your network:

```bash
python manage.py runserver 0.0.0.0:8000
```

Find your local IP:
```bash
# macOS/Linux
ifconfig | grep "inet "

# Windows
ipconfig
```

Then access via: `http://YOUR_LOCAL_IP:8000`

---

## 📁 Project Structure

```
emsarena/
├── accounts/               # User authentication & roles
├── assignments/            # Assignment management
├── blog/                   # Blog & main exam system
├── courses/                # Course & topic management
├── labs/                   # Lab work system
├── liveExam/              # Real-time live quizzes (WebSocket)
├── projects/              # Course projects
├── emsarena/              # Main project settings
│   ├── settings.py        # Django configuration
│   ├── urls.py            # Root URL routing
│   ├── asgi.py            # ASGI for WebSockets
│   ├── static/            # Global static files
│   └── templates/         # Base templates
├── media/                 # User uploads
├── staticfiles/           # Collected static files (production)
├── .env                   # Environment variables (create this)
├── .env.example           # Example env file
├── docker-compose.yml     # Docker setup
├── manage.py              # Django management script
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

---

## 🎯 Usage Guide

### **For Teachers:**

1. **Create a Course:**
   - Navigate to "Kurslarım" → "Yeni Kurs Yarat"
   - Add topics and resources

2. **Add Students:**
   - Go to Course Dashboard → "Üzvlər"
   - Add students individually or by group

3. **Create Exams:**
   - "İmtahanlarım" → "Yeni İmtahan Yarat"
   - Use question bank for bulk import
   - Configure time limits and access controls

4. **Create Assignments/Labs:**
   - From Course Dashboard
   - Set deadlines and attempt limits
   - Assign to specific students/groups

5. **Grade Work:**
   - View pending submissions in "Pending Work"
   - Provide feedback and scores

6. **Live Quiz:**
   - Create exam → "Canlı İmtahan Başlat"
   - Share QR code/PIN with students
   - Control question flow in real-time

---

### **For Students:**

1. **Register & Join Courses:**
   - Create account with email verification
   - Wait for teacher to add you to courses

2. **Take Exams:**
   - "İmtahanlar" → View available exams
   - Check time limits and attempt counts
   - Submit before deadline

3. **Submit Assignments:**
   - Course Dashboard → View assignments
   - Upload files or provide links
   - Track submission status

4. **Complete Labs:**
   - View assigned questions
   - Submit answers (text/file)
   - Check grades and feedback

5. **Join Live Quiz:**
   - Scan QR code or enter PIN
   - Choose nickname and avatar
   - Answer questions in real-time

---

## 🔧 Advanced Configuration

### **Custom Template Tags**

Project includes custom template tags:

```python
# labs/templatetags/lab_filters.py
@register.filter
def get_item(dictionary, key):
    """Dictionary lookup: {{ dict|get_item:key }}"""
    return dictionary.get(int(key))

@register.filter
def multiply(value, arg):
    """Multiply: {{ value|multiply:2 }}"""
    return value * arg

@register.filter
def percentage(value, total):
    """Percentage: {{ value|percentage:total }}"""
    return round((value / total) * 100, 1) if total else 0
```

---

### **WebSocket Configuration**

WebSocket support requires Redis. Configuration in `settings.py`:

```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}
```

To run with WebSocket support:

```bash
# Start Daphne (ASGI server)
daphne -b 0.0.0.0 -p 8000 emsarena.asgi:application
```

---

### **Email Configuration**

For Gmail SMTP:

1. Enable 2-Factor Authentication
2. Generate App Password
3. Update `.env`:

```env
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-16-char-app-password
```

---

## 🐳 Docker Deployment

### **Development with Docker Compose:**

```bash
# Start all services (PostgreSQL + Redis + pgAdmin)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

---

### **Production Deployment**

#### **Using Gunicorn:**

```bash
# Collect static files
python manage.py collectstatic --noinput

# Run with Gunicorn
gunicorn emsarena.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

#### **Using Daphne (with WebSockets):**

```bash
daphne -b 0.0.0.0 -p 8000 emsarena.asgi:application
```

---

## 🧪 Testing

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test blog
python manage.py test courses

# Check code coverage
coverage run --source='.' manage.py test
coverage report
```

---

## 📊 Database Management

### **Create Backup:**

```bash
# PostgreSQL dump
pg_dump -U admin emsarena > backup.sql

# Restore
psql -U admin emsarena < backup.sql
```

### **Reset Database:**

```bash
python manage.py flush
python manage.py migrate
python manage.py createsuperuser
```

---

## 🔐 Security Best Practices

1. **Never commit `.env` file**
2. **Use strong SECRET_KEY in production**
3. **Set DEBUG=False in production**
4. **Use HTTPS in production**
5. **Restrict ALLOWED_HOSTS**
6. **Enable CSRF protection**
7. **Use environment variables for sensitive data**
8. **Regular security updates:**

```bash
pip list --outdated
pip install --upgrade <package-name>
```

---

## 🐛 Troubleshooting

### **Common Issues:**

#### **1. Template Filter Not Found**

```
Error: Invalid filter: 'get_item'
```

**Solution:**
- Ensure `labs/templatetags/__init__.py` exists
- Restart Django server (template tags load on startup)
- Check `{% load lab_filters %}` at top of template

---

#### **2. WebSocket Connection Failed**

**Solution:**
- Verify Redis is running: `redis-cli ping`
- Check CHANNEL_LAYERS configuration
- Use Daphne instead of `runserver` for WebSocket support

---

#### **3. Database Connection Error**

**Solution:**
- Verify PostgreSQL is running
- Check DATABASE_URL in `.env`
- Test connection: `psql -U admin -d emsarena`

---

#### **4. Static Files Not Loading**

**Solution:**
```bash
python manage.py collectstatic --noinput
```

In production, configure Nginx/Apache to serve `/static/` and `/media/`

---

## 📚 Documentation

- [Django Documentation](https://docs.djangoproject.com/)
- [Django Channels](https://channels.readthedocs.io/)
- [Bootstrap 5](https://getbootstrap.com/docs/5.0/)
- [PostgreSQL](https://www.postgresql.org/docs/)

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 👨‍💻 Author

**Elvin Qurbanov**

- 🎓 University Lecturer
- 💻 Full-Stack Developer
- 🔬 Researcher

📧 Email: [your-email@example.com]
🔗 LinkedIn: [your-linkedin]
🐙 GitHub: [your-github]

---

## 🙏 Acknowledgments

- Django community for the excellent framework
- Bootstrap team for the UI toolkit
- All contributors and testers

---

## 📅 Version History

- **v2.0.0** (2026-02-10) - Lab system, live exams, enhanced UI
- **v1.5.0** (2025-12-01) - Course management system
- **v1.0.0** (2025-09-15) - Initial release

---

## 💡 Future Roadmap

- [ ] Mobile app (React Native)
- [ ] Video conferencing integration
- [ ] AI-powered question generation
- [ ] Analytics dashboard
- [ ] Gamification system
- [ ] Multi-language support
- [ ] API for third-party integrations

---

**⭐ If you find this project useful, please consider giving it a star on GitHub!**


# CI
# 1. Əvvəl isort (Black profili ilə)
isort --profile black .

# 2. Sonra Black
black .

# 3. Yoxla - heç bir dəyişiklik olmamalı
isort --check --profile black .
black --check .