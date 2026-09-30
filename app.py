import os
import io
import re
import secrets
import smtplib
import urllib.parse
import urllib.request

from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file
from sqlalchemy import inspect
from werkzeug import Client
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from models import (
    db, User, Faculty, Student, Prediction, Intervention, Course,
    Mentor, AttendanceRecord, MarkRecord, ModelTraining
)

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)




for folder in [app.config['UPLOAD_FOLDER'], app.config['MODEL_FOLDER'],
               os.path.join(app.root_path, 'instance')]:
    os.makedirs(folder, exist_ok=True)


# ----------------------------- Basic helpers -----------------------------

def normalize_name(value):
    value = re.sub(r'[^A-Za-z ]', '', (value or ''))
    return re.sub(r'\s+', ' ', value).strip()

def valid_phone(value):
    return bool(re.fullmatch(r'[0-9]{10}', value or ''))

def valid_email(value):
    return bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value or ''))

def performance_percent(student):
    records = MarkRecord.query.filter_by(student_id=student.id).all()
    if not records:
        return 0.0
    return round(sum(r.percentage for r in records) / len(records), 1)

def performance_category(percent):
    thresholds = app.config['PERFORMANCE_THRESHOLDS']
    if percent >= thresholds['good']:
        return 'Excellent'
    if percent >= thresholds['average']:
        return 'Good'
    if percent >= thresholds['poor']:
        return 'Average'
    return 'Poor'

def risk_level(student):
    pct = performance_percent(student)
    t = app.config['RISK_THRESHOLDS']
    if pct < t['high_mark'] or student.attendance < t['high_attendance']:
        return 'High'
    if pct < t['medium_mark'] or student.attendance < t['medium_attendance']:
        return 'Medium'
    return 'Low'

def status_label(student):
    return performance_category(performance_percent(student))

def recommendations(student, risk):
    out = []
    if student.attendance < 75:
        out.append('Improve attendance and review missed classes with the faculty member.')
    pct = performance_percent(student)
    if pct < 50:
        out.append('Provide subject-wise remedial support and a short weekly improvement plan.')
    elif pct < 65:
        out.append('Use targeted practice and faculty feedback to move marks above the average band.')
    if student.discipline == 'Bad':
        out.append('Discuss discipline expectations and agree on a classroom improvement plan.')
    return out or ['Maintain the current academic routine and continue regular faculty review.']

def current_user():
    return db.session.get(User, session.get('user_id')) if session.get('user_id') else None

def guard(*roles):
    def deco(fn):
        from functools import wraps
        @wraps(fn)
        def wrapped(*args, **kwargs):
            u = current_user()
            if not u:
                return redirect(url_for('login'))
            if roles and u.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return deco

def scoped_students():
    # Admin and Faculty work from the same live student table.
    # This keeps students added by Admin immediately available to every Faculty
    # member in Marks Entry and Attendance.
    return Student.query

def student_or_404(student_id):
    s = db.session.get(Student, student_id)
    if not s:
        abort(404)
    return s

