from flask import Flask, render_template, request, jsonify, redirect, url_for, session, g, send_file, flash
import sqlite3, os, hashlib, time, json, secrets, functools
from itsdangerous import URLSafeTimedSerializer
from flask_wtf import CSRFProtect
from werkzeug.utils import secure_filename
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from io import BytesIO
import ai.gemini_client as gemini
from ai.gemini_kids import kids_generate_question, kids_evaluate
from dotenv import load_dotenv
load_dotenv()
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont
import io
from PIL import Image   # make sure pillow is installed: pip install pillow
from ai.gemini_competitive import competitive_generate_question, competitive_evaluate
from ai.gemini_competitive import competitive_generate_question, competitive_evaluate
from ai.gemini_communication import (
    generate_speech_prompt,
    evaluate_speech,
    generate_conversation_question,
    evaluate_conversation,
    generate_debate_prompt,
    evaluate_debate,)
from ai.gemini_resume import analyze_resume

from docx import Document      # pip install python-docx
import PyPDF2                
import time
import os
#from instamojo_wrapper import Instamojo




# strict syllabus subject lists (trimmed; extend with your lists)
SCHOOL_SYLLABI = {
    "icse": {
        "9": ["english language","english literature","hindi grammar","history","civics","geography","mathematics","physics","chemistry","biology","economics","computer applications","art","physical education"],
        "10": ["english language","english literature","hindi grammar","history","civics","geography","mathematics","physics","chemistry","biology","economics","computer applications"]
    },
    "cbse": {
        "9": ["mathematics_basic","mathematics_standard","science","social science","english","hindi","computer science"],
        "10": ["mathematics","science","social science","english","hindi","computer science"]
    },
    "isc": {
        "11": ["biology","chemistry","physics","history","political science","mathematics","economics","computer science"],
        "12": ["biology","chemistry","physics","history","political science","mathematics","economics","computer science"]
    }
    # extend as needed...
}

# --- initial DB bootstrap for kids + viva tables (one-time guarding) ---
DB = os.path.join(os.getcwd(), "database", "intervuverse.db")
os.makedirs(os.path.join(os.getcwd(), "database"), exist_ok=True)
conn = sqlite3.connect(DB)
c = conn.cursor()

# 🔹 NEW: communication trainer tables
c.execute('''
CREATE TABLE IF NOT EXISTS communication_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    mode TEXT,          -- 'speech', 'conversation', 'debate'
    topic TEXT,         -- optional topic / theme
    session_type TEXT,  -- 'open' or 'timed'
    time_limit INTEGER, -- seconds (NULL/0 for open)
    started_at INTEGER,
    ended_at INTEGER
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS communication_attempts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    session_id INTEGER,
    mode TEXT,
    prompt TEXT,        -- topic / prompt
    question TEXT,      -- question asked (for conversation/debate)
    answer TEXT,        -- user speech transcript
    feedback TEXT,      -- AI feedback text
    overall_score INTEGER,
    confidence INTEGER,
    clarity INTEGER,
    fluency INTEGER,
    grammar INTEGER,
    vocabulary INTEGER,
    structure INTEGER,
    ts INTEGER
)
''')



c.execute('''
CREATE TABLE IF NOT EXISTS kids_attempts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    session_id INTEGER,
    question TEXT,
    transcription TEXT,
    feedback TEXT,
    score INTEGER,
    stars INTEGER,
    ts INTEGER
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS kids_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    started_at INTEGER
)
''')

# viva tables (needed by /api/viva_start_session and /api/viva_save)
c.execute('''
CREATE TABLE IF NOT EXISTS viva_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    board TEXT,
    class TEXT,
    subject TEXT,
    topic TEXT,
    started_at INTEGER
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS viva_attempts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    session_id INTEGER,
    question TEXT,
    transcription TEXT,
    feedback TEXT,
    score INTEGER,
    stars INTEGER,
    ts INTEGER
)
''')

# 🔹 NEW: competitive interview tables
c.execute('''
CREATE TABLE IF NOT EXISTS competitive_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    track TEXT,          -- UPSC / NDA / Job etc.
    role TEXT,           -- Optional: IAS, Software Engineer…
    difficulty TEXT,
    language TEXT,
    started_at INTEGER
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS competitive_attempts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    session_id INTEGER,
    question TEXT,
    transcription TEXT,
    feedback TEXT,
    score INTEGER,
    stars INTEGER,
    ts INTEGER
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS communication_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    context TEXT,
    topic TEXT,
    language TEXT,
    started_at INTEGER
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS communication_attempts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    session_id INTEGER,
    question TEXT,
    transcription TEXT,
    feedback TEXT,
    score INTEGER,
    stars INTEGER,
    ts INTEGER
)
''')

# 🔹 NEW: communication practice tables
c.execute('''
CREATE TABLE IF NOT EXISTS communication_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    mode TEXT,
    topic TEXT,
    language TEXT,
    tone TEXT,
    rounds INTEGER,
    started_at INTEGER
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS communication_attempts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    session_id INTEGER,
    prompt TEXT,
    transcription TEXT,
    feedback TEXT,
    score INTEGER,
    stars INTEGER,
    fluency TEXT,
    structure TEXT,
    confidence TEXT,
    vocabulary TEXT,
    ts INTEGER
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS resume_analyses (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    file_name TEXT,
    role TEXT,
    mode TEXT,
    overall_score INTEGER,
    ats_score INTEGER,
    clarity_score INTEGER,
    impact_score INTEGER,
    grammar_score INTEGER,
    strengths TEXT,
    improvements TEXT,
    summary TEXT,
    ts INTEGER
)
''')



conn.commit()
conn.close()
print("Tables created/verified successfully!")

app = Flask(__name__)
app.secret_key = os.environ.get("INTERVUSERVE_SECRET") or secrets.token_hex(32)
csrf = CSRFProtect(app)
BASE = os.path.dirname(__file__)
DB = os.path.join(BASE, "database", "intervuverse.db")
UPLOAD_FOLDER = os.path.join(BASE, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# email token serializer
serializer = URLSafeTimedSerializer(app.secret_key)

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def to_embed_url(url):
    if not url:
        return None

    url = url.strip()

    if "youtube.com/watch?v=" in url:
        video_id = url.split("v=")[1].split("&")[0]
        return f"https://www.youtube.com/embed/{video_id}"

    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
        return f"https://www.youtube.com/embed/{video_id}"

    if "youtube.com/embed/" in url:
        return url  # already embed

    return None


def get_user_gemini_key():
    if not g.user:
        return None

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT api_key FROM user_api_keys
        WHERE user_id=? AND provider='gemini' AND is_active=1
    """, (g.user["id"],))

    row = c.fetchone()
    conn.close()

    return row["api_key"] if row else None


def init_db():
    os.makedirs(os.path.join(BASE, "database"), exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT DEFAULT "student", created_at INTEGER, verified INTEGER DEFAULT 0, school TEXT, class TEXT, profession TEXT, address TEXT, photo TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS progress (id INTEGER PRIMARY KEY, user_id INTEGER, module TEXT, score INTEGER, ts INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS badges (id INTEGER PRIMARY KEY, user_id INTEGER, badge TEXT, ts INTEGER)')
    conn.commit(); conn.close()

def extract_resume_text(path: str) -> str:
    """
    Reads text from PDF / DOCX / TXT resume files.
    """
    ext = os.path.splitext(path)[1].lower()
    text = ""

    try:
        if ext == ".pdf":
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                pages = []
                for page in reader.pages:
                    pages.append(page.extract_text() or "")
                text = "\n".join(pages)

        elif ext == ".docx":
            doc = Document(path)
            text = "\n".join(p.text for p in doc.paragraphs)

        elif ext in (".txt", ".md"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        else:
            # unsupported type for now
            text = ""
    except Exception as e:
        print("RESUME EXTRACT ERROR:", e)
        text = ""

    return text.strip()

def check_course_completion(user_id, course_id):
    conn = get_db(); c = conn.cursor()

    # total lessons
    c.execute("SELECT COUNT(*) FROM skill_lessons WHERE course_id=?", (course_id,))
    total = c.fetchone()[0]

    # completed lessons
    c.execute("""
        SELECT COUNT(*) FROM lesson_progress lp
        JOIN skill_lessons sl ON sl.id = lp.lesson_id
        WHERE lp.user_id=? AND sl.course_id=? AND lp.completed=1
    """, (user_id, course_id))
    done = c.fetchone()[0]

    if total > 0 and total == done:
        c.execute("""
            UPDATE course_enrollments
            SET completed=1
            WHERE user_id=? AND course_id=?
        """, (user_id, course_id))

        # issue certificate
        code = f"INTV-{user_id}-{course_id}-{int(time.time())}"
        c.execute("""
            INSERT INTO certificates (user_id, course_id, certificate_code, issued_at)
            VALUES (?,?,?,?)
        """, (user_id, course_id, code, int(time.time())))

    conn.commit(); conn.close()



def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()

def login_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return wrapped


from functools import wraps
from flask import abort

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.user or g.user.get("role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper



# ================= ADMIN =================

@app.route("/admin")
@csrf.exempt
@login_required
@admin_required
def admin_root():
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/dashboard")
@csrf.exempt
@login_required
@admin_required
def admin_dashboard():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]

    conn.close()
    return render_template("admin/dashboard.html", tables=tables)

# ================= ADMIN DATABASE =================

@app.route("/admin/database")
@csrf.exempt
@login_required
def admin_database():
    if g.user["role"] != "admin":
        return redirect("/dashboard")

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    tables = [r["name"] for r in c.fetchall()]
    conn.close()

    return render_template("admin/database.html", tables=tables)


@app.route("/admin/table/<table>")
@csrf.exempt
@login_required
def admin_table_view(table):
    if g.user["role"] != "admin":
        return redirect("/dashboard")

    conn = get_db()
    c = conn.cursor()

    c.execute(f"PRAGMA table_info({table})")
    columns = [r["name"] for r in c.fetchall()]

    c.execute(f"SELECT * FROM {table}")
    rows = c.fetchall()
    conn.close()

    return render_template(
        "admin/table_view.html",
        table=table,
        columns=columns,
        rows=rows
    )


@app.route("/admin/delete/<table>/<int:row_id>", methods=["POST"])
@csrf.exempt
@login_required
def admin_delete_row(table, row_id):
    if g.user["role"] != "admin":
        return redirect("/dashboard")

    conn = get_db()
    c = conn.cursor()
    c.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
    conn.commit()
    conn.close()

    return redirect(f"/admin/table/{table}")



@app.route("/admin/users")
@csrf.exempt
@login_required
@admin_required
def admin_users():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    return render_template("admin/users.html", users=users)






@app.route("/admin/user/<int:uid>/role/<role>")
@csrf.exempt
@login_required
@admin_required
def change_user_role(uid, role):
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
    conn.commit(); conn.close()
    return redirect("/admin/users")



@app.route("/admin/feedback")
@csrf.exempt
@login_required
@admin_required
def admin_feedback():
    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT f.*, u.name
        FROM feedback f
        LEFT JOIN users u ON u.id=f.user_id
        ORDER BY f.created_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return render_template("admin/feedback.html", rows=rows)


@app.route("/admin/feedback/reply/<int:fid>", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def reply_feedback(fid):
    reply = request.form.get("reply")
    conn = get_db(); c = conn.cursor()
    c.execute("""
        UPDATE feedback
        SET reply=?, replied_at=?
        WHERE id=?
    """, (reply, int(time.time()), fid))
    conn.commit(); conn.close()
    return redirect("/admin/feedback")




@app.route("/admin/api-keys/add", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def add_api_key():
    name = request.form.get("name")
    key = request.form.get("key")
    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO api_keys (name, key, created_at)
        VALUES (?, ?, ?)
    """, (name, key, int(time.time())))
    conn.commit(); conn.close()
    return redirect("/admin/api-keys")


