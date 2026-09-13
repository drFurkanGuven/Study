from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
import sqlite3
import os
import secrets
import string
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "ders-motivasyon-2026-gizli-anahtar-degistir"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "study.db")

TASK_XP = 20  # görev başına XP
FOCUS_XP_PER_MIN = 2  # 25 dk = 50 XP
WEEKLY_JOINT_GOAL_MIN = 600  # ekibin toplam haftalık hedefi (dk)

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
    CREATE TABLE IF NOT EXISTS friendships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester INTEGER NOT NULL,
        addressee INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        UNIQUE(requester, addressee),
        FOREIGN KEY(requester) REFERENCES users(id),
        FOREIGN KEY(addressee) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS wagers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        friendship_id INTEGER NOT NULL,
        proposer INTEGER NOT NULL,
        text TEXT NOT NULL,
        status TEXT DEFAULT 'proposed',
        winner_id INTEGER,
        week_start TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(friendship_id) REFERENCES friendships(id),
        FOREIGN KEY(proposer) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        friendship_id INTEGER NOT NULL,
        sender INTEGER NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(friendship_id) REFERENCES friendships(id),
        FOREIGN KEY(sender) REFERENCES users(id)
    );
    """)
    # eski DB'lere davet kodu + admin kolonu ekle, kodları doldur, ilk kullanıcıyı admin yap
    cols = [r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()]
    if "invite_code" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN invite_code TEXT")
    if "is_admin" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_invite ON users(invite_code)")
    for r in db.execute("SELECT id FROM users WHERE invite_code IS NULL").fetchall():
        db.execute("UPDATE users SET invite_code=? WHERE id=?", (make_code(), r[0]))
    db.execute("UPDATE users SET is_admin=1 WHERE id=1")
    db.commit()
    db.close()


def make_code(n=6):
    alpha = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alpha) for _ in range(n))

# ---------- helpers ----------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if not current_user()["is_admin"]:
            return redirect(url_for("dashboard"))
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


def friend_ids(user_id):
    """Kabul edilmiş ikili arkadaşlıklar: sadece direkt arkadaşlar (gizli)."""
    db = get_db()
    rows = db.execute(
        """SELECT CASE WHEN requester=? THEN addressee ELSE requester END AS fid
           FROM friendships WHERE status='accepted' AND (requester=? OR addressee=?)""",
        (user_id, user_id, user_id)).fetchall()
    return [r["fid"] for r in rows]


def are_friends(a, b):
    db = get_db()
    return db.execute(
        """SELECT 1 FROM friendships WHERE status='accepted'
           AND ((requester=? AND addressee=?) OR (requester=? AND addressee=?)) LIMIT 1""",
        (a, b, b, a)).fetchone() is not None


def week_start():
    return (date.today() - timedelta(days=date.today().weekday())).isoformat()

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
                first = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0
                db.execute("INSERT INTO users (username, password_hash, created_at, invite_code, is_admin) VALUES (?,?,?,?,?)",
                           (u, generate_password_hash(p), datetime.now().isoformat(), make_code(), 1 if first else 0))
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

    # --- gizli ikili arkadaşlıklar: sadece direkt arkadaşlarım ---
    fids = friend_ids(me["id"])
    friends = []
    for fid in fids:
        o = db.execute("SELECT * FROM users WHERE id=?", (fid,)).fetchone()
        if not o:
            continue
        st = user_stats(fid)
        olvl, _, otitle = level_for_xp(st["total_xp"])
        fs = db.execute(
            """SELECT * FROM friendships WHERE status='accepted'
               AND ((requester=? AND addressee=?) OR (requester=? AND addressee=?))""",
            (me["id"], fid, fid, me["id"])).fetchone()
        # aktif iddia (bu haftanın veya kabul bekleyen)
        wager = db.execute(
            """SELECT * FROM wagers WHERE friendship_id=? AND status IN ('proposed','accepted')
               ORDER BY id DESC LIMIT 1""", (fs["id"],)).fetchone()
        my_w = my["week_xp"]
        th_w = st["week_xp"]
        leader = "me" if my_w > th_w else ("them" if th_w > my_w else "tie")
        friends.append({"user": o, "stats": st, "level": olvl, "title": otitle,
                        "fid": fs["id"], "wager": wager,
                        "my_week": my_w, "their_week": th_w, "leader": leader})

    # istekler
    req_in = db.execute(
        """SELECT f.*, u.username AS from_name FROM friendships f
           JOIN users u ON u.id=f.requester
           WHERE f.addressee=? AND f.status='pending' ORDER BY f.id DESC""",
        (me["id"],)).fetchall()
    req_out = db.execute(
        """SELECT f.*, u.username AS to_name FROM friendships f
           JOIN users u ON u.id=f.addressee
           WHERE f.requester=? AND f.status='pending' ORDER BY f.id DESC""",
        (me["id"],)).fetchall()

    # sıralama: sadece ben + direkt arkadaşlarım (başkası birbirini göremez)
    board = [{"username": me["username"], "id": me["id"], "week_xp": my["week_xp"],
              "today_min": my["today_min"], "streak": my["streak"],
              "level": lvl, "title": title, "is_me": True}]
    for f in friends:
        board.append({"username": f["user"]["username"], "id": f["user"]["id"],
                      "week_xp": f["stats"]["week_xp"], "today_min": f["stats"]["today_min"],
                      "streak": f["stats"]["streak"], "level": f["level"], "title": f["title"],
                      "is_me": False})
    board.sort(key=lambda x: x["week_xp"], reverse=True)

    # ekip toplamı (sadece sayı, isim yok)
    joint_week_min = my["week_min"] + sum(f["stats"]["week_min"] for f in friends)
    joint_pct = min(100, int(joint_week_min / WEEKLY_JOINT_GOAL_MIN * 100)) if WEEKLY_JOINT_GOAL_MIN else 0

    # gelen mesajlar (okundu işaretle) — eski poke kutusu yerine chat var
    db.execute("UPDATE pokes SET seen=1 WHERE to_user=?", (me["id"],))
    db.commit()

    # chat: ?c=friendship_id seçili konuşma
    try:
        chat_fid = int(request.args.get("c", 0))
    except (TypeError, ValueError):
        chat_fid = 0
    chat_msgs, chat_peer = [], None
    if chat_fid:
        fs = db.execute("SELECT * FROM friendships WHERE id=? AND status='accepted'", (chat_fid,)).fetchone()
        if fs and me["id"] in (fs["requester"], fs["addressee"]):
            peer_id = fs["addressee"] if fs["requester"] == me["id"] else fs["requester"]
            chat_peer = db.execute("SELECT * FROM users WHERE id=?", (peer_id,)).fetchone()
            chat_msgs = db.execute(
                "SELECT * FROM messages WHERE friendship_id=? ORDER BY id", (chat_fid,)).fetchall()
        else:
            chat_fid = 0
    if not chat_fid and friends:
        chat_fid = friends[0]["fid"]
        chat_peer = friends[0]["user"]
        chat_msgs = db.execute(
            "SELECT * FROM messages WHERE friendship_id=? ORDER BY id", (chat_fid,)).fetchall()

    return render_template("dashboard.html", me=me, my=my, level=lvl, progress=prog,
                           title=title, tasks=tasks, friends=friends, board=board,
                           req_in=req_in, req_out=req_out,
                           joint_min=joint_week_min, joint_goal=WEEKLY_JOINT_GOAL_MIN,
                           joint_pct=joint_pct, task_xp=TASK_XP,
                           wager_presets=WAGER_PRESETS,
                           chat_fid=chat_fid, chat_msgs=chat_msgs, chat_peer=chat_peer)

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

@app.route("/api/chat/<int:fid>", methods=["GET"])
@login_required
def chat_fetch(fid):
    db = get_db()
    fs = db.execute("SELECT * FROM friendships WHERE id=? AND status='accepted'", (fid,)).fetchone()
    if not fs or session["user_id"] not in (fs["requester"], fs["addressee"]):
        return jsonify({"ok": False}), 403
    since = int(request.args.get("since", 0))
    rows = db.execute("SELECT id, sender, body, created_at FROM messages WHERE friendship_id=? AND id>? ORDER BY id LIMIT 100",
                      (fid, since)).fetchall()
    return jsonify({"ok": True, "msgs": [dict(r) for r in rows], "me": session["user_id"]})


@app.route("/api/chat/<int:fid>/send", methods=["POST"])
@login_required
def chat_send(fid):
    db = get_db()
    fs = db.execute("SELECT * FROM friendships WHERE id=? AND status='accepted'", (fid,)).fetchone()
    if not fs or session["user_id"] not in (fs["requester"], fs["addressee"]):
        return redirect(url_for("dashboard"))
    body = request.form.get("body", "").strip()[:500]
    if body:
        db.execute("INSERT INTO messages (friendship_id, sender, body, created_at) VALUES (?,?,?,?)",
                   (fid, session["user_id"], body, datetime.now().isoformat()))
        db.commit()
    return redirect(url_for("dashboard", c=fid, _anchor="mesaj"))


@app.route("/admin")
@admin_required
def admin():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    rows = []
    for u in users:
        st = user_stats(u["id"])
        nf = len(friend_ids(u["id"]))
        rows.append({"u": u, "xp": st["total_xp"], "mins": st["total_min"],
                     "streak": st["streak"], "friends": nf})
    return render_template("admin.html", rows=rows, me=current_user())


@app.route("/admin/user/<int:uid>/delete", methods=["POST"])
@admin_required
def admin_delete(uid):
    if uid == session["user_id"]:
        return redirect(url_for("admin"))
    db = get_db()
    fids = [r["id"] for r in db.execute(
        "SELECT id FROM friendships WHERE requester=? OR addressee=?", (uid, uid)).fetchall()]
    for fid in fids:
        db.execute("DELETE FROM wagers WHERE friendship_id=?", (fid,))
        db.execute("DELETE FROM messages WHERE friendship_id=?", (fid,))
    db.execute("DELETE FROM friendships WHERE requester=? OR addressee=?", (uid, uid))
    db.execute("DELETE FROM tasks WHERE user_id=?", (uid,))
    db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    db.execute("DELETE FROM pokes WHERE from_user=? OR to_user=?", (uid, uid))
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:uid>/toggle-admin", methods=["POST"])
@admin_required
def admin_toggle(uid):
    if uid == session["user_id"]:
        return redirect(url_for("admin"))
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if u:
        db.execute("UPDATE users SET is_admin=? WHERE id=?", (0 if u["is_admin"] else 1, uid))
        db.commit()
    return redirect(url_for("admin"))


WAGER_PRESETS = [
    "Kaybeden kahve ısmarlar",
    "Kaybeden 25 dk extra odak yapar",
    "Kazanan film/dizi seçer",
    "Kaybeden tatlı alır",
]


@app.route("/api/friends/add", methods=["POST"])
@login_required
def friend_add():
    code = request.form.get("code", "").strip().upper()
    db = get_db()
    me = current_user()
    if me["invite_code"] == code or not code:
        return redirect(url_for("dashboard"))
    target = db.execute("SELECT * FROM users WHERE invite_code=?", (code,)).fetchone()
    if not target:
        return redirect(url_for("dashboard"))
    a, b = session["user_id"], target["id"]
    exists = db.execute(
        """SELECT 1 FROM friendships
           WHERE (requester=? AND addressee=?) OR (requester=? AND addressee=?) LIMIT 1""",
        (a, b, b, a)).fetchone()
    if not exists:
        db.execute("INSERT INTO friendships (requester, addressee, status, created_at) VALUES (?,?,'pending',?)",
                   (a, b, datetime.now().isoformat()))
        db.commit()
    return redirect(url_for("dashboard"))


@app.route("/api/friends/<int:fid>/accept", methods=["POST"])
@login_required
def friend_accept(fid):
    db = get_db()
    db.execute("UPDATE friendships SET status='accepted' WHERE id=? AND addressee=?",
               (fid, session["user_id"]))
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/api/friends/<int:fid>/reject", methods=["POST"])
@login_required
def friend_reject(fid):
    db = get_db()
    db.execute("DELETE FROM friendships WHERE id=? AND (requester=? OR addressee=?)",
               (fid, session["user_id"], session["user_id"]))
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/api/friends/<int:fid>/remove", methods=["POST"])
@login_required
def friend_remove(fid):
    db = get_db()
    db.execute("DELETE FROM friendships WHERE id=? AND (requester=? OR addressee=?)",
               (fid, session["user_id"], session["user_id"]))
    db.execute("DELETE FROM wagers WHERE friendship_id=?", (fid,))
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/api/wager/propose", methods=["POST"])
@login_required
def wager_propose():
    fid = int(request.form.get("friendship_id", 0))
    text = request.form.get("text", "").strip()[:160]
    if not fid or not text:
        return redirect(url_for("dashboard"))
    db = get_db()
    fs = db.execute("SELECT * FROM friendships WHERE id=? AND status='accepted'", (fid,)).fetchone()
    if not fs or session["user_id"] not in (fs["requester"], fs["addressee"]):
        return redirect(url_for("dashboard"))
    live = db.execute("SELECT 1 FROM wagers WHERE friendship_id=? AND status IN ('proposed','accepted') LIMIT 1",
                      (fid,)).fetchone()
    if live:
        return redirect(url_for("dashboard"))
    db.execute("""INSERT INTO wagers (friendship_id, proposer, text, status, week_start, created_at)
                  VALUES (?,?,?,'proposed',?,?)""",
               (fid, session["user_id"], text, week_start(), datetime.now().isoformat()))
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/api/wager/<int:wid>/accept", methods=["POST"])
@login_required
def wager_accept(wid):
    db = get_db()
    w = db.execute("SELECT * FROM wagers WHERE id=? AND status='proposed'", (wid,)).fetchone()
    if w:
        fs = db.execute("SELECT * FROM friendships WHERE id=?", (w["friendship_id"],)).fetchone()
        if fs and session["user_id"] in (fs["requester"], fs["addressee"]) and session["user_id"] != w["proposer"]:
            db.execute("UPDATE wagers SET status='accepted' WHERE id=?", (wid,))
            db.commit()
    return redirect(url_for("dashboard"))


@app.route("/api/wager/<int:wid>/decline", methods=["POST"])
@login_required
def wager_decline(wid):
    db = get_db()
    w = db.execute("SELECT * FROM wagers WHERE id=? AND status='proposed'", (wid,)).fetchone()
    if w:
        fs = db.execute("SELECT * FROM friendships WHERE id=?", (w["friendship_id"],)).fetchone()
        if fs and session["user_id"] in (fs["requester"], fs["addressee"]):
            db.execute("DELETE FROM wagers WHERE id=?", (wid,))
            db.commit()
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    print("→ http://127.0.0.1:5001 adresinde çalışıyor")
    app.run(host="0.0.0.0", port=5001, debug=True)
