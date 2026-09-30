from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default='faculty')
    department = db.Column(db.String(80))
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='active')
    password_change_required = db.Column(db.Boolean, default=False)
    otp_hash = db.Column(db.String(255))
    otp_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    faculty = db.relationship('Faculty', backref='user', uselist=False, cascade='all, delete-orphan')
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Faculty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    faculty_id = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(80), nullable=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(30), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    department = db.Column(db.String(80), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(25))
    address = db.Column(db.Text)
    discipline = db.Column(db.String(20), default='Good')
    arrears = db.Column(db.Integer, default=0, nullable=False)
    attendance = db.Column(db.Float, default=0)
    # Legacy fields are kept for database compatibility; they are no longer used by the UI.
    previous_gpa = db.Column(db.Float, default=0)
    assignment_score = db.Column(db.Float, default=0)
    internal_mark = db.Column(db.Float, default=0)
    study_hours = db.Column(db.Float, default=0)
    previous_semester_mark = db.Column(db.Float, default=0)
    practical_mark = db.Column(db.Float, default=0)
    participation_score = db.Column(db.Float, default=0)
    backlogs = db.Column(db.Integer, default=0)
    assigned_faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    predictions = db.relationship('Prediction', backref='student', lazy=True, cascade='all, delete-orphan')
    mark_records = db.relationship('MarkRecord', backref='student', lazy=True, cascade='all, delete-orphan')
    attendance_records = db.relationship('AttendanceRecord', backref='student', lazy=True, cascade='all, delete-orphan')

class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    attendance = db.Column(db.Float)
    previous_gpa = db.Column(db.Float)
    internal_mark = db.Column(db.Float)
    assignment_score = db.Column(db.Float)
    study_hours = db.Column(db.Float)
    previous_semester_mark = db.Column(db.Float)
    practical_mark = db.Column(db.Float)
    participation_score = db.Column(db.Float)
    backlogs = db.Column(db.Integer)
    predicted_score = db.Column(db.Float, nullable=False)
    performance_category = db.Column(db.String(30))
    risk_level = db.Column(db.String(20))
    probability = db.Column(db.Float)
    model_version = db.Column(db.String(40))
    predicted_at = db.Column(db.DateTime, default=datetime.utcnow)

class ModelTraining(db.Model):
    # Legacy table retained so old databases can migrate without data loss.
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(100))
    algorithm = db.Column(db.String(80))
    dataset_name = db.Column(db.String(200))
    training_records = db.Column(db.Integer)
    accuracy = db.Column(db.Float)
    precision = db.Column(db.Float)
    recall = db.Column(db.Float)
    f1_score = db.Column(db.Float)
    trained_at = db.Column(db.DateTime, default=datetime.utcnow)
    model_version = db.Column(db.String(40), unique=True)

class Intervention(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    identified_factor = db.Column(db.Text)
    recommendation = db.Column(db.Text)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(30), default='open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(30), unique=True, nullable=False)
    course_name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    semester = db.Column(db.Integer, nullable=False)

class Mentor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    present = db.Column(db.Boolean, nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class MarkRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    subject_name = db.Column(db.String(120))
    subject_code = db.Column(db.String(30))
    assessment = db.Column(db.String(60), nullable=False)
    score = db.Column(db.Float, nullable=False)
    maximum_score = db.Column(db.Float, nullable=False, default=100)
    pass_mark = db.Column(db.Float, nullable=False, default=35)
    discipline = db.Column(db.String(20), default='Good')
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    course = db.relationship('Course', backref='marks')
    @property
    def percentage(self):
        return round((self.score / self.maximum_score) * 100, 2) if self.maximum_score else 0
    @property
    def passed(self):
        return self.score >= self.pass_mark