@app.route("/admin/announcements", methods=["GET", "POST"])
@csrf.exempt
@login_required
@admin_required
def admin_announcements():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        title = request.form.get("title")
        message = request.form.get("message")
        c.execute("""
            INSERT INTO announcements (title, message, created_at)
            VALUES (?, ?, ?)
        """, (title, message, int(time.time())))
        conn.commit()

    c.execute("SELECT * FROM announcements ORDER BY created_at DESC")
    announcements = c.fetchall()
    conn.close()

    return render_template(
        "admin/announcements.html",
        announcements=announcements
    )

@app.route("/admin/announcements/add", methods=["POST"])
@login_required
@csrf.exempt
@admin_required
def add_announcement():
    title = request.form.get("title")
    message = request.form.get("message")

    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO announcements (title, message, created_at)
        VALUES (?, ?, ?)
    """, (title, message, int(time.time())))
    conn.commit(); conn.close()

    return redirect("/admin/announcements")


@app.route("/announcements")
@csrf.exempt
@login_required
def user_announcements():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM announcements ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return render_template("announcements.html", announcements=rows)


@app.route("/api/save_api_key", methods=["POST"])
@login_required
@csrf.exempt
def save_api_key():
    api_key = request.form.get("api_key")
    if not api_key:
        return redirect("/settings")

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO user_api_keys (user_id, api_key, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
        api_key=excluded.api_key,
        is_active=1
    """, (g.user["id"], api_key, int(time.time())))

    conn.commit()
    conn.close()

    flash("API key saved successfully")
    return redirect("/settings")

@app.route("/admin/api-keys")
@login_required
@admin_required
def admin_api_keys():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT u.id, u.name, u.email, k.api_key, k.created_at
        FROM user_api_keys k
        JOIN users u ON u.id=k.user_id
        ORDER BY k.created_at DESC
    """)

    keys = c.fetchall()
    conn.close()

    return render_template("admin/api_keys.html", keys=keys)


@app.before_request

def load_logged_in_user():
    g.user = None
    
    uid = session.get("user_id")
    if uid:
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT id,name,email,role,verified,school,class,profession,address,photo,gemini_api_key FROM users WHERE id=?", (uid,))
        row = c.fetchone()
        conn.close()
        if row:
            g.user = {
                "id": row["id"], "name": row["name"], "email": row["email"],
                "role": row["role"], "verified": row["verified"],
                "school": row["school"], "class": row["class"],
                "profession": row["profession"], "address": row["address"],
                "photo": row["photo"],
                "gemini_api_key": row["gemini_api_key"]

            }
            if g.user and g.user.get("is_blocked"):
             return "Your account is blocked by admin."


@app.route("/skills")
@csrf.exempt
def skills_index():
    conn = get_db()
    c = conn.cursor()

    user_id = session.get("user_id")

    c.execute("""
        SELECT sc.*,
        EXISTS(
            SELECT 1 FROM course_enrollments ce
            WHERE ce.course_id = sc.id AND ce.user_id = ?
        ) AS enrolled
        FROM skill_courses sc
    """, (user_id or -1,))

    courses = c.fetchall()
    conn.close()

    return render_template("skills/index.html", courses=courses)



@app.route("/skills/course/<int:course_id>", methods=["GET", "POST"])
@csrf.exempt
@login_required
def skill_course(course_id):
    conn = get_db()
    c = conn.cursor()

    # Course + Instructor
    c.execute("""
        SELECT sc.*, i.name, i.bio, i.expertise, i.linkedin, i.photo
        FROM skill_courses sc
        LEFT JOIN instructors i ON sc.instructor_id = i.id
        WHERE sc.id=?
    """, (course_id,))
    course = c.fetchone()

    # Enrollment check
    c.execute("""
        SELECT * FROM course_enrollments
        WHERE user_id=? AND course_id=?
    """, (g.user["id"], course_id))
    enrolled = c.fetchone() is not None

    lessons = []
    if enrolled:
        c.execute("""
            SELECT * FROM skill_lessons
            WHERE course_id=?
            ORDER BY order_no
        """, (course_id,))
        lessons = c.fetchall()

    conn.close()

    return render_template(
        "skills/course.html",
        course=course,
        enrolled=enrolled,
        lessons=lessons
    )



@app.route("/skills/enroll/<int:course_id>", methods=["GET", "POST"])
@csrf.exempt
@login_required
def enroll_course(course_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM skill_courses WHERE id=?", (course_id,))
    course = c.fetchone()

    if request.method == "POST":
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        cert_name = request.form.get("certificate_name")

        if not full_name or not email or not cert_name:
            return "Missing enrollment details"

        # save enrollment details (table already exists)
        c.execute("""
            INSERT INTO course_enrollments
            (user_id, course_id, enrolled_at)
            VALUES (?, ?, ?)
        """, (g.user["id"], course_id, int(time.time())))
        conn.commit()

        # PAID → redirect to payment
        if course["is_paid"]:
            return redirect(f"/skills/pay/{course_id}")

        # FREE → direct success
        return redirect(f"/skills/course/{course_id}")

    conn.close()
    return render_template("skills/enroll.html", course=course)



@app.route("/skills/lesson/<int:lesson_id>")
@csrf.exempt
@login_required
def skill_lesson(lesson_id):
    conn = get_db(); c = conn.cursor()

    c.execute("""
SELECT l.*,
       EXISTS(
         SELECT 1 FROM skill_lesson_progress p
         WHERE p.lesson_id = l.id AND p.user_id = ?
       ) AS completed
FROM skill_lessons l
WHERE l.id = ?
""", (g.user["id"], lesson_id))

    lesson = c.fetchone()

    # Mark progress
    c.execute("""
        INSERT OR IGNORE INTO lesson_progress
        (user_id, lesson_id)
        VALUES (?, ?)
    """, (g.user["id"], lesson_id))
    conn.commit(); conn.close()

    return render_template("skills/lesson.html", lesson=lesson)

@app.route("/skills/progress")
@csrf.exempt
@login_required
def skill_progress():
    conn = get_db(); c = conn.cursor()

    c.execute("""
        SELECT sc.title,
        COUNT(sl.id) AS total,
        SUM(lp.completed) AS done
        FROM skill_courses sc
        JOIN skill_lessons sl ON sl.course_id = sc.id
        LEFT JOIN lesson_progress lp
          ON lp.lesson_id = sl.id AND lp.user_id=?
        GROUP BY sc.id
    """, (g.user["id"],))
    progress = c.fetchall()

    conn.close()
    return render_template("skills/progress.html", progress=progress)

@app.route("/skills/lesson/complete/<int:lesson_id>", methods=["POST"])
@csrf.exempt
@login_required
def complete_lesson(lesson_id):
    user_id = g.user["id"]

    conn = get_db()
    c = conn.cursor()

    # Check if already completed
    c.execute("""
        SELECT 1 FROM skill_lesson_progress
        WHERE user_id=? AND lesson_id=?
    """, (user_id, lesson_id))

    already_done = c.fetchone()

    if not already_done:
        c.execute("""
            INSERT OR IGNORE INTO skill_lesson_progress
            (user_id, lesson_id, completed_at)
            VALUES (?, ?, ?)
        """, (user_id, lesson_id, int(time.time())))
        conn.commit()

    # Get course_id to redirect back
    c.execute("""
        SELECT course_id FROM skill_lessons WHERE id=?
    """, (lesson_id,))
    row = c.fetchone()

    conn.close()

    return redirect(f"/skills/course/{row['course_id']}")



@app.route("/skills/certificate/<int:course_id>")
@login_required
def skill_certificate(course_id):
    conn = get_db(); c = conn.cursor()

    c.execute("""
        SELECT completed FROM course_enrollments
        WHERE user_id=? AND course_id=?
    """, (g.user["id"], course_id))
    row = c.fetchone()
    if not row or row["completed"] == 0:
        return "Complete course first", 403

    code = secrets.token_hex(6)
    c.execute("""
        INSERT INTO certificates
        (user_id, course_id, certificate_code, issued_at)
        VALUES (?,?,?,?)
    """, (g.user["id"], course_id, code, int(time.time())))
    conn.commit(); conn.close()

    # PDF
    buf = BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    p.setFont("Helvetica-Bold", 26)
    p.drawCentredString(w/2, h-150, "Certificate of Completion")

    p.setFont("Helvetica", 16)
    p.drawCentredString(w/2, h-220, f"This certifies that")
    p.drawCentredString(w/2, h-250, g.user["name"])

    p.drawCentredString(w/2, h-300, "has successfully completed the course")

    p.drawCentredString(w/2, h-350, f"Course ID: {course_id}")
    p.drawCentredString(w/2, h-380, f"Certificate Code: {code}")

    p.save()
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name="certificate.pdf",
        mimetype="application/pdf"
    )


@app.route("/admin/skills/instructors/add", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def add_instructor():
    name = request.form["name"]
    user_id = request.form["user_id"]
    expertise = request.form.get("expertise")
    linkedin = request.form.get("linkedin")
    bio = request.form.get("bio")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO instructors (name, user_id, expertise, linkedin, bio)
        VALUES (?, ?, ?, ?, ?)
    """, (name, user_id, expertise, linkedin, bio))
    conn.commit()
    conn.close()

    return redirect("/admin/skills/instructors")

@app.route("/admin/skills/course/delete/<int:course_id>", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def admin_delete_course(course_id):
    conn = get_db()
    c = conn.cursor()

    # Delete lessons first
    c.execute("DELETE FROM skill_lessons WHERE course_id=?", (course_id,))

    # Delete enrollments
    c.execute("DELETE FROM course_enrollments WHERE course_id=?", (course_id,))

    # Delete certificates
    c.execute("DELETE FROM certificates WHERE course_id=?", (course_id,))

    # Finally delete course
    c.execute("DELETE FROM skill_courses WHERE id=?", (course_id,))

    conn.commit()
    conn.close()

    return redirect("/admin/skills/courses")



@app.route("/api/skills/lesson_complete", methods=["POST"])
@csrf.exempt
@login_required
@csrf.exempt
def lesson_complete():
    lesson_id = request.form.get("lesson_id")
    course_id = request.form.get("course_id")

    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO lesson_progress
        (user_id, lesson_id, completed, completed_at)
        VALUES (?,?,1,?)
    """, (g.user["id"], lesson_id, int(time.time())))
    conn.commit(); conn.close()

    check_course_completion(g.user["id"], course_id)

    return jsonify({"success": True})


@app.route("/admin/skills/badge/add", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def add_course_badge():
    course_id = request.form.get("course_id")
    badge_name = request.form.get("badge_name")
    badge_icon = request.form.get("badge_icon")

    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO course_badges (course_id, badge_name, badge_icon)
        VALUES (?,?,?)
    """, (course_id, badge_name, badge_icon))
    conn.commit(); conn.close()

    return redirect("/admin/skills/courses")


