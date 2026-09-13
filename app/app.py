from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
import sqlite3
import os
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "ders-motivasyon-2026-gizli-anahtar-degistir"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "study.db")

TASK_XP = 20  # görev başına XP
FOCUS_XP_PER_MIN = 2  # 25 dk = 50 XP
WEEKLY_JOINT_GOAL_MIN = 600  # ikinizin toplam haftalık hedefi (dk)

# ---------- DB ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        subject TEXT DEFAULT '',
        done INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        minutes INTEGER NOT NULL,
        kind TEXT DEFAULT 'focus',
        xp_earned INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS pokes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user INTEGER NOT NULL,
        to_user INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        seen INTEGER DEFAULT 0,
        FOREIGN KEY(from_user) REFERENCES users(id),
        FOREIGN KEY(to_user) REFERENCES users(id)
    );
    """)
    db.commit()
    db.close()

# ---------- helpers ----------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

def user_stats(user_id):
    db = get_db()
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=6)).isoformat()

    today_s = db.execute(
        "SELECT COALESCE(SUM(minutes),0) m, COALESCE(SUM(xp_earned),0) x, COUNT(*) c FROM sessions WHERE user_id=? AND date(created_at)=?",
        (user_id, today)).fetchone()
    total_s = db.execute(
        "SELECT COALESCE(SUM(minutes),0) m, COALESCE(SUM(xp_earned),0) x, COUNT(*) c FROM sessions WHERE user_id=?",
        (user_id,)).fetchone()
    week_s = db.execute(
        "SELECT COALESCE(SUM(minutes),0) m, COALESCE(SUM(xp_earned),0) x FROM sessions WHERE user_id=? AND date(created_at)>=?",
        (user_id, week_ago)).fetchone()
    done_tasks = db.execute("SELECT COUNT(*) c FROM tasks WHERE user_id=? AND done=1", (user_id,)).fetchone()["c"]
    total_tasks = db.execute("SELECT COUNT(*) c FROM tasks WHERE user_id=?", (user_id,)).fetchone()["c"]
    task_xp_total = done_tasks * TASK_XP
    task_xp_today = db.execute(
        "SELECT COUNT(*) c FROM tasks WHERE user_id=? AND done=1 AND date(completed_at)=?",
        (user_id, today)).fetchone()["c"] * TASK_XP
    task_xp_week = db.execute(
        "SELECT COUNT(*) c FROM tasks WHERE user_id=? AND done=1 AND date(completed_at)>=?",
        (user_id, week_ago)).fetchone()["c"] * TASK_XP

    # son 7 gün (grafik için)
    last7 = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        r = db.execute("SELECT COALESCE(SUM(minutes),0) m FROM sessions WHERE user_id=? AND date(created_at)=?",
                       (user_id, d)).fetchone()
        last7.append({"date": d[5:], "minutes": r["m"]})

    # streak: bugünden geriye art arda çalışılan gün (session var veya görev bitmiş)
    streak = 0
    d = date.today()
    while True:
        ds = d.isoformat()
        has_session = db.execute("SELECT 1 FROM sessions WHERE user_id=? AND date(created_at)=? LIMIT 1",
                                 (user_id, ds)).fetchone()
        has_task = db.execute("SELECT 1 FROM tasks WHERE user_id=? AND done=1 AND date(completed_at)=? LIMIT 1",
                              (user_id, ds)).fetchone()
        if has_session or has_task:
            streak += 1
            d -= timedelta(days=1)
        else:
            # bugün boşsa streak'i dün üzerinden say (motivasyon kırılmasın)
            if ds == date.today().isoformat():
                d -= timedelta(days=1)
                continue
            break
        if streak > 365:
            break

    return {
        "today_min": today_s["m"], "today_xp": today_s["x"] + task_xp_today,
        "today_sessions": today_s["c"],
        "total_min": total_s["m"], "total_xp": total_s["x"] + task_xp_total,
        "total_sessions": total_s["c"],
        "week_min": week_s["m"], "week_xp": week_s["x"] + task_xp_week,
        "done_tasks": done_tasks, "total_tasks": total_tasks,
        "streak": streak, "last7": last7,
    }

def level_for_xp(xp):
    level = xp // 200 + 1
    progress = (xp % 200) / 200 * 100
    titles = ["Acemi", "Kararlı", "Azimli", "Odak Canavarı", "Bilgi Avcısı", "Usta", "Efsane"]
    title = titles[min(level - 1, len(titles) - 1)]
    return level, int(progress), title

# ---------- routes ----------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    err = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if len(u) < 2 or len(p) < 3:
            err = "Kullanıcı adı (min 2) ve şifre (min 3) gir."
        else:
            db = get_db()
            try:
                db.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
                           (u, generate_password_hash(p), datetime.now().isoformat()))
                db.commit()
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                err = "Bu kullanıcı adı alınmış."
    return render_template("register.html", err=err)

@app.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if user and check_password_hash(user["password_hash"], p):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        err = "Hatalı giriş. Tekrar dene."
    return render_template("login.html", err=err)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    me = current_user()
    my = user_stats(me["id"])
    lvl, prog, title = level_for_xp(my["total_xp"])

    tasks = db.execute("SELECT * FROM tasks WHERE user_id=? ORDER BY done, id DESC",
                       (me["id"],)).fetchall()

    others = db.execute("SELECT * FROM users WHERE id != ? ORDER BY id", (me["id"],)).fetchall()
    partners = []
    for o in others:
        st = user_stats(o["id"])
        olvl, _, otitle = level_for_xp(st["total_xp"])
        partners.append({"user": o, "stats": st, "level": olvl, "title": otitle})

    # liderlik: haftalık XP'ye göre herkes
    all_users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    board = []
    for u in all_users:
        st = user_stats(u["id"])
        lv, _, ti = level_for_xp(st["total_xp"])
        board.append({"username": u["username"], "id": u["id"],
                      "week_xp": st["week_xp"], "today_min": st["today_min"],
                      "streak": st["streak"], "level": lv, "title": ti,
                      "is_me": u["id"] == me["id"]})
    board.sort(key=lambda x: x["week_xp"], reverse=True)

    # ortak haftalık hedef
    joint_week_min = sum(user_stats(u["id"])["week_min"] for u in all_users)
    joint_pct = min(100, int(joint_week_min / WEEKLY_JOINT_GOAL_MIN * 100)) if WEEKLY_JOINT_GOAL_MIN else 0

    # gelen / giden dürtmeler
    pokes_in = db.execute(
        """SELECT p.*, u.username AS from_name FROM pokes p
           JOIN users u ON u.id=p.from_user
           WHERE p.to_user=? ORDER BY p.id DESC LIMIT 8""", (me["id"],)).fetchall()
    # görülmemişleri işaretle
    db.execute("UPDATE pokes SET seen=1 WHERE to_user=?", (me["id"],))
    db.commit()

    return render_template("dashboard.html", me=me, my=my, level=lvl, progress=prog,
                           title=title, tasks=tasks, partners=partners, board=board,
                           joint_min=joint_week_min, joint_goal=WEEKLY_JOINT_GOAL_MIN,
                           joint_pct=joint_pct, pokes=pokes_in, task_xp=TASK_XP)

@app.route("/api/tasks", methods=["POST"])
@login_required
def add_task():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    if not title:
        return redirect(url_for("dashboard"))
    db = get_db()
    db.execute("INSERT INTO tasks (user_id, title, subject, created_at) VALUES (?,?,?,?)",
               (session["user_id"], title, subject, datetime.now().isoformat()))
    db.commit()
    return redirect(url_for("dashboard"))

@app.route("/api/tasks/<int:tid>/toggle", methods=["POST"])
@login_required
def toggle_task(tid):
    db = get_db()
    t = db.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, session["user_id"])).fetchone()
    if t:
        new = 0 if t["done"] else 1
        comp = datetime.now().isoformat() if new else None
        db.execute("UPDATE tasks SET done=?, completed_at=? WHERE id=?", (new, comp, tid))
        db.commit()
    return redirect(url_for("dashboard"))

@app.route("/api/tasks/<int:tid>/delete", methods=["POST"])
@login_required
def delete_task(tid):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (tid, session["user_id"]))
    db.commit()
    return redirect(url_for("dashboard"))

@app.route("/api/sessions", methods=["POST"])
@login_required
def log_session():
    data = request.get_json(force=True, silent=True) or {}
    minutes = int(data.get("minutes", 0))
    kind = data.get("kind", "focus")
    if minutes < 1 or minutes > 180:
        return jsonify({"ok": False, "err": "geçersiz süre"}), 400
    xp = minutes * FOCUS_XP_PER_MIN if kind == "focus" else 0
    db = get_db()
    db.execute("INSERT INTO sessions (user_id, minutes, kind, xp_earned, created_at) VALUES (?,?,?,?,?)",
               (session["user_id"], minutes, kind, xp, datetime.now().isoformat()))
    db.commit()
    st = user_stats(session["user_id"])
    return jsonify({"ok": True, "xp": xp, "today_min": st["today_min"], "today_xp": st["today_xp"]})

@app.route("/api/poke", methods=["POST"])
@login_required
def poke():
    to_id = request.form.get("to_user", "")
    msg = request.form.get("message", "").strip()[:200]
    presets = {
        "cok-iyi": "Çok iyi gidiyorsun, devam et!",
        "mola-bit": "Mola bitti, hadi bir pomodoro daha?",
        "gurur": "Seninle gurur duyuyorum!",
        "yaris": "Seni yakalayacağım, yarış başlasın!",
    }
    if msg.startswith("preset:"):
        msg = presets.get(msg[7:], msg)
    if not to_id or not msg:
        return redirect(url_for("dashboard"))
    db = get_db()
    db.execute("INSERT INTO pokes (from_user, to_user, message, created_at) VALUES (?,?,?,?)",
               (session["user_id"], int(to_id), msg, datetime.now().isoformat()))
    db.commit()
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    print("→ http://127.0.0.1:5001 adresinde çalışıyor")
    app.run(host="0.0.0.0", port=5001, debug=True)