def migrate_existing_database():
    """Add new columns to an existing SQLite database without deleting existing data."""
    inspector = inspect(db.engine)
    additions = {
        'user': {
            'phone': 'VARCHAR(20)',
            'password_change_required': 'BOOLEAN DEFAULT 0',
            'otp_hash': 'VARCHAR(255)',
            'otp_expires_at': 'DATETIME',
        },
        'student': {
            'address': 'TEXT',
            'discipline': "VARCHAR(20) DEFAULT 'Good'",
            'arrears': 'INTEGER DEFAULT 0',
        },
        'mark_record': {
            'subject_name': 'VARCHAR(120)',
            'subject_code': 'VARCHAR(30)',
            'pass_mark': 'FLOAT DEFAULT 35',
            'discipline': "VARCHAR(20) DEFAULT 'Good'",
        },
    }
    for table, columns in additions.items():
        existing = {c['name'] for c in inspector.get_columns(table)}
        for name, sql_type in columns.items():
            if name not in existing:
                db.session.execute(db.text(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}'))

    # Give legacy rows safe values for the newly introduced fields.
    db.session.execute(db.text("UPDATE user SET password_change_required=0 WHERE password_change_required IS NULL"))
    db.session.execute(db.text("UPDATE student SET discipline='Good' WHERE discipline IS NULL"))
    db.session.execute(db.text("UPDATE student SET arrears=0 WHERE arrears IS NULL"))
    db.session.execute(db.text("UPDATE mark_record SET pass_mark=35 WHERE pass_mark IS NULL"))
    db.session.execute(db.text("UPDATE mark_record SET discipline='Good' WHERE discipline IS NULL"))
    db.session.execute(db.text("UPDATE mark_record SET subject_name='Legacy Subject' WHERE subject_name IS NULL OR subject_name=''"))
    db.session.execute(db.text("UPDATE mark_record SET subject_code='LEGACY' WHERE subject_code IS NULL OR subject_code=''"))
    db.session.commit()


@app.errorhandler(403)
def forbidden(error):
    return render_template('errors/message.html', title='Access denied',
                           message='Your role does not have permission to access this area.'), 403

@app.errorhandler(404)
def not_found(error):
    return render_template('errors/message.html', title='Page not found',
                           message='This page is unavailable or you do not have access to this record.'), 404

@app.before_request
def csrf_protection():
    if request.method == 'POST' and request.form.get('_csrf_token') != session.get('_csrf_token'):
        abort(403)

@app.context_processor
def inject():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return {
        'user': current_user(),
        'now': datetime.now(),
        'csrf_token': session['_csrf_token'],
        'assessment_defaults': app.config['ASSESSMENT_DEFAULTS'],
        'config': app.config,
    }


# ----------------------------- Authentication -----------------------------

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        identity = request.form.get('identity', '').strip()
        password = request.form.get('password', '')
        u = User.query.filter((User.email == identity) | (User.username == identity)).first()

        if u and u.status == 'active' and u.role in ('admin', 'faculty') and u.check_password(password):
            session.clear()
            session['user_id'] = u.id
            session.permanent = bool(request.form.get('remember'))
            if u.password_change_required:
                return redirect(url_for('change_password'))
            return redirect(url_for('dashboard'))

        flash('Invalid credentials or inactive account.', 'danger')

    return render_template('login.html')


@app.route('/change-password', methods=['GET', 'POST'])
@guard('admin', 'faculty')
def change_password():
    u = current_user()
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 8 or not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
            flash('Password must be at least 8 characters and contain letters and numbers.', 'danger')
        elif password != confirm:
            flash('Passwords do not match.', 'danger')
        else:
            u.set_password(password)
            u.password_change_required = False
            db.session.commit()
            flash('Permanent password saved successfully.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('change_password.html')




@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()

        if not identifier:
            flash('Enter your registered email or mobile number.', 'danger')
            return redirect(url_for('forgot_password'))

        if valid_phone(identifier):
            u = User.query.filter_by(phone=identifier).first()
        else:
            u = User.query.filter_by(email=identifier.lower()).first()

        if not u:
            flash('No account found with that email or mobile number.', 'danger')
            return redirect(url_for('forgot_password'))

        session['reset_user_id'] = u.id
        return redirect(url_for('reset_password'))

    return render_template('forgot.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    user_id = session.get('reset_user_id')

    if not user_id:
        return redirect(url_for('forgot_password'))

    u = db.session.get(User, user_id)

    if not u:
        session.pop('reset_user_id', None)
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if (
            len(password) < 8
            or not re.search(r'[A-Za-z]', password)
            or not re.search(r'\d', password)
        ):
            flash(
                'Password must be at least 8 characters and contain letters and numbers.',
                'danger'
            )

        elif password != confirm:
            flash('Passwords do not match.', 'danger')

        else:
            u.set_password(password)
            u.password_change_required = False

            db.session.commit()

            session.pop('reset_user_id', None)

            flash(
                'Password reset successfully. You can now log in.',
                'success'
            )

            return redirect(url_for('login'))

    return render_template('reset_password.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


# ----------------------------- Dashboard -----------------------------

@app.route('/dashboard')
@guard('admin', 'faculty')
def dashboard():
    students = scoped_students().all()
    scores = [performance_percent(s) for s in students]
    overall_marks = round(sum(scores) / len(scores), 1) if scores else 0
    overall_attendance = round(sum((s.attendance or 0) for s in students) / len(students), 1) if students else 0
    overall_performance = round((overall_marks + overall_attendance) / 2, 1)
    stats = {
        'students': len(students),
        'faculty': Faculty.query.count(),
        'departments': len(set(s.department for s in students)),
        'performance': overall_performance,
    }
    departments = sorted(set(s.department for s in students))
    dept_rows = []
    for d in departments:
        group = [s for s in students if s.department == d]
        marks = round(sum(performance_percent(s) for s in group) / len(group), 1) if group else 0
        attendance = round(sum((s.attendance or 0) for s in group) / len(group), 1) if group else 0
        performance = round((marks + attendance) / 2, 1)
        dept_rows.append({'name': d, 'students': len(group), 'marks': marks, 'attendance': attendance, 'performance': performance})

    latest = MarkRecord.query.order_by(MarkRecord.created_at.desc()).limit(10).all()
    return render_template('dashboard.html', stats=stats, dept_rows=dept_rows, latest=latest)


# ----------------------------- Students -----------------------------

@app.route('/students')
@guard('admin', 'faculty')
def students():
    q = scoped_students()
    search = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'student_id')
    direction = request.args.get('direction', 'asc')

    if search:
        q = q.filter(
            (Student.student_id.ilike(f'%{search}%')) |
            (Student.name.ilike(f'%{search}%')) |
            (Student.department.ilike(f'%{search}%'))
        )

    rows = q.all()
    sort_map = {
        'student_id': lambda s: s.student_id.lower(),
        'name': lambda s: s.name.lower(),
        'department': lambda s: s.department.lower(),
        'year': lambda s: s.year,
        'attendance': lambda s: s.attendance,
        'status': lambda s: performance_percent(s),
        'arrears': lambda s: s.arrears,
    }
    rows.sort(key=sort_map.get(sort, sort_map['student_id']), reverse=(direction == 'desc'))

    page = max(int(request.args.get('page', 1)), 1)
    per_page = 10
    pages = max(1, (len(rows) + per_page - 1) // per_page)
    page = min(page, pages)

    return render_template(
        'students.html',
        students=rows[(page - 1) * per_page:page * per_page],
        page=page, pages=pages,
        status_label=status_label, performance_percent=performance_percent
    )


@app.route('/students/new', methods=['GET', 'POST'])
@app.route('/students/<int:id>/edit', methods=['GET', 'POST'])
@guard('admin', 'faculty')
def student_form(id=None):
    s = student_or_404(id) if id else Student()
    if request.method == 'POST':
        try:
            s.student_id = request.form.get('student_id', '').strip()
            s.name = normalize_name(request.form.get('name'))
            s.gender = request.form.get('gender', '').strip()
            s.department = normalize_name(request.form.get('department'))
            s.email = request.form.get('email', '').strip()
            s.phone = request.form.get('phone', '').strip()
            s.address = request.form.get('address', '').strip()
            s.year = int(request.form.get('year', 0))
            s.semester = int(request.form.get('semester', 0))
            s.discipline = request.form.get('discipline', 'Good')
            s.arrears = int(request.form.get('arrears', 0) or 0)

            if not s.student_id or not s.name or not s.department:
                raise ValueError('Student ID, name, and department are required.')
            if not re.fullmatch(r'[A-Za-z0-9]+', s.student_id):
                raise ValueError('Student ID must contain letters and numbers only.')
            if not re.fullmatch(r'[A-Za-z ]{2,120}', s.name):
                raise ValueError('Name must contain letters and spaces only.')
            if not re.fullmatch(r'[A-Za-z ]{2,100}', s.department):
                raise ValueError('Department must contain letters and spaces only.')
            if not valid_phone(s.phone):
                raise ValueError('Mobile number must contain exactly 10 digits.')
            if not valid_email(s.email):
                raise ValueError('Enter a valid email address.')
            if s.year not in range(1, 6) or s.semester not in range(1, 11):
                raise ValueError('Select a valid year and semester.')
            if s.arrears < 0 or s.arrears > 99:
                raise ValueError('Number of arrears must be a whole number from 0 to 99.')
            if not id:
                # Faculty-created students automatically belong to that faculty.
                if current_user().role == 'faculty' and current_user().faculty:
                    s.assigned_faculty_id = current_user().faculty.id
                db.session.add(s)
            db.session.commit()
            flash('Student registration saved. Enter marks and attendance from the Faculty pages.', 'success')
            return redirect(url_for('student_profile', id=s.id))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
        except Exception:
            db.session.rollback()
            flash('Student ID must be unique and the entered values must be valid.', 'danger')
    return render_template('student_form.html', student=s)


@app.post('/students/<int:id>/delete')
@guard('admin')
def student_delete(id):
    s = student_or_404(id)
    db.session.delete(s)
    db.session.commit()
    flash('Student deleted.', 'success')
    return redirect(url_for('students'))


@app.route('/students/<int:id>')
@guard('admin', 'faculty')
def student_profile(id):
    s = student_or_404(id)
    marks = MarkRecord.query.filter_by(student_id=s.id).order_by(
        MarkRecord.created_at.desc()).all()
    predictions = sorted(s.predictions, key=lambda x: x.predicted_at, reverse=True)
    return render_template(
        'profile.html', student=s, marks=marks, predictions=predictions,
        performance_percent=performance_percent,
        performance_category=performance_category,
        risk_level=risk_level,
        recommendations=recommendations
    )


# ----------------------------- Prediction -----------------------------

@app.route('/predict/<int:id>', methods=['GET', 'POST'])
@guard('admin', 'faculty')
def prediction(id):
    s = student_or_404(id)
    result = None
    if request.method == 'POST':
        pct = performance_percent(s)
        # A prediction is now based only on the verified marks entered in the system.
        if not MarkRecord.query.filter_by(student_id=s.id).count():
            flash('Enter subject marks first. The prediction uses the verified marks and attendance.', 'danger')
        else:
            cat = performance_category(pct)
            risk = risk_level(s)
            p = Prediction(
                student_id=s.id,
                attendance=s.attendance,
                predicted_score=pct,
                performance_category=cat,
                risk_level=risk,
                probability=round(min(99, max(50, pct)), 1),
                model_version='marks-rules-v1'
            )
            db.session.add(p)
            db.session.commit()
            result = p
            flash('Prediction saved from the latest verified marks and attendance.', 'success')

    marks = MarkRecord.query.filter_by(student_id=s.id).order_by(
        MarkRecord.subject_name, MarkRecord.created_at.desc()).all()
    subjects = sorted(set((m.subject_name or 'Unnamed Subject') for m in marks))
    return render_template(
        'prediction.html', student=s, result=result, marks=marks,
        subjects=subjects, performance_percent=performance_percent,
        performance_category=performance_category, risk_level=risk_level,
        recommendations=recommendations
    )


# ----------------------------- At risk -----------------------------

@app.route('/at-risk')
@guard('admin', 'faculty')
def at_risk():
    students = [s for s in scoped_students().all() if risk_level(s) in ['High', 'Medium']]
    return render_template('at_risk.html', students=students, risk_level=risk_level,
                           performance_percent=performance_percent)


# ----------------------------- Prediction history -----------------------------

@app.route('/history')
@guard('admin', 'faculty')
def history():
    q = Prediction.query.join(Student)
    return render_template('history.html',
                           predictions=q.order_by(Prediction.predicted_at.desc()).all())


# ----------------------------- Attendance -----------------------------

@app.route('/attendance', methods=['GET', 'POST'])
@guard('admin', 'faculty')
def attendance_entry():
    students = scoped_students().all()
    if request.method == 'POST':
        try:
            s = student_or_404(int(request.form['student_id']))
            present = request.form.get('present') == 'present'
            db.session.add(AttendanceRecord(
                student_id=s.id, present=present, recorded_by=current_user().id))
            db.session.commit()
            records = AttendanceRecord.query.filter_by(student_id=s.id).all()
            s.attendance = round(100 * sum(r.present for r in records) / len(records), 1) if records else 0
            db.session.commit()
            flash('Attendance recorded and student attendance recalculated.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Attendance could not be saved: {e}', 'danger')
        return redirect(url_for('attendance_entry'))

    recent = AttendanceRecord.query.order_by(AttendanceRecord.date.desc()).limit(15).all()
    return render_template('attendance.html', students=students, records=recent)


# ----------------------------- Marks -----------------------------

@app.route('/marks', methods=['GET', 'POST'])
@guard('admin', 'faculty')
def marks_entry():
    students = scoped_students().all()
    defaults = app.config['ASSESSMENT_DEFAULTS']

    if request.method == 'POST':
        try:
            s = student_or_404(int(request.form['student_id']))
            discipline = request.form.get('discipline', 'Good')
            if discipline not in ('Good', 'Bad'):
                raise ValueError('Select Good or Bad discipline.')

            # Dynamic subject cards submit fields such as subjects[0][subject_name].
            subject_indexes = sorted({
                int(m.group(1)) for key in request.form.keys()
                for m in [re.match(r'subjects\[(\d+)\]\[subject_name\]$', key)] if m
            })
            if not subject_indexes:
                raise ValueError('Add at least one subject before saving marks.')

            saved = 0
            failed = []
            for idx in subject_indexes:
                subject_name = normalize_name(request.form.get(f'subjects[{idx}][subject_name]', ''))
                subject_code = re.sub(r'[^A-Za-z0-9-]', '', request.form.get(f'subjects[{idx}][subject_code]', '').upper())
                if not re.fullmatch(r'[A-Za-z ]{2,120}', subject_name):
                    raise ValueError(f'Subject {idx + 1}: name must contain letters and spaces only.')
                if not re.fullmatch(r'[A-Z0-9-]{2,30}', subject_code):
                    raise ValueError(f'Subject {idx + 1}: enter a valid subject code.')

                for assessment, info in defaults.items():
                    key = assessment.lower().replace(' ', '_')
                    raw_score = request.form.get(f'subjects[{idx}][{key}_score]', '').strip()
                    raw_max = request.form.get(f'subjects[{idx}][{key}_max]', '').strip()
                    raw_pass = request.form.get(f'subjects[{idx}][{key}_pass]', '').strip()
                    if raw_score == '':
                        continue
                    maximum = float(raw_max) if raw_max else info['maximum']
                    pass_mark = float(raw_pass) if raw_pass else info['pass']
                    score = float(raw_score)
                    if maximum <= 0 or pass_mark < 0 or pass_mark > maximum:
                        raise ValueError(f'Subject {idx + 1} {assessment}: invalid maximum/pass mark.')
                    if score < 0 or score > maximum:
                        raise ValueError(f'Subject {idx + 1} {assessment}: score must be between 0 and {maximum}.')
                    db.session.add(MarkRecord(
                        student_id=s.id, subject_name=subject_name, subject_code=subject_code,
                        assessment=assessment, score=score, maximum_score=maximum,
                        pass_mark=pass_mark, discipline=discipline, recorded_by=current_user().id
                    ))
                    saved += 1
                    if score < pass_mark:
                        failed.append(f'{subject_name} - {assessment}')

            if not saved:
                raise ValueError('Enter at least one assessment mark.')
            s.discipline = discipline
            db.session.commit()
            if failed:
                flash(f'{saved} marks saved. FAIL: {", ".join(failed)}.', 'warning')
            else:
                flash(f'{saved} marks saved. All entered assessments are PASS.', 'success')
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Marks could not be saved: {e}', 'danger')
        return redirect(url_for('marks_entry'))

    records = MarkRecord.query.order_by(MarkRecord.created_at.desc()).limit(30).all()
    return render_template('marks.html', students=students, records=records, defaults=defaults)


# ----------------------------- User management -----------------------------

@app.route('/users', methods=['GET', 'POST'])
@guard('admin')
def users():
    if request.method == 'POST':
        try:
            username = normalize_name(request.form.get('username'))
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()
            role = request.form.get('role', 'faculty')
            department = normalize_name(request.form.get('department'))
            temp_password = request.form.get('temporary_password', '')

            if not re.fullmatch(r'[A-Za-z ]{2,80}', username):
                raise ValueError(
                    'Name must contain characters and spaces only. Example: Arun Kumar.'
                )

            if not valid_email(email):
                raise ValueError(
                    'Enter a valid email address. Example: faculty@example.com.'
                )

            if not valid_phone(phone):
                raise ValueError(
                    'Mobile number must contain exactly 10 digits. Example: 9876543210.'
                )

            if role not in ('admin', 'faculty'):
                raise ValueError('Select a valid system role.')

            if len(temp_password) < 8:
                raise ValueError(
                    'Temporary password must contain at least 8 characters.'
                )

            if User.query.filter(
                (User.email == email) | (User.username == username)
            ).first():
                raise ValueError(
                    'A user with this name or email already exists.'
                )

            u = User(
                username=username,
                email=email,
                phone=phone,
                role=role,
                department=department,
                status='active',
                password_change_required=True
            )

            u.set_password(temp_password)

            db.session.add(u)
            db.session.flush()

            if role == 'faculty':
                db.session.add(
                    Faculty(
                        user_id=u.id,
                        faculty_id=f'FAC{u.id:03d}',
                        name=username,
                        department=department or 'General'
                    )
                )

            db.session.commit()

            flash(
                'System user created successfully. Temporary password is active until first login.',
                'success'
            )

        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')

        except Exception as e:
            db.session.rollback()
            flash(
                f'User could not be created: {e}',
                'danger'
            )

        return redirect(url_for('users'))

    return render_template(
        'users.html',
        users=User.query.order_by(User.created_at.desc()).all(),
        pending={},
        otp_verified=False
    )

# ----------------------------- Student contact -----------------------------

@app.route('/recommendations/<int:id>')
@guard('admin', 'faculty')
def recommendation_page(id):
    s = student_or_404(id)
    last = Prediction.query.filter_by(student_id=s.id).order_by(Prediction.predicted_at.desc()).first()
    return render_template('recommendations.html', student=s, prediction=last,
                           recommendations=recommendations(s, last.risk_level if last else risk_level(s)),
                           performance_percent=performance_percent)


# ----------------------------- PDF -----------------------------

@app.route('/prediction-report/<int:id>')
@guard('admin', 'faculty')
def prediction_report(id):
    s = student_or_404(id)
    last = Prediction.query.filter_by(student_id=s.id).order_by(Prediction.predicted_at.desc()).first()
    return render_template('prediction_report.html', student=s, prediction=last,
                           recommendations=recommendations(s, last.risk_level if last else risk_level(s)))


@app.route('/reports/student/<int:id>.pdf')
@guard('admin', 'faculty')
def student_report(id):
    s = student_or_404(id)
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    file = io.BytesIO()
    c = canvas.Canvas(file, pagesize=A4)
    c.setFont('Helvetica-Bold', 18)
    c.drawString(50, 800, 'Student Performance Report')
    c.setFont('Helvetica', 11)
    lines = [
        f'Student: {s.name} ({s.student_id})',
        f'Department: {s.department} | Year {s.year} | Semester {s.semester}',
        f'Attendance: {s.attendance}%',
        f'Marks performance: {performance_percent(s)}%',
        f'Category: {performance_category(performance_percent(s))}',
        f'Risk: {risk_level(s)}',
        f'Discipline: {s.discipline}',
    ]
    y = 760
    for line in lines:
        c.drawString(50, y, line)
        y -= 25
    c.save()
    file.seek(0)
    return send_file(file, download_name=f'{s.student_id}-report.pdf',
                     as_attachment=True, mimetype='application/pdf')


@app.route('/profile')
@guard('admin', 'faculty')
def profile():
    return render_template('user_profile.html')


# ----------------------------- Seed + startup -----------------------------

def seed():
    legacy_users = User.query.filter(User.role == 'authorized').all()
    for legacy in legacy_users:
        db.session.delete(legacy)
    db.session.commit()

    if User.query.first():
        return

    admin = User(username='Admin User', email='admin@college.edu',
                 role='admin', department='Administration', phone='9000000001')
    admin.set_password('Admin@123')

    facuser = User(username='Faculty User', email='faculty@college.edu',
                   role='faculty', department='Computer Science', phone='9000000002')
    facuser.set_password('Faculty@123')

    db.session.add_all([admin, facuser])
    db.session.commit()

    faculty = Faculty(user_id=facuser.id, faculty_id='FAC001',
                      name='Faculty User', department='Computer Science')
    db.session.add(faculty)
    db.session.commit()

    demo = [
        ('ST001', 'Arun Kumar', 'Computer Science', 2, 87),
        ('ST002', 'Priya Shah', 'BCA', 2, 62),
        ('ST003', 'Kumar Raj', 'Information Technology', 3, 91),
        ('ST004', 'Ananya Bose', 'Computer Science', 1, 58),
        ('ST005', 'Ravi Menon', 'BCA', 3, 76),
    ]
    for sid, name, dept, year, attendance in demo:
        db.session.add(Student(
            student_id=sid, name=name, department=dept, year=year,
            semester=year * 2 - 1, attendance=attendance,
            email=sid.lower() + '@college.edu', phone='98765' + str(43210 + len(sid)),
            address='Demo address', discipline='Good', assigned_faculty_id=faculty.id
        ))
    db.session.commit()

    # Seed realistic subject marks so the dashboard/list/prediction pages work immediately.
    students = Student.query.all()
    subjects = [
        ('Python Programming', 'CS101'),
        ('Database Systems', 'CS102'),
        ('Web Development', 'CS103'),
    ]
    defaults = app.config['ASSESSMENT_DEFAULTS']
    for s in students:
        base = max(30, min(92, s.attendance - 2))
        for subject_index, (subject, code) in enumerate(subjects):
            for assessment, info in defaults.items():
                score = round(max(0, min(info['maximum'], base - subject_index * 4 + (5 if assessment in ('Assignment', 'Practical') else 0))), 1)
                db.session.add(MarkRecord(
                    student_id=s.id, subject_name=subject, subject_code=code,
                    assessment=assessment, score=score,
                    maximum_score=info['maximum'], pass_mark=info['pass'],
                    discipline='Good', recorded_by=facuser.id
                ))
    db.session.commit()


with app.app_context():
    db.create_all()
    migrate_existing_database()
    seed()

if __name__ == '__main__':
    app.run(debug=True)