@app.route("/api/course_review", methods=["POST"])
@csrf.exempt
@login_required
def course_review():
    data = request.get_json()
    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO course_reviews (user_id, course_id, rating, review, created_at)
        VALUES (?,?,?,?,?)
    """, (
        g.user["id"], data["course_id"],
        data["rating"], data["review"],
        int(time.time())
    ))
    conn.commit(); conn.close()
    return jsonify({"success": True})

def instructor_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.user or g.user["role"] != "instructor":
            abort(403)
        return f(*args, **kwargs)
    return wrapper



def award_course_badge(user_id, course_id):
    conn = get_db(); c = conn.cursor()

    c.execute("""
        SELECT COUNT(*) FROM skill_lessons WHERE course_id=?
    """, (course_id,))
    total = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM lesson_progress
        WHERE user_id=? AND completed=1
        AND lesson_id IN (
            SELECT id FROM skill_lessons WHERE course_id=?
        )
    """, (user_id, course_id))
    done = c.fetchone()[0]

    if total > 0 and total == done:
        c.execute("""
            UPDATE course_enrollments
            SET completed=1
            WHERE user_id=? AND course_id=?
        """, (user_id, course_id))

    conn.commit(); conn.close()

# ================= SKILLS ADMIN =================

@app.route("/admin/skills/instructors")
@csrf.exempt
@login_required
@admin_required
def admin_instructors():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM instructors")
    instructors = c.fetchall()

    c.execute("SELECT id, name, email FROM users")
    users = c.fetchall()

    c.execute("SELECT id, title FROM skill_courses")
    courses = c.fetchall()

    conn.close()

    return render_template(
        "admin/skills/instructors.html",
        instructors=instructors,
        users=users,
        courses=courses
    )


@app.route("/admin/skills/courses")
@csrf.exempt
@login_required
@admin_required
def admin_skill_courses():
    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT c.*, i.name as instructor_name
        FROM skill_courses c
        LEFT JOIN instructors i ON i.id = c.instructor_id
        ORDER BY c.created_at DESC
    """)
    courses = c.fetchall()
    conn.close()
    return render_template("admin/skills/courses.html", courses=courses)

@app.route("/admin/skills/assign_course", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def admin_assign_course():
    instructor_id = request.form.get("instructor_id")
    course_id = request.form.get("course_id")

    if not instructor_id or not course_id:
        return redirect("/admin/skills/instructors")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE skill_courses
        SET instructor_id=?
        WHERE id=?
    """, (instructor_id, course_id))
    conn.commit()
    conn.close()

    return redirect("/admin/skills/instructors")


@app.route("/admin/skills/course/<int:course_id>/lessons")
@csrf.exempt
@login_required
@admin_required
def admin_course_lessons(course_id):
    conn = get_db(); c = conn.cursor()

    c.execute("SELECT * FROM skill_courses WHERE id=?", (course_id,))
    course = c.fetchone()

    c.execute("""
        SELECT * FROM skill_lessons
        WHERE course_id=?
        ORDER BY order_no ASC
    """, (course_id,))
    lessons = c.fetchall()

    conn.close()

    if not course:
        return "Course not found", 404

    return render_template(
        "admin/skills/lessons.html",
        course=course,
        lessons=lessons
    )

@app.route("/admin/skills/course/add", methods=["GET", "POST"])
@csrf.exempt
@login_required
@admin_required
def admin_add_course():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        title = request.form["title"]
        description = request.form.get("description")
        level = request.form.get("level")
        is_paid = 1 if request.form.get("is_paid") else 0
        price = int(request.form.get("price") or 0)
        instructor_id = request.form.get("instructor_id") or None

        c.execute("""
            INSERT INTO skill_courses
            (title, description, level, is_paid, price, instructor_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            title, description, level,
            is_paid, price, instructor_id,
            int(time.time())
        ))

        conn.commit()
        conn.close()
        return redirect("/admin/skills/courses")

    c.execute("SELECT id, name FROM instructors")
    instructors = c.fetchall()
    conn.close()

    return render_template(
        "admin/skills/course_add.html",
        instructors=instructors
    )




@app.route("/admin/skills/course/<int:course_id>/lesson/add", methods=["GET", "POST"])
@csrf.exempt
@login_required
@admin_required
def admin_add_lesson(course_id):
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        video_url = to_embed_url(request.form["video_url"])
        order_no = int(request.form.get("order_no") or 1)

        conn = get_db(); c = conn.cursor()
        c.execute("""
            INSERT INTO skill_lessons
            (course_id, title, content, video_url, order_no, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (course_id, title, content, video_url, order_no, int(time.time())))
        conn.commit(); conn.close()

        return redirect(f"/admin/skills/course/{course_id}/lessons")

    return render_template(
        "admin/skills/lesson_add.html",
        course_id=course_id
    )
@app.route("/admin/skills/lesson/delete/<int:lesson_id>")
@csrf.exempt
@login_required
@admin_required 
def admin_delete_lesson(lesson_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT course_id FROM skill_lessons WHERE id=?", (lesson_id,))
    row = c.fetchone()

    if row:
        course_id = row["course_id"]
        c.execute("DELETE FROM skill_lessons WHERE id=?", (lesson_id,))
        conn.commit()
        conn.close()
        return redirect(f"/admin/skills/course/{course_id}/lessons")

    conn.close()
    return redirect("/admin/skills/courses")

@app.route("/instructor/lesson/delete/<int:lesson_id>")
@csrf.exempt
@login_required
def instructor_delete_lesson(lesson_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT course_id FROM skill_lessons WHERE id=?", (lesson_id,))
    row = c.fetchone()

    if row:
        course_id = row["course_id"]
        c.execute("DELETE FROM skill_lessons WHERE id=?", (lesson_id,))
        conn.commit()
        conn.close()
        return redirect(f"/instructor/course/{course_id}/lessons")

    conn.close()
    return "Unauthorized", 403




api = None 
@app.route("/skills/pay/<int:course_id>", methods=["GET", "POST"])
@csrf.exempt
@login_required
def skill_payment(course_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM skill_courses WHERE id=?", (course_id,))
    course = c.fetchone()
    conn.close()

    if request.method == "POST":
        name = request.form["full_name"]
        email = request.form["email"]

        response = api.payment_request_create(
        amount=str(course["price"]),
        purpose=course["title"],
        buyer_name= name,
        email=email,
        redirect_url=url_for("payment_success",course_id=course_id,_external=True),
        webhook=url_for("payment_success",course_id=course_id, _external=True),
        send_email=True,
        allow_repeated_payments=False
           )
    

# 🔐 SAFETY CHECK
        if not response or "payment_request" not in response:
         print("Instamojo Error:", response)
         return "Payment gateway error. Please try again later."

        pay_url = response["payment_request"].get("longurl")
        if not pay_url:
         return "Payment URL not generated."
        return redirect(pay_url)
        if api is None:
         return "Payments are temporarily disabled.", 503
      


    return render_template("skills/payment.html", course=course)

@app.route("/payment/success/<int:course_id>")
@csrf.exempt
@login_required
def payment_success(course_id):
    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO course_enrollments (user_id, course_id, enrolled_at)
        VALUES (?, ?, ?)
    """, (g.user["id"], course_id, int(time.time())))
    conn.commit(); conn.close()
    return redirect(f"/skills/course/{course_id}")


# ================= INSTRUCTOR DASHBOARD =================
@app.route("/instructor/dashboard")
@csrf.exempt
@login_required
def instructor_dashboard():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM instructors WHERE user_id=?", (g.user["id"],))
    inst = c.fetchone()
    if not inst:
        abort(403)

    instructor_id = inst["id"]

    c.execute("""
        SELECT * FROM skill_courses
        WHERE instructor_id=?
    """, (instructor_id,))
    courses = c.fetchall()

    conn.close()

    return render_template("instructor/dashboard.html", courses=courses)



@app.route("/instructor/course/<int:course_id>/lessons", methods=["GET","POST"])
@csrf.exempt
@login_required
def instructor_lessons(course_id):
    if g.user["role"] != "instructor":
        return redirect("/dashboard")

    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        c.execute("""
            INSERT INTO skill_lessons
            (course_id, title, content, video_url, order_no, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            course_id,
            request.form["title"],
            request.form["content"],
            request.form["video_url"],
            request.form.get("order_no", 1),
            int(time.time())
        ))
        conn.commit()

    c.execute("""
        SELECT * FROM skill_lessons
        WHERE course_id=?
        ORDER BY order_no
    """, (course_id,))
    lessons = c.fetchall()

    conn.close()

    return render_template(
        "instructor/lessons.html",
        lessons=lessons,
        course_id=course_id
    )

@app.route("/instructor/lesson/add/<int:course_id>", methods=["GET", "POST"])
@csrf.exempt
@login_required
def instructor_add_lesson(course_id):
    if g.user["role"] != "instructor":
        return redirect("/dashboard")

    conn = get_db()
    c = conn.cursor()

    # 🔐 Make sure instructor owns this course
    c.execute("""
        SELECT * FROM skill_courses
        WHERE id=? AND instructor_id=?
    """, (course_id, g.user["instructor_id"]))
    course = c.fetchone()

    if not course:
        conn.close()
        return "Unauthorized", 403

    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        raw_url = request.form.get("video_url")

        # ✅ USE SAME FUNCTION AS ADMIN
        video_url = to_embed_url(raw_url)

        order_no = int(request.form.get("order_no") or 1)

        c.execute("""
            INSERT INTO skill_lessons
            (course_id, title, content, video_url, order_no, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            course_id,
            title,
            content,
            video_url,
            order_no,
            int(time.time())
        ))

        conn.commit()
        conn.close()
        return redirect(f"/instructor/course/{course_id}/lessons")

    conn.close()
    return render_template("instructor/lesson_add.html", course=course)



def check_and_generate_certificate(user_id, course_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT COUNT(*) FROM skill_lessons WHERE course_id=?
    """, (course_id,))
    total = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM lesson_progress lp
        JOIN skill_lessons sl ON sl.id=lp.lesson_id
        WHERE lp.user_id=? AND sl.course_id=? AND lp.completed=1
    """, (user_id, course_id))
    done = c.fetchone()[0]

    if total == done:
        c.execute("""
            INSERT INTO certificates
            (user_id, course_id, certificate_code, issued_at)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            course_id,
            f"INTV-{user_id}-{course_id}",
            int(time.time())
        ))
        conn.commit()

    conn.close()


@app.route("/api/my_feedback")
@login_required
def my_feedback():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT message, rating, reply, created_at
        FROM feedback
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (g.user["id"],))

    rows = c.fetchall()
    conn.close()

    return {
        "success": True,
        "feedback": [
            {
                "message": r["message"],
                "rating": r["rating"],
                "reply": r["reply"]
            }
            for r in rows
        ]
    }


