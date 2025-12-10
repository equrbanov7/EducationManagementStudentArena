
# Django Exam & Blog Platform

This project is a Django-based blog and exam management system.  
It includes user authentication, blog posts, comments, exam creation, exam attempts, and result checking.

This guide explains how to set up the project locally using **Python 3.11**, **pyenv**, and a **virtual environment (venv)**.

---

## 🚀 Requirements

Before starting, you should have:

- **Homebrew** (for macOS users)
- **pyenv** → for managing Python versions (optional but recommended)
- **Python 3.11.6**
- **pip** (comes with Python)
- **Git**

---

## 📥 1. Clone the Project

```bash
git clone <repository-url>
cd blogApp
````

Replace `<repository-url>` with your actual Git repository URL.

---

## 🐍 2. (Optional but Recommended) Set Up Python 3.11.6 with pyenv

If you don’t have Python 3.11.6 yet and want to use `pyenv`:

```bash
pyenv install 3.11.6
pyenv local 3.11.6
```

This sets Python 3.11.6 as the local version for this project.

You can verify with:

```bash
python --version
```

It should show something like:

```text
Python 3.11.6
```

---

## 🌱 3. Create a Virtual Environment

Create a virtual environment called `venv` inside the project:

```bash
python -m venv venv
```

---

## 🔄 4. Activate the Virtual Environment

### On macOS / Linux:

```bash
source venv/bin/activate
```

### On Windows (PowerShell):

```powershell
venv\Scripts\Activate.ps1
```

After activation, your terminal prompt will look like:

```text
(venv) your-user@machine %
```

This means you are now inside the virtual environment.

---

## 📦 5. Install Dependencies from requirements.txt

With the virtual environment activated, install all dependencies:

```bash
pip install -r requirements.txt
```

This will install:

* Django
* PostgreSQL support (`psycopg2-binary`)
* `dj-database-url`
* `python-decouple` / `python-dotenv`
* Pillow
* Whitenoise
* Gunicorn
* django-phonenumber-field, phonenumbers
* django-haystack
* Requests, BeautifulSoup, etc.

You can check installed packages with:

```bash
pip freeze
```

---

## ⚙️ 6. Apply Database Migrations

Run Django migrations to create database tables:

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 👑 7. Create a Superuser (Admin)

To access the Django admin panel:

```bash
python manage.py createsuperuser
```

Follow the prompts to set username, email, and password.

---

## ▶️ 8. Run the Development Server

Start the local development server:

```bash
python manage.py runserver
```

Then open your browser at:

```text
http://127.0.0.1:8000/
```

---

## 🧪 9. Basic Usage

* Log in to `/admin/` using the superuser account
* Create exams, questions, and manage blog posts
* Students can:

  * Register / log in
  * Take available exams
* Teachers can:

  * View attempts
  * Check and approve results
  * See which attempts are checked (e.g., via `checked_by_teacher` field)

---

## 📁 Project Structure (Simplified)

```text
blogApp/
│── blog/               # Main app: blog & exam logic
│── blogApp/            # Django project settings, URLs, WSGI/ASGI
│── media/              # Uploaded files (if any)
│── venv/               # Virtual environment (do not commit)
│── requirements.txt    # Project dependencies
│── manage.py           # Django management script
│── README.md           # Project documentation
```

---

## ☁️ (Optional) Deployment Notes (Render.com Example)

For deployment to a platform like Render:

1. Push the project to GitHub

2. Create a new **Web Service** on Render

3. Set environment variables:

   * `DJANGO_SECRET_KEY`
   * `DATABASE_URL` (e.g. PostgreSQL URL)
   * `DEBUG=False`

4. Build command:

   ```bash
   pip install -r requirements.txt
   ```

5. Start command:

   ```bash
   gunicorn blogApp.wsgi:application --bind 0.0.0.0:$PORT
   ```

6. For static files:

   ```bash
   python manage.py collectstatic --noinput
   ```

---

## ✅ Tips

* **Always activate the virtual environment** before running Django commands:

  ```bash
  source venv/bin/activate
  ```
* If you switch machines, just:

  1. Clone the repo
  2. Create & activate `venv`
  3. Run `pip install -r requirements.txt`
  4. Apply migrations

---

## 🧑‍💻 Author

Developed by **Elvin Qurbanov**
University Lecturer • Full-Stack Developer • Researcher

```

Əgər istəyirsənsə, növbəti addımda bunun **Azerbaycanca versiyasını** da yaza bilərəm (məsələn, tələbələr üçün PDF kimi).
```
