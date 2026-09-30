import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret-key')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'college.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'instance', 'uploads')
    MODEL_FOLDER = os.path.join(BASE_DIR, 'instance', 'models')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    
    SMTP_HOST = 'smtp.gmail.com'
    SMTP_PORT = 587
    SMTP_USERNAME = 'admin@gmail.com'
    SMTP_PASSWORD = 'tnwn sxgd qwhn tmrl'
    SMTP_FROM = 'admin@gmail.com'


    # You can change these values without changing the templates.
    PERFORMANCE_THRESHOLDS = {
        'poor': 50,
        'average': 65,
        'good': 80,
    }
    RISK_THRESHOLDS = {
        'high_mark': 50,
        'medium_mark': 65,
        'high_attendance': 60,
        'medium_attendance': 75,
    }
    # Default maximum/pass marks. Each marks-entry row can override the pass mark.
    ASSESSMENT_DEFAULTS = {
        'CIAT 1': {'maximum': 40, 'pass': 14},
        'CIAT 2': {'maximum': 40, 'pass': 14},
        'Model Examination': {'maximum': 100, 'pass': 35},
        'Semester Examination': {'maximum': 100, 'pass': 35},
        'Practical': {'maximum': 100, 'pass': 35},
        'Internal': {'maximum': 100, 'pass': 35},
        'Assignment': {'maximum': 100, 'pass': 35},
    }

    # Optional email OTP settings. For local testing, if SMTP is not configured,
    # the OTP is printed to the terminal.
    SMTP_HOST = os.environ.get('SMTP_HOST', '')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_FROM = os.environ.get('SMTP_FROM', SMTP_USERNAME)

    # Optional SMS OTP settings. For real SMS, configure Twilio environment variables.
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_FROM = os.environ.get('TWILIO_FROM', '')