@app.route("/experience")
def user_experience():
    conn = get_db()
    c = conn.cursor()

    # Average rating
    c.execute("SELECT AVG(rating) FROM feedback WHERE rating IS NOT NULL")
    avg_rating = round(c.fetchone()[0] or 0, 1)

    

    # Rating distribution
    dist = {}
    for i in range(1, 6):
        c.execute("SELECT COUNT(*) FROM feedback WHERE rating=?", (i,))
        dist[i] = c.fetchone()[0]

    # All feedback ordered
    c.execute("""
        SELECT f.*, u.name
        FROM feedback f
        LEFT JOIN users u ON f.user_id = u.id
        ORDER BY rating DESC, created_at DESC
    """)
    feedbacks = c.fetchall()

    conn.close()

    return render_template(
        "experience.html",
        avg_rating=avg_rating,
        dist=dist,
        feedbacks=feedbacks
    )

@app.route("/admin/feedback/feature/<int:id>", methods=["POST"])
@admin_required
@csrf.exempt
def feature_feedback(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE feedback SET featured = 1-featured WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/admin/feedback")

@app.route("/my_courses")
@csrf.exempt
@login_required
def my_courses():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
SELECT
  sc.id,
  sc.title,
  COUNT(DISTINCT sl.id) AS total_lessons,
  COUNT(DISTINCT p.lesson_id) AS completed_lessons
FROM skill_courses sc
JOIN course_enrollments e ON e.course_id = sc.id
LEFT JOIN skill_lessons sl ON sl.course_id = sc.id
LEFT JOIN skill_lesson_progress p
  ON p.lesson_id = sl.id AND p.user_id = ?
WHERE e.user_id = ?
GROUP BY sc.id
""", (g.user["id"], g.user["id"]))


    courses = c.fetchall()
    conn.close()

    return render_template("/my_courses.html", courses=courses)


@app.route("/certificate/<int:course_id>")
@login_required
def download_certificate(course_id):
    conn = get_db()
    c = conn.cursor()

    # Check enrollment
    c.execute("""
        SELECT 1 FROM course_enrollments
        WHERE user_id=? AND course_id=?
    """, (g.user["id"], course_id))
    if not c.fetchone():
        conn.close()
        return "Not enrolled", 403

    # Count lessons
    c.execute("SELECT COUNT(*) FROM skill_lessons WHERE course_id=?", (course_id,))
    total = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM lesson_progress lp
        JOIN skill_lessons sl ON lp.lesson_id = sl.id
        WHERE lp.user_id=? AND sl.course_id=?
    """, (g.user["id"], course_id))
    completed = c.fetchone()[0]

    if total == 0 or completed < total:
        conn.close()
        return "Course not completed", 403

    # Insert certificate if not exists
    c.execute("""
        INSERT OR IGNORE INTO certificates (user_id, course_id, issued_at)
        VALUES (?, ?, ?)
    """, (g.user["id"], course_id, int(time.time())))
    conn.commit()

    # Fetch details
    c.execute("""
        SELECT c.title, i.name AS instructor
        FROM skill_courses c
        LEFT JOIN instructors i ON c.instructor_id=i.id
        WHERE c.id=?
    """, (course_id,))
    course = c.fetchone()

    conn.close()

    return render_template(
        "certificate.html",
        user=g.user,
        course=course
    )



@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/register")
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("register.html")


# -------------------------------------------------
# COMPETITIVE MODE – UPSC / NDA / JOB INTERVIEWS
# -------------------------------------------------

@app.route("/api/competitive_start_session", methods=["POST"])
@login_required
@csrf.exempt
def competitive_start_session():
    data = request.get_json() or {}
    track      = (data.get("track") or "Job Interview").strip()
    role       = (data.get("role") or "").strip()
    difficulty = (data.get("difficulty") or "standard").strip()
    language   = (data.get("language") or "English").strip()
    qcount     = int(data.get("qcount") or 5)

    ts = int(time.time())
    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO competitive_sessions
        (user_id, track, role, difficulty, language, started_at)
        VALUES (?,?,?,?,?,?)
    """, (g.user["id"], track, role, difficulty, language, ts))
    conn.commit()
    sid = c.lastrowid
    conn.close()
    return jsonify({"session_id": sid, "qcount": qcount})

@app.route("/api/competitive_question", methods=["GET", "POST"])
@login_required
def api_competitive_question():
    api_key = get_user_gemini_key()
    if request.method == "POST":
        data = request.get_json() or {}
        track      = data.get("track") or "UPSC Civil Services (IAS / IPS)"
        role       = data.get("role") or ""
        difficulty = data.get("difficulty") or "standard"
        language   = data.get("language") or "English"
    else:
        track      = request.args.get("track", "UPSC Civil Services (IAS / IPS)")
        role       = request.args.get("role", "")
        difficulty = request.args.get("difficulty", "standard")
        language   = request.args.get("language", "English")

    q = competitive_generate_question(track, role, difficulty, language)
    return jsonify({"question": q})

@app.route("/api/competitive_evaluate", methods=["POST"])
@login_required
@csrf.exempt
def api_competitive_evaluate():
    api_key = get_user_gemini_key()
    data = request.get_json() or {}
    question   = data.get("question", "")
    answer     = data.get("answer", "")
    track      = data.get("track") or "UPSC Civil Services (IAS / IPS)"
    role       = data.get("role") or ""
    difficulty = data.get("difficulty") or "standard"
    language   = data.get("language") or "English"

    result = competitive_evaluate(question, answer, track, role, difficulty, language)

    score = int(result.get("score", 50))
    notes = result.get("notes", "Good attempt.")
    confidence = result.get("confidence", "Medium")
    communication = result.get("communication", "Good")

    # save to progress as 'competitive'
    conn = get_db(); c = conn.cursor()
    c.execute(
        "INSERT INTO progress (user_id, module, score, ts) VALUES (?, ?, ?, ?)",
        (g.user["id"], "competitive", score, int(time.time()))
    )
    conn.commit(); conn.close()

    return jsonify({
        "score": score,
        "notes": notes,
        "confidence": confidence,
        "communication": communication,
    })

@app.route("/api/competitive_save", methods=["POST"])
@login_required
@csrf.exempt
def competitive_save():
    data = request.get_json() or {}
    session_id    = data.get("session_id")
    question      = data.get("question", "") or ""
    transcription = data.get("transcription", "") or ""
    feedback      = data.get("feedback", "") or ""
    score         = int(data.get("score") or 0)
    stars         = int(data.get("stars") or 0)

    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO competitive_attempts
        (user_id, session_id, question, transcription, feedback, score, stars, ts)
        VALUES (?,?,?,?,?,?,?,?)
    """, (g.user["id"], session_id, question, transcription, feedback, score, stars, int(time.time())))
    attempt_id = c.lastrowid

    # Track in global progress as "competitive"
    c.execute("""
        INSERT INTO progress (user_id, module, score, ts)
        VALUES (?,?,?,?)
    """, (g.user["id"], "competitive", score, int(time.time())))
    conn.commit()
    conn.close()

    return jsonify({"saved": True, "id": attempt_id})

@app.route("/api/competitive_stats")
@login_required
def competitive_stats():
    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT score, ts
        FROM progress
        WHERE user_id=? AND module='competitive'
        ORDER BY ts ASC
    """, (g.user["id"],))
    rows = c.fetchall()
    conn.close()
    scores = [r["score"] if isinstance(r, sqlite3.Row) else r[0] for r in rows]
    labels = [
        time.strftime('%d %b', time.localtime(r["ts"] if isinstance(r, sqlite3.Row) else r[1]))
        for r in rows
    ]
    return jsonify({"labels": labels, "scores": scores})

@app.route("/competitive_report/<int:session_id>")
@login_required
def competitive_report(session_id):
    """
    Session-wise Competitive / Job interview report.
    Uses competitive_attempts + competitive_sessions for this session only.
    """
    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT track, role, difficulty, language, started_at
        FROM competitive_sessions
        WHERE id=? AND user_id=?
    """, (session_id, g.user["id"]))
    sess = c.fetchone()

    if not sess:
        conn.close()
        return "No such interview session.", 404

    c.execute("""
        SELECT question, transcription, feedback, score, stars, ts
        FROM competitive_attempts
        WHERE user_id=? AND session_id=?
        ORDER BY ts ASC
    """, (g.user["id"], session_id))
    attempts = c.fetchall()
    conn.close()

    if not attempts:
        return "No attempts recorded for this session.", 404

    scores = [a["score"] for a in attempts]
    avg_score = round(sum(scores) / len(scores))
    best_score = max(scores)

    # small chart of this session
    fig, ax = plt.subplots(figsize=(6, 2.4))
    ax.bar(range(1, len(scores) + 1), scores)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Question")
    ax.set_ylabel("Score")
    ax.set_title("Interview Question-wise Scores")
    buf = BytesIO()
    fig.tight_layout()
    plt.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    chart_img = Image.open(buf)

    pdf_buf = BytesIO()
    p = canvas.Canvas(pdf_buf, pagesize=A4)
    width, height = A4

    # Watermark
    p.saveState()
    p.setFont("Helvetica-Bold", 34)
    p.setFillColorRGB(0.92, 0.92, 0.96)
    p.translate(width/2, height/2)
    p.rotate(30)
    p.drawCentredString(0, 0, "IntervuVerse Competitive")
    p.restoreState()

    # Header band
    p.setFillColorRGB(0.96, 0.98, 1)
    p.rect(0, height-200, width, 200, fill=True, stroke=False)

    # Logo if present
    logo_paths = [
        os.path.join("static", "images", "logo.png"),
        os.path.join("static", "images", "intervuverse_logo.png")
    ]
    for lp in logo_paths:
        if os.path.exists(lp):
            try:
                lg = ImageReader(lp)
                p.drawImage(lg, 40, height-150, width=90, height=90, mask="auto")
            except Exception:
                pass
            break

    # Candidate photo if any
    if g.user.get("photo"):
        try:
            photo_path = g.user["photo"].replace("/uploads/", "uploads/")
            if os.path.exists(photo_path):
                pic = Image.open(photo_path).convert("RGB")
                pic = pic.resize((110, 110))
                p.drawImage(ImageReader(pic), width-160, height-200, 150, 110, mask="auto")
        except Exception:
            pass

    # Titles
    p.setFont("Helvetica-Bold", 20)
    p.setFillColor(colors.HexColor("#1a237e"))
    p.drawString(150, height-80, "Competitive Interview Session Report")

    p.setFont("Helvetica", 12)
    p.setFillColor(colors.black)
    p.drawString(170, height-105, f"Candidate: {g.user['name']}")
    p.drawString(170, height-120, f"Track: {sess['track']}")
    if sess["role"]:
        p.drawString(170, height-135, f"Role/Post: {sess['role']}")
    p.drawString(170, height-150, f"Difficulty: {sess['difficulty']}   Language: {sess['language']}")
    p.drawString(170, height-165,
                 "Interview Date: " + time.strftime('%d %b %Y, %I:%M %p',
                                                    time.localtime(sess["started_at"])))

    # Summary box
    p.drawString(55, height-260, "Session Summary")

    p.setFont("Helvetica", 11)
    p.drawString(60, height-280, f"Questions attempted: {len(attempts)}")
    p.drawString(60, height-295, f"Average score: {avg_score}/100")
    p.drawString(60, height-310, f"Best score: {best_score}/100")

    

    p.showPage()

    # Chart + transcript
    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, height-60, "Question-wise Scores")
    p.drawInlineImage(chart_img, 40, height-320, width-80, 220)

    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, height-350, "Detailed Transcript")

    def wrap(text, max_chars=95):
        words = str(text or "").split()
        line, out = [], []
        for w in words:
            test = (" ".join(line + [w])).strip()
            if len(test) > max_chars and line:
                out.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            out.append(" ".join(line))
        return out

    y = height-380
    qno = 1
    for row in attempts:
        if y < 120:
            p.showPage()
            p.setFont("Helvetica-Bold", 16)
            p.drawString(40, height-60, "Detailed Transcript (contd.)")
            y = height-90

        p.setFont("Helvetica-Bold", 11)
        p.drawString(40, y,
                     f"Q{qno} | Score: {row['score']}/100  Stars: {'★'*row['stars']}{'☆'*(5-row['stars'])}")
        y -= 14

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(50, y, "Panel Question:")
        y -= 12
        p.setFont("Helvetica", 10)
        for line in wrap(row["question"]):
            p.drawString(65, y, line)
            y -= 12

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(50, y, "Candidate Answer:")
        y -= 12
        p.setFont("Helvetica", 10)
        ans = row["transcription"] or "(No answer recorded)"
        for line in wrap(ans):
            p.drawString(65, y, line)
            y -= 12

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(50, y, "AI Feedback:")
        y -= 12
        p.setFont("Helvetica", 10)
        for line in wrap(row["feedback"]):
            p.drawString(65, y, line)
            y -= 12

        y -= 8
        qno += 1

    p.save()
    pdf_buf.seek(0)

    return send_file(
        pdf_buf,
        as_attachment=True,
        download_name=f"competitive_session_{session_id}.pdf",
        mimetype="application/pdf"
    )


