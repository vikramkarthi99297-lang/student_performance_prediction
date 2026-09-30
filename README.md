# Student Performance Prediction System

This version uses **verified subject marks + attendance** for performance categories and risk levels. The old ML model-management, dataset-upload and analytics pages have been removed.

## Main changes
- Login welcome page no longer displays admin/faculty credentials.
- Forgot password uses OTP confirmation.
- Dashboard shows department-wise performance.
- Student list supports ID/name search, department filter and sortable columns.
- Student status is Poor / Average / Good / Excellent based on marks.
- Student registration contains personal/contact/address details only; subjects are entered in Marks Entry.
- Marks Entry supports CIAT 1, CIAT 2, Model Examination, Semester Examination, Practical, Internal and Assignment.
- Every assessment has editable maximum and pass marks.
- PASS/FAIL is verified immediately after saving.
- Discipline is recorded as Good/Bad.
- Attendance is stored and recalculated automatically.
- At-Risk uses marks + attendance and shows Low/Medium/High risk plus mobile contact.
- Prediction History no longer shows model version.
- User Management includes mobile number, OTP verification and temporary-to-permanent password flow.
- Faculty-created students are linked to that faculty, so the same students appear in marks and attendance pages.

## Run

Open PowerShell in the folder containing `app.py`:

```powershell
py app.py
```

Then open:

```text
http://127.0.0.1:5000/
```

If your terminal is one folder above the project:

```powershell
cd .\student-performance-prediction-system
py app.py
```

## Default development accounts

These are used only to seed a fresh database. They are intentionally **not displayed on the login page**.

- Admin: `admin@college.edu` / `Admin@123`
- Faculty: `faculty@college.edu` / `Faculty@123`

## OTP

For real email OTP, set these environment variables before starting Flask:

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM
```

Without SMTP configuration, local development prints the OTP in the Flask terminal so the workflow can still be tested.

## Adjustable pass marks

Default values are in `config.py` under `ASSESSMENT_DEFAULTS`. The Marks Entry page also lets you change the maximum and pass mark for each assessment every time you enter marks.

Example:
- `35 / 100`
- `15 / 40`

## Performance bands

Edit `PERFORMANCE_THRESHOLDS` in `config.py`:
- Poor: below 50
- Average: 50 to below 65
- Good: 65 to below 80
- Excellent: 80 and above

## Risk bands

Edit `RISK_THRESHOLDS` in `config.py` to change the marks/attendance boundaries for High, Medium and Low risk.