# -------------------------------------------------
# COMMUNICATION TRAINER – 3 MODES
# 1) Public Speaking
# 2) Conversational English
# 3) Debate & Argumentation
# -------------------------------------------------

@app.route("/api/comm_start_session", methods=["POST"])
@login_required
@csrf.exempt
def comm_start_session():
    data = request.get_json() or {}

    mode  = data.get("mode", "public")   # public / convo / debate
    topic = data.get("topic", "")
    timed = int(data.get("timed", 0))

    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO communication_sessions 
        (user_id, mode, topic, timed, started_at)
        VALUES (?,?,?,?,?)
    """, (
        g.user["id"],
        mode,
        topic,
        timed,
        int(time.time())
    ))
    conn.commit()
    sid = c.lastrowid
    conn.close()

    return jsonify({ "session_id": sid })


# ============ MODE 1: PUBLIC SPEAKING ============

@app.route("/api/comm_speech_prompt", methods=["POST"])
@login_required
@csrf.exempt
def comm_speech_prompt():
    api_key = get_user_gemini_key()
    data = request.get_json() or {}
    topic_hint = (data.get("topic_hint") or "").strip()
    level = (data.get("level") or "standard").strip()

    prompt_text = generate_speech_prompt(topic_hint, level)
    return jsonify({"prompt": prompt_text})


@app.route("/api/comm_speech_evaluate", methods=["POST"])
@login_required
@csrf.exempt
def comm_speech_evaluate():
    api_key = get_user_gemini_key()
    data = request.get_json() or {}
    session_id = data.get("session_id")
    prompt_text = data.get("prompt") or ""
    answer = data.get("answer") or ""

    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    result = evaluate_speech(prompt_text, answer)

    overall = int(result.get("overall_score", 60))
    confidence = int(result.get("confidence", 60))
    clarity = int(result.get("clarity", 60))
    structure = int(result.get("structure", 60))
    feedback_text = result.get("overall_feedback", "Good attempt.")
    body_tips = result.get("body_language_tips", "")

    # Save attempt + progress
    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO communication_attempts
        (user_id, session_id, mode, prompt, question, answer, feedback,
         overall_score, confidence, clarity, fluency, grammar, vocabulary, structure, ts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        g.user["id"], session_id, "speech",
        prompt_text, prompt_text, answer,
        feedback_text + ("\n\nBody language tips: " + body_tips if body_tips else ""),
        overall, confidence, clarity,
        0, 0, 0, structure,
        int(time.time())
    ))
    c.execute(
        "INSERT INTO progress (user_id, module, score, ts) VALUES (?,?,?,?)",
        (g.user["id"], "communication", overall, int(time.time()))
    )
    conn.commit(); conn.close()

    return jsonify({
        "mode": "speech",
        "overall_score": overall,
        "confidence": confidence,
        "clarity": clarity,
        "structure": structure,
        "overall_feedback": feedback_text,
        "body_language_tips": body_tips,
    })


# ============ MODE 2: CONVERSATIONAL ENGLISH ============

@app.route("/api/comm_conversation_question", methods=["POST"])
@login_required
@csrf.exempt
def comm_conversation_question():
    api_key = get_user_gemini_key()
    data = request.get_json() or {}
    history = data.get("history") or []   # list of {question, answer}
    goal = (data.get("goal") or "").strip()

    q = generate_conversation_question(history, goal)
    return jsonify({"question": q})


@app.route("/api/comm_conversation_evaluate", methods=["POST"])
@login_required
@csrf.exempt
def comm_conversation_evaluate():
    api_key = get_user_gemini_key()
    data = request.get_json() or {}
    session_id = data.get("session_id")
    question = data.get("question") or ""
    answer = data.get("answer") or ""
    history = data.get("history") or []

    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    result = evaluate_conversation(question, answer, history)

    overall = int(result.get("overall_score", 60))
    fluency = int(result.get("fluency", 60))
    grammar = int(result.get("grammar", 60))
    vocabulary = int(result.get("vocabulary", 60))
    clarity = int(result.get("clarity", 60))
    feedback_text = result.get("overall_feedback", "Good attempt.")

    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO communication_attempts
        (user_id, session_id, mode, prompt, question, answer, feedback,
         overall_score, confidence, clarity, fluency, grammar, vocabulary, structure, ts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        g.user["id"], session_id, "conversation",
        "", question, answer, feedback_text,
        overall, 0, clarity, fluency, grammar, vocabulary, 0,
        int(time.time())
    ))
    c.execute(
        "INSERT INTO progress (user_id, module, score, ts) VALUES (?,?,?,?)",
        (g.user["id"], "communication", overall, int(time.time()))
    )
    conn.commit(); conn.close()

    return jsonify({
        "mode": "conversation",
        "overall_score": overall,
        "fluency": fluency,
        "grammar": grammar,
        "vocabulary": vocabulary,
        "clarity": clarity,
        "overall_feedback": feedback_text,
    })


# ============ MODE 3: DEBATE TRAINER ============

@app.route("/api/comm_debate_prompt", methods=["POST"])
@login_required
@csrf.exempt
def comm_debate_prompt():
    api_key = get_user_gemini_key()
    data = request.get_json() or {}
    topic_hint = (data.get("topic_hint") or "").strip()
    side = (data.get("side") or "for").strip().lower()   # 'for' / 'against'

    motion = generate_debate_prompt(topic_hint, side)
    return jsonify({"motion": motion})


@app.route("/api/comm_debate_evaluate", methods=["POST"])
@login_required
@csrf.exempt
def comm_debate_evaluate():
    api_key = get_user_gemini_key()
    data = request.get_json() or {}
    session_id = data.get("session_id")
    motion = data.get("motion") or ""
    argument = data.get("argument") or ""
    side = (data.get("side") or "for").strip().lower()

    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    result = evaluate_debate(motion, argument, side)

    overall = int(result.get("overall_score", 60))
    confidence = int(result.get("confidence", 60))
    logic = int(result.get("logic", 60))
    evidence = int(result.get("evidence", 60))
    emotion = int(result.get("emotion", 60))
    feedback_text = result.get("overall_feedback", "Good argument.")

    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO communication_attempts
        (user_id, session_id, mode, prompt, question, answer, feedback,
         overall_score, confidence, clarity, fluency, grammar, vocabulary, structure, ts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        g.user["id"], session_id, "debate",
        motion, motion, argument, feedback_text,
        overall, confidence, logic, 0, evidence, 0, emotion,
        int(time.time())
    ))
    c.execute(
        "INSERT INTO progress (user_id, module, score, ts) VALUES (?,?,?,?)",
        (g.user["id"], "communication", overall, int(time.time()))
    )
    conn.commit(); conn.close()

    return jsonify({
        "mode": "debate",
        "overall_score": overall,
        "confidence": confidence,
        "logic": logic,
        "evidence": evidence,
        "emotion": emotion,
        "overall_feedback": feedback_text,
    })


# ============ COMMUNICATION PDF REPORT ============

@app.route("/communication_report/<int:session_id>")
@login_required
def communication_report(session_id):
    """
    Download a multi-page communication report (any of the 3 modes).
    """
    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT id, mode, topic
        FROM communication_sessions
        WHERE id=? AND user_id=?
    """, (session_id, g.user["id"]))
    sess = c.fetchone()

    if not sess:
        conn.close()
        return "No such communication session.", 404

    c.execute("""
        SELECT prompt, question, answer, feedback,
               overall_score, confidence, clarity, fluency,
               grammar, vocabulary, structure, ts
        FROM communication_attempts
        WHERE user_id=? AND session_id=?
        ORDER BY ts ASC
    """, (g.user["id"], session_id))
    attempts = c.fetchall()
    conn.close()

    if not attempts:
        return "No attempts recorded for this session.", 404

    # aggregate stats
    scores = [a["overall_score"] for a in attempts]
    best_score = max(scores)

    avg_conf = round(sum(a["confidence"] for a in attempts) / len(attempts)) if any(a["confidence"] for a in attempts) else 0
    avg_clarity = round(sum(a["clarity"] for a in attempts) / len(attempts)) if any(a["clarity"] for a in attempts) else 0
    avg_fluency = round(sum(a["fluency"] for a in attempts) / len(attempts)) if any(a["fluency"] for a in attempts) else 0

    # small chart
    fig, ax = plt.subplots(figsize=(6, 2.4))
    ax.plot(range(1, len(scores) + 1), scores, marker="o")
    ax.set_ylim(0, 100)
    ax.set_xlabel("Attempt")
    ax.set_ylabel("Score")
    ax.set_title("Communication Performance")
    buf = BytesIO()
    fig.tight_layout()
    plt.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    chart_img = Image.open(buf)

    pdf_buf = BytesIO()
    p = canvas.Canvas(pdf_buf, pagesize=A4)
    width, height = A4

    def wrap(text, max_chars=95):
        words = str(text or "").split()
        line, out = [], []
        for w in words:
            test = (" ".join(line + [w])).strip()
            if len(test) > max_chars and line:
                out.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            out.append(" ".join(line))
        return out

    # watermark
    p.saveState()
    p.setFont("Helvetica-Bold", 34)
    p.setFillColorRGB(0.92, 0.92, 0.96)
    p.translate(width/2, height/2)
    p.rotate(30)
    p.drawCentredString(0, 0, "IntervuVerse Communication")
    p.restoreState()

    # header band
    p.setFillColorRGB(0.96, 0.98, 1)
    p.rect(0, height-200, width, 200, fill=True, stroke=False)

    # logo
    logo_paths = [
        os.path.join("static", "images", "logo.png"),
        os.path.join("static", "images", "intervuverse_logo.png")
    ]
    for lp in logo_paths:
        if os.path.exists(lp):
            try:
                lg = ImageReader(lp)
                p.drawImage(lg, 40, height-150, width=90, height=90, mask="auto")
            except Exception:
                pass
            break

    # user photo
    if g.user.get("photo"):
        try:
            photo_path = g.user["photo"].replace("/uploads/", "uploads/")
            if os.path.exists(photo_path):
                pic = Image.open(photo_path).convert("RGB")
                pic = pic.resize((110, 110))
                p.drawImage(ImageReader(pic), width-160, height-180, 110, 110, mask="auto")
        except Exception:
            pass

    mode_label = {
        "speech": "Public Speaking Trainer",
        "conversation": "Conversational English Trainer",
        "debate": "Debate & Argumentation Trainer"
    }.get(sess["mode"], "Communication Trainer")

    p.setFont("Helvetica-Bold", 20)
    p.setFillColor(colors.HexColor("#1a237e"))
    p.drawString(150, height-80, "Communication Session Report")

    p.setFont("Helvetica", 12)
    p.setFillColor(colors.black)
    p.drawString(150, height-105, f"Student: {g.user['name']}")
    p.drawString(150, height-120, f"Mode: {mode_label}")

    

    # summary stats
    p.setFont("Helvetica-Bold", 13)
    p.drawString(40, height-210, "Summary")
    p.setFont("Helvetica", 11)
    p.drawString(60, height-230, f"Attempts: {len(attempts)}")
    p.drawString(60, height-260, f"Best score: {best_score}/100")
    if avg_conf:
        p.drawString(60, height-275, f"Avg confidence: {avg_conf}/100")
    if avg_clarity:
        p.drawString(60, height-290, f"Avg clarity: {avg_clarity}/100")
    if avg_fluency:
        p.drawString(60, height-305, f"Avg fluency: {avg_fluency}/100")

    p.showPage()

    # chart + transcript
    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, height-60, "Performance Overview")
    p.drawInlineImage(chart_img, 40, height-320, width-80, 220)

    y = height-340
    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, y, "Detailed Transcript")
    y -= 20

    attempt_no = 1
    for row in attempts:
        if y < 120:
            p.showPage()
            p.setFont("Helvetica-Bold", 16)
            p.drawString(40, height-60, "Detailed Transcript (contd.)")
            y = height-90

        p.setFont("Helvetica-Bold", 11)
        date_str = time.strftime('%d %b %Y', time.localtime(row["ts"]))
        p.drawString(
            40, y,
            f"Attempt {attempt_no}  [{date_str}]  Score: {row['overall_score']}/100"
        )
        y -= 14

        if row["prompt"]:
            p.setFont("Helvetica-Oblique", 10)
            p.drawString(50, y, "Prompt / Topic:")
            y -= 12
            p.setFont("Helvetica", 10)
            for line in wrap(row["prompt"]):
                p.drawString(65, y, line)
                y -= 12

        if row["question"]:
            p.setFont("Helvetica-Oblique", 10)
            p.drawString(50, y, "Question / Motion:")
            y -= 12
            p.setFont("Helvetica", 10)
            for line in wrap(row["question"]):
                p.drawString(65, y, line)
                y -= 12

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(50, y, "Your answer:")
        y -= 12
        p.setFont("Helvetica", 10)
        for line in wrap(row["answer"] or "(No answer recorded)"):
            p.drawString(65, y, line)
            y -= 12

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(50, y, "AI feedback:")
        y -= 12
        p.setFont("Helvetica", 10)
        for line in wrap(row["feedback"] or ""):
            p.drawString(65, y, line)
            y -= 12

        y -= 10
        attempt_no += 1

    # teacher signature block
    if y < 140:
        p.showPage()
        y = height-100

    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, y, "Teacher / Mentor Remarks:")
    y -= 25
    p.setFont("Helvetica", 11)
    for _ in range(4):
        p.drawString(40, y, "______________________________________________")
        y -= 20

    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, 110, "Teacher's Signature:")
    p.line(170, 112, 420, 112)
    p.drawString(40, 85, "Date:")
    p.line(80, 87, 200, 87)

    p.save()
    pdf_buf.seek(0)

    return send_file(
        pdf_buf,
        as_attachment=True,
        download_name=f"communication_session_{session_id}.pdf",
        mimetype="application/pdf"
    )




# ---------------- Kids Mode API ----------------
@app.route("/api/kids_question")
@login_required
def api_kids_question():
    api_key = get_user_gemini_key()
    q = kids_generate_question()
    return jsonify({"question": q})

@app.route("/api/kids_evaluate", methods=["POST"])
@login_required
@csrf.exempt
def api_kids_evaluate():
    api_key = get_user_gemini_key()
    data = request.get_json()
    question = data.get("question", "")
    transcription = data.get("transcription", "")

    result = kids_evaluate(question, transcription)

    score = result["score"]
    stars = max(1, min(5, score // 20))

    return jsonify({
        "score": score,
        "notes": result["notes"],
        "stars": stars
    })

@app.route("/api/kids_start_session", methods=["POST"])
@login_required
@csrf.exempt
def kids_start_session():
    conn = get_db(); c = conn.cursor()
    ts = int(time.time())
    c.execute("INSERT INTO kids_sessions (user_id, started_at) VALUES (?, ?)",
              (g.user["id"], ts))
    conn.commit()
    sid = c.lastrowid
    conn.close()
    return jsonify({"session_id": sid})

@app.route("/api/kids_save", methods=["POST"])
@login_required
@csrf.exempt
def kids_save():
    data = request.get_json()

    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO kids_attempts
        (user_id, session_id, question, transcription, feedback, score, stars, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        g.user["id"], session_id,
        data["question"], data["transcription"], data["feedback"],
        data["score"], data["stars"],
        int(time.time())
    ))
    conn.commit()
    attempt_id = c.lastrowid
    conn.close()

    return jsonify({"saved": True, "id": attempt_id})

# Kids final PDF
@app.route("/kids_final_report/<int:session_id>")
@login_required
def kids_session_report(session_id):
    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT question, transcription, feedback, score, stars, ts
        FROM kids_attempts
        WHERE user_id=? AND session_id=?
        ORDER BY ts ASC
    """, (g.user["id"], session_id))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return "No attempts found for this session.", 404

    avg_score = sum([r["score"] for r in rows]) / len(rows)
    if avg_score >= 70:
        medal = "GOLD";   medal_color = colors.gold
    elif avg_score >= 50:
        medal = "SILVER"; medal_color = colors.silver
    else:
        medal = "BRONZE"; medal_color = colors.brown

    scores = [r["score"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 2.2))
    ax.bar(range(len(scores)), scores,
           color=['#ffd166','#ff7aa2','#9be7ff','#b5ffb2'] * 4)
    ax.set_ylim(0,100)
    ax.set_ylabel("Score")
    ax.set_xticks([])
    ax.set_title("Session Scores")

    buf = BytesIO()
    fig.tight_layout()
    plt.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    chart_img = Image.open(buf)

    pdf_buf = BytesIO()
    p = canvas.Canvas(pdf_buf, pagesize=A4)
    width, height = A4

    p.setFillColorRGB(0.96, 0.98, 1)
    p.rect(0, 0, width, height, fill=True, stroke=False)

    cover_path = "static/images/kids_cover.png"
    cover_img = ImageReader(cover_path)
    p.drawImage(cover_img, 30, height-420, width-60, height=400, mask='auto')

    p.setFont("Helvetica-Bold", 28)
    p.setFillColor(colors.darkblue)
    p.drawCentredString(width/2, height-450, "Kids Interview Report")

    if g.user["photo"]:
        try:
            photo_path = g.user["photo"].replace("/uploads/", "uploads/")
            if os.path.exists(photo_path):
                child = Image.open(photo_path).convert("RGB")
                child = child.resize((140, 140))
                child_reader = ImageReader(child)
                p.drawImage(child_reader, width/2-75, height - 630 ,150,150, mask='auto')
        except Exception as e:
            print("PHOTO ERROR:", e)

    p.setFont("Helvetica-Bold", 18)
    p.setFillColor(colors.black)
    p.drawCentredString(width/2, height-650, f"Child Name: {g.user['name']}")

    p.setFont("Helvetica", 12)
    p.drawCentredString(width/2, height-670, f"Generated on: {time.ctime()}")

    p.setFont("Helvetica-Bold", 20)
    p.setFillColor(medal_color)
    p.drawCentredString(width/2, height-710, f"🏅 {medal} ACHIEVER 🏅")

    p.showPage()

    p.drawInlineImage(chart_img, 40, height-260, width-80, 160)

    y = height - 300
    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, y, "Interview Responses")
    y -= 30

    p.setFont("Helvetica", 11)
    for i, row in enumerate(rows):
        if y < 120:
            p.showPage()
            y = height - 80

        p.setFont("Helvetica-Bold", 11)
        p.drawString(40, y, f"Q{i+1}: {row['question']}")
        y -= 16

        p.setFont("Helvetica", 10)
        p.drawString(60, y, f"Answer: {row['transcription']}")
        y -= 14
        p.drawString(60, y, f"Feedback: {row['feedback']}")
        y -= 14
        p.drawString(60, y, f"Score: {row['score']}   Stars: {'★'*row['stars']}")
        y -= 25

    p.showPage()
    p.setFont("Helvetica-Bold", 20)
    p.drawString(40, height-80, "Performance Summary")

    strengths = []
    weaknesses = []

    for r in rows:
        if r["score"] >= 70:
            strengths.append("✔ Clear and confident answers")
        elif r["score"] >= 40:
            strengths.append("✔ Good attempt with improving clarity")
        else:
            weaknesses.append("✘ Needs more confidence and vocabulary")

    if not strengths:
        strengths.append("✔ Showed willingness to participate")

    if not weaknesses:
        weaknesses.append("✘ Provide fuller sentences for better clarity")

    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, height-130, "Key Strengths:")
    p.setFont("Helvetica", 12)
    y = height - 150
    for s in strengths:
        p.drawString(60, y, s)
        y -= 16

    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, y-10, "Key Weaknesses / Improvements:")
    y -= 40
    p.setFont("Helvetica", 12)
    for w in weaknesses:
        p.drawString(60, y, w)
        y -= 16

    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, 120, "Teacher's Signature:")
    p.line(180, 122, 420, 122)

    p.drawString(40, 90, "Date:")
    p.line(90, 92, 200, 92)

    p.save()
    pdf_buf.seek(0)

    return send_file(pdf_buf, as_attachment=True,
                     download_name="kids_session_report.pdf",
                     mimetype="application/pdf")

# ----------- PAGES -----------
@app.route("/viva")
@login_required
def viva():
    return render_template("viva.html")

@app.route("/kids")
@login_required
def kids():
    return render_template("kids.html")

@app.route("/competitive")
@login_required
def competitive():
    return render_template("competitive.html")

@app.route("/resume")
@login_required
def resume():
    return render_template("resume.html")

@app.route("/communication")
@login_required
def communication():
    return render_template("communication.html")

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as sessions, AVG(score) as avg_score FROM progress WHERE user_id=?", (g.user["id"],))
    stats = c.fetchone()
    c.execute("SELECT badge FROM badges WHERE user_id=?", (g.user["id"],))
    badges = [r["badge"] for r in c.fetchall()]
    conn.close()
    sessions = stats["sessions"] or 0
    avg_score = int(stats["avg_score"] or 0)
    return render_template("dashboard.html", sessions=sessions, avg_score=avg_score, badges=badges)

@app.route("/leaderboard")
@login_required
def leaderboard():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT u.name, SUM(p.score) as points FROM users u JOIN progress p ON u.id=p.user_id GROUP BY u.id ORDER BY points DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    return render_template("leaderboard.html", rows=rows)

@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=g.user)

# ----------- AUTH / PROFILE -----------
@app.route("/api/register", methods=["POST"])
@csrf.exempt
def api_register():
    data = request.get_json()
    name, email, pw = data.get("name"), data.get("email"), data.get("pass")
    if not (name and email and pw):
        return jsonify({"success":False,"message":"Provide name,email,password"}),400
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO users (name,email,password_hash,created_at) VALUES (?,?,?,?)",
                  (name,email,hash_pw(pw),int(time.time())))
        conn.commit(); uid = c.lastrowid; conn.close()
        token = serializer.dumps(email, salt='email-verify')
        session.clear()
        session["user_id"] = uid
        session["user_name"] = name
        return jsonify({"success":True,"message":"Registered. Verification email (demo) sent.", "verify_token": token})
    except Exception as e:
        conn.close()
        return jsonify({"success":False,"message":"Email exists or error: "+str(e)})

@app.route("/verify_email/<token>")
def verify_email(token):
    try:
        email = serializer.loads(token, salt='email-verify', max_age=60*60*24)
    except Exception as e:
        return "Verification link invalid or expired."
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE users SET verified=1 WHERE email=?", (email,))
    conn.commit(); conn.close()
    return "Email verified. You can close this page."

@app.route("/api/kids_recent")
@login_required
def api_kids_recent():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT score, ts FROM kids_attempts WHERE user_id=? ORDER BY ts DESC LIMIT 12", (g.user['id'],))
    rows = c.fetchall(); conn.close()
    scores = [r["score"] for r in rows][::-1]
    return jsonify({"scores": scores})

@app.route("/api/login", methods=["POST"])
@csrf.exempt
def api_login():
    data = request.get_json()
    email, pw = data.get("email"), data.get("pass")

    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT id, name, password_hash, verified, role
        FROM users WHERE email=?
    """, (email,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"success": False, "message": "No such user."})

    if row["password_hash"] != hash_pw(pw):
        return jsonify({"success": False, "message": "Incorrect password."})

    session.clear()
    session["user_id"] = row["id"]
    session["user_name"] = row["name"]
    
    if row["role"] == "admin":
     return jsonify({"success":True,"redirect":"/admin/dashboard"})

    return jsonify({"success":True,"redirect":"/dashboard"})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ----------- VIVA: question + evaluation -----------
@app.route("/api/question")
@login_required
def api_question():
    api_key = get_user_gemini_key()
    board = request.args.get("board", "icse").lower()
    cls = request.args.get("class", "9")
    subject = request.args.get("subject", "english").lower()
    topic = request.args.get("topic", "").strip()
    strict = request.args.get("strict", "0")

    strict_mode = "STRICT" if strict == "1" else "NORMAL"

    prompt = f"""
You are a professional school viva examiner.
Generate ONE viva-style oral question.

Board: {board.upper()}
Class: {cls}
Subject: {subject}
Topic (optional): {topic if topic else 'general any topic but only and only syllabus-based'}
Mode: {strict_mode}

Rules:
1. MUST be strictly from the official syllabus.
2. Oral viva style only.
3. Single sentence not very lengthy but good and conceptual.
4. No out-of-syllabus.
5. be very very strict and stick to class and official syllabus in every board and class
also make sure only give question and not other things like here is your question or anything 
"""

    try:
        ai_response = gemini.generate_question(prompt)

        # ✅ SAFELY extract ONLY the generated question
        if isinstance(ai_response, dict):
            question = ai_response.get("text") or ai_response.get("question")
        else:
            question = str(ai_response)

        if not question.strip():
            question = f"What is one key concept from {subject}?"

        return jsonify({"question": question.strip()})

    except Exception as e:
        print("AI ERROR:", e)
        return jsonify({"question": f"What is one important concept from {subject}?"})


@app.route("/api/evaluate", methods=["POST"])
@login_required
@csrf.exempt
def api_evaluate():
    api_key = get_user_gemini_key()
    data = request.get_json(silent=True) or {}

    question = data.get("question", "")
    answer = data.get("answer", "") or data.get("transcription", "") or ""

    if not question.strip():
        return jsonify({"error": "Missing question"}), 400

    try:
        result = gemini.evaluate_answer(question, answer)
    except Exception:
        words = len(answer.split())
        score = min(100, max(20, words * 6))
        result = {"score": score, "notes": "Good attempt! Improve clarity."}

    score = int(result.get("score", 50))
    notes = result.get("notes", "")

    try:
        conn = get_db(); c = conn.cursor()
        c.execute(
            "INSERT INTO progress (user_id, module, score, ts) VALUES (?, ?, ?, ?)",
            (g.user["id"], "viva", score, int(time.time()))
        )
        conn.commit()
        conn.close()
    except:
        pass

    return jsonify({"score": score, "notes": notes})


# ----------- VIVA: session save (for kids-style flow) -----------
@app.route("/api/viva_start_session", methods=["POST"])
@login_required
def viva_start_session():
    data = request.get_json() or {}
    board = data.get("board", "icse")
    cls = data.get("class", "9")
    subject = data.get("subject", "")
    topic = data.get("topic", "")
    ts = int(time.time())
    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO viva_sessions (user_id, board, class, subject, topic, started_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (g.user["id"], board, cls, subject, topic, ts))
    conn.commit()
    sid = c.lastrowid
    conn.close()
    return jsonify({"session_id": sid})

@app.route("/api/viva_save", methods=["POST"])
@login_required
@csrf.exempt
def viva_save():
    data = request.get_json() or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    conn = get_db(); c = conn.cursor()
    c.execute("""
      INSERT INTO viva_attempts (user_id, session_id, question, transcription, feedback, score, stars, ts)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (g.user["id"], session_id, data.get("question"), data.get("transcription"),
          data.get("feedback"), data.get("score"), data.get("stars"), int(time.time())))
    aid = c.lastrowid

    c.execute("INSERT INTO progress (user_id,module,score,ts) VALUES (?,?,?,?)",
              (g.user['id'], 'viva', data.get('score'), int(time.time())))
    conn.commit()
    conn.close()
    return jsonify({"saved": True, "id": aid})

@app.route("/viva_session_report/<int:session_id>")
@login_required
@csrf.exempt
def session_report(session_id):
    conn = get_db(); c = conn.cursor()

    # ✅ Get latest viva session
    c.execute("""
        SELECT id, board, class, subject, topic, started_at
        FROM viva_sessions
        WHERE user_id=?
        ORDER BY started_at DESC
        LIMIT 1
    """, (g.user["id"],))
    session_row = c.fetchone()

    if not session_row:
        return "No viva session found.", 400

    session_id = session_row["id"]

    # ✅ Get full transcript for this session
    c.execute("""
        SELECT question, transcription, feedback, score, stars, ts
        FROM viva_attempts
        WHERE user_id=? AND session_id=?
        ORDER BY ts ASC
    """, (g.user["id"], session_id))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return "No viva attempts found.", 400

    # ✅ Stats
    scores = [r["score"] for r in rows]
    avg_score = round(sum(scores) / len(scores))
    best_score = max(scores)

    # ✅ Chart
    fig, ax = plt.subplots(figsize=(6, 2.2))
    ax.bar(range(1, len(scores)+1), scores)
    ax.set_ylim(0,100)
    ax.set_title("Viva Question-wise Scores")

    buf = BytesIO()
    fig.tight_layout()
    plt.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    chart_img = Image.open(buf)

    # ✅ PDF
    pdf_buf = BytesIO()
    p = canvas.Canvas(pdf_buf, pagesize=A4)
    width, height = A4

    # ---------- COVER PAGE ----------
    p.setFillColorRGB(0.95, 0.97, 1)
    p.rect(0, 0, width, height, fill=True)

    # Logo
    logo_path = "static/images/logo.png"
    if os.path.exists(logo_path):
        p.drawImage(logo_path, width/2-60, height-130, 120, 120, mask="auto")

    p.setFont("Helvetica-Bold", 26)
    p.drawCentredString(width/2, height-170, "IntervuVerse Viva Session Report")

    p.setFont("Helvetica", 13)
    p.drawCentredString(width/2, height-200, f"Student: {g.user['name']}")
    p.drawCentredString(width/2, height-220, f"Board: {session_row['board']}  Class: {session_row['class']}")
    p.drawCentredString(width/2, height-240, f"Subject: {session_row['subject']}")

    p.drawCentredString(
        width/2, height-265,
        time.strftime("%d %b %Y, %I:%M %p", time.localtime(session_row["started_at"]))
    )

    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width/2, height-310, f"Average Score: {avg_score}/100")
    p.drawCentredString(width/2, height-335, f"Best Score: {best_score}/100")

    # Photo
    if g.user.get("photo"):
        try:
            path = g.user["photo"].replace("/uploads/", "uploads/")
            if os.path.exists(path):
                img = Image.open(path).resize((140,140))
                p.drawImage(ImageReader(img), width/2-70, height-480, 140, 140, mask="auto")
        except:
            pass

    p.showPage()

    # ---------- CHART PAGE ----------
    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, height-80, "Viva Performance Chart")
    p.drawInlineImage(chart_img, 40, height-320, width-80, 220)
    p.showPage()

    # ---------- TRANSCRIPT PAGES ----------
    def wrap(txt, max_chars=90):
        words = str(txt).split()
        out, line = [], []
        for w in words:
            test = " ".join(line+[w])
            if len(test) > max_chars:
                out.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            out.append(" ".join(line))
        return out

    y = height - 80
    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, y, "Viva Transcript")
    y -= 30

    qno = 1
    for r in rows:
        if y < 140:
            p.showPage()
            y = height - 80
            p.setFont("Helvetica-Bold", 16)
            p.drawString(40, y, "Viva Transcript (contd.)")
            y -= 30

        p.setFont("Helvetica-Bold", 11)
        p.drawString(40, y, f"Q{qno} | Score: {r['score']} | Stars: {'★'*r['stars']}")
        y -= 14

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(55, y, "Question:")
        y -= 12
        p.setFont("Helvetica", 10)
        for line in wrap(r["question"]):
            p.drawString(70, y, line)
            y -= 12

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(55, y, "Answer:")
        y -= 12
        p.setFont("Helvetica", 10)
        for line in wrap(r["transcription"] or "(No answer)"):
            p.drawString(70, y, line)
            y -= 12

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(55, y, "Feedback:")
        y -= 12
        p.setFont("Helvetica", 10)
        for line in wrap(r["feedback"]):
            p.drawString(70, y, line)
            y -= 12

        y -= 10
        qno += 1

    # ---------- SIGNATURE PAGE ----------
    p.showPage()
    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, height-100, "Teacher's Signature:")
    p.line(220, height-100, 450, height-100)

    p.drawString(40, height-140, "Date:")
    p.line(90, height-140, 200, height-140)

    p.save()
    pdf_buf.seek(0)

    return send_file(
        pdf_buf,
        as_attachment=True,
        download_name="viva_session_report.pdf",
        mimetype="application/pdf"
    )


# ----------- SETTINGS & ANALYTICS -----------

@app.route("/resume_report/<int:analysis_id>")
@login_required
def resume_report(analysis_id):
    """
    Professional PDF for one resume analysis.
    """
    conn = get_db(); c = conn.cursor()
    c.execute("""
        SELECT *
        FROM resume_analyses
        WHERE id=? AND user_id=?
    """, (analysis_id, g.user["id"]))
    row = c.fetchone()
    conn.close()

    if not row:
        return "No such resume analysis.", 404

    strengths = json.loads(row["strengths"] or "[]")
    improvements = json.loads(row["improvements"] or "[]")

    pdf_buf = BytesIO()
    p = canvas.Canvas(pdf_buf, pagesize=A4)
    width, height = A4

    # Watermark
    p.saveState()
    p.setFont("Helvetica-Bold", 34)
    p.setFillColorRGB(0.92, 0.92, 0.96)
    p.translate(width/2, height/2)
    p.rotate(30)
    p.drawCentredString(0, 0, "IntervuVerse Resume Report")
    p.restoreState()

    # Top band
    p.setFillColorRGB(0.96, 0.98, 1)
    p.rect(0, height-200, width, 200, fill=True, stroke=False)

    # Logo
    logo_paths = [
        os.path.join("static", "images", "logo.png"),
        os.path.join("static", "images", "intervuverse_logo.png")
    ]
    for lp in logo_paths:
        if os.path.exists(lp):
            try:
                lg = ImageReader(lp)
                p.drawImage(lg, 40, height-150, width=90, height=90, mask="auto")
            except Exception:
                pass
            break

    # Candidate photo
    if g.user.get("photo"):
        try:
            photo_path = g.user["photo"].replace("/uploads/", "uploads/")
            if os.path.exists(photo_path):
                pic = Image.open(photo_path).convert("RGB")
                pic = pic.resize((110, 110))
                p.drawImage(ImageReader(pic), width-160, height-160, 110, 110, mask="auto")
        except Exception as e:
            print("RESUME PHOTO ERROR:", e)

    # Header text
    p.setFont("Helvetica-Bold", 20)
    p.setFillColor(colors.HexColor("#1a237e"))
    p.drawString(150, height-80, "AI Resume Analysis Report")

    p.setFont("Helvetica", 12)
    p.setFillColor(colors.black)
    p.drawString(150, height-105, f"Candidate: {g.user['name']}")
    if g.user.get("profession"):
        p.drawString(150, height-120, f"Profile: {g.user['profession']}")
    if row["role"]:
        p.drawString(150, height-135, f"Target Role: {row['role']}")
    p.drawString(150, height-150,
                 f"Generated on: {time.strftime('%d %b %Y, %I:%M %p', time.localtime(row['ts']))}")

    # Scores box
    p.setFillColorRGB(1, 1, 1)
    p.roundRect(40, height-360, width-80, 150, 10, fill=True, stroke=True)
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(colors.HexColor("#263238"))
    p.drawString(55, height-250, "Score Summary (0–100)")

    p.setFont("Helvetica", 11)
    p.setFillColor(colors.black)
    p.drawString(60, height-270, f"Overall Score: {row['overall_score']}/100")
    p.drawString(60, height-290, f"ATS Compatibility: {row['ats_score']}/100")
    p.drawString(60, height-310, f"Clarity & Structure: {row['clarity_score']}/100")
    p.drawString(60, height-330, f"Impact (Achievements): {row['impact_score']}/100")
    p.drawString(60, height-350, f"Grammar & Language: {row['grammar_score']}/100")

    

    p.showPage()

    # Page 2 – strengths & improvements
    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, height-70, "Key Strengths")
    p.setFont("Helvetica", 11)
    y = height-95
    if not strengths:
        strengths = ["The AI could not detect clear strengths, please review your resume structure."]
    for s in strengths:
        if y < 120:
            p.showPage()
            p.setFont("Helvetica-Bold", 16)
            p.drawString(40, height-70, "Key Strengths (contd.)")
            p.setFont("Helvetica", 11)
            y = height-95
        p.drawString(60, y, f"• {s}")
        y -= 16

    if y < 160:
        p.showPage()
        y = height-70

    p.setFont("Helvetica-Bold", 16)
    p.drawString(40, y, "Improvements & Suggestions")
    y -= 25
    p.setFont("Helvetica", 11)
    if not improvements:
        improvements = ["Consider adding quantified achievements and clearer bullet points."]
    for imp in improvements:
        if y < 120:
            p.showPage()
            p.setFont("Helvetica-Bold", 16)
            p.drawString(40, height-70, "Improvements & Suggestions (contd.)")
            p.setFont("Helvetica", 11)
            y = height-95
        p.drawString(60, y, f"• {imp}")
        y -= 16

    # Page 3 – overall summary
    p.showPage()
    p.setFont("Helvetica-Bold", 18)
    p.drawString(40, height-80, "Overall AI Summary")

    def wrap(text, max_chars=95):
        words = str(text or "").split()
        out, line = [], []
        for w in words:
            test = (" ".join(line + [w])).strip()
            if len(test) > max_chars and line:
                out.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            out.append(" ".join(line))
        return out

    p.setFont("Helvetica", 12)
    y = height-110
    for line in wrap(row["summary"] or ""):
        if y < 120:
            p.showPage()
            p.setFont("Helvetica-Bold", 18)
            p.drawString(40, height-80, "Overall AI Summary (contd.)")
            p.setFont("Helvetica", 12)
            y = height-110
        p.drawString(60, y, line)
        y -= 16

    p.save()
    pdf_buf.seek(0)

    return send_file(
        pdf_buf,
        as_attachment=True,
        download_name=f"resume_report_{analysis_id}.pdf",
        mimetype="application/pdf"
    )


@app.route("/api/upload_resume", methods=["POST"])
@login_required
@csrf.exempt
def upload_resume():
    """
    Upload + analyze resume with Gemini.
    Returns JSON with analysis + analysis_id for PDF report.
    """
    f = request.files.get("resume")
    if not f:
        return jsonify({"success": False, "message": "Please upload a resume file."}), 400

    filename = secure_filename(f.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    f.save(save_path)

    role = (request.form.get("role") or "").strip()
    mode = (request.form.get("mode") or "general").strip()

    resume_text = extract_resume_text(save_path)
    if not resume_text or len(resume_text.split()) < 30:
        return jsonify({
            "success": False,
            "message": "Could not read enough text from the resume. Please upload a clear PDF/DOCX/TXT file."
        }), 400

    try:
        analysis = analyze_resume(resume_text, role, mode)
    except Exception as e:
        print("RESUME AI ERROR:", e)
        analysis = {
            "overall_score": 70,
            "ats_score": 68,
            "clarity_score": 72,
            "impact_score": 65,
            "grammar_score": 75,
            "strengths": ["Good basic structure."],
            "improvements": ["AI analysis failed, please try again."],
            "summary": "Fallback analysis because the AI call failed."
        }

    # Save summary in DB
    conn = get_db(); c = conn.cursor()
    c.execute("""
        INSERT INTO resume_analyses
        (user_id, file_name, role, mode,
         overall_score, ats_score, clarity_score, impact_score, grammar_score,
         strengths, improvements, summary, ts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        g.user["id"], filename, role, mode,
        analysis["overall_score"], analysis["ats_score"],
        analysis["clarity_score"], analysis["impact_score"], analysis["grammar_score"],
        json.dumps(analysis.get("strengths") or []),
        json.dumps(analysis.get("improvements") or []),
        analysis.get("summary") or "",
        int(time.time())
    ))
    conn.commit()
    analysis_id = c.lastrowid
    conn.close()

    return jsonify({
        "success": True,
        "analysis": analysis,
        "analysis_id": analysis_id,
        "file_name": filename
    })


@csrf.exempt
@app.route("/api/update_profile", methods=["POST"])
@login_required
def update_profile():
    name = request.form.get("name")
    role = request.form.get("role")
    school = request.form.get("school")
    cls = request.form.get("class")
    profession = request.form.get("profession")
    address = request.form.get("address")

    photo_url = g.user["photo"]

    photo = request.files.get("photo")
    if photo:
        filename = secure_filename(photo.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        photo.save(save_path)
        photo_url = f"/uploads/{filename}"

    conn = get_db(); c = conn.cursor()
    c.execute("""
        UPDATE users SET name=?, role=?, school=?, class=?, profession=?, address=?, photo=?
        WHERE id=?
    """, (name, role, school, cls, profession, address, photo_url, g.user["id"]))
    conn.commit(); conn.close()

    return redirect("/profile")

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", user=g.user)

@app.route("/api/save_settings", methods=["POST"])
@login_required
@csrf.exempt
def save_settings():
    language = request.form.get("language")
    theme = request.form.get("theme")
    voice = request.form.get("voice")
    speed = request.form.get("speed")
    gemini_api_key = request.form.get("gemini_api_key")


    weekly_report = 1 if request.form.get("weekly_report") else 0
    reminders = 1 if request.form.get("reminders") else 0
    badges = 1 if request.form.get("badges") else 0

    conn = get_db(); c = conn.cursor()
    c.execute("""
      UPDATE users SET 
       language=?, theme=?, voice=?, speed=?,
         weekly_report=?, reminders=?, badges=?,
      gemini_api_key=?
        WHERE id=?
    """, (language, theme, voice, speed, weekly_report, reminders, badges,gemini_api_key, g.user["id"]))
    conn.commit(); conn.close()

    return redirect("/settings")


@app.route("/about")
@login_required
def about():
    return render_template("about.html")


@app.route("/api/submit_feedback", methods=["POST"])
@login_required
@csrf.exempt
def submit_feedback():
    # 1. Get data from the POST request
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    rating = int(data.get("rating", 0))
    
    # 2. Calculate created_at timestamp (using time.time() for consistency with INTEGER type)
    import time
    created_at = int(time.time()) 

    if not message:
        return jsonify({"error": "Feedback cannot be empty"}), 400

    conn = get_db(); c = conn.cursor()
    
    # 3. UPDATED SQL STATEMENT: Including user_id, message, rating, and created_at
    #    Note: 'admin_reply' and 'replied_at' are left out as they are set later by an admin.
    c.execute("""
        INSERT INTO feedback (user_id, message, rating, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        g.user["id"], 
        message, 
        rating, 
        created_at
    ))
    conn.commit(); conn.close()

    return jsonify({"success": True})


@app.route("/api/session_stats")
@login_required
@csrf.exempt
def session_stats():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT score, ts FROM progress WHERE user_id=? ORDER BY ts ASC", (g.user["id"],))
    rows = c.fetchall(); conn.close()
    scores = [r[0] for r in rows]
    labels = [time.strftime('%d %b', time.localtime(r[1])) for r in rows]
    return jsonify({"labels": labels, "scores": scores})
    






# ----------- MAIN -----------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)

app = Flask(__name__)

if __name__ == "__main__":
    app.run()
