"""Database helpers for the Monarch gym prototype.

Uses the standard-library sqlite3 module. A single file (monarch.db) holds all
data and persists across restarts. On first run the schema is created and demo
data is seeded so the app is immediately usable.
"""

import os
import sqlite3
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

# Database file location. Defaults to the project root; override with the
# DB_PATH env var (e.g. point it at a Render persistent disk like
# /var/data/monarch.db). The directory is created if missing.
DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "monarch.db"),
)
os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)


def get_db():
    """Open a connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if the database does not exist yet, then seed demo data."""
    first_run = not os.path.exists(DB_PATH)
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS members (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name     TEXT NOT NULL,
            plan_name     TEXT NOT NULL,
            plan_status   TEXT NOT NULL,
            start_date    TEXT NOT NULL,
            expiry_date   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS coaches (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            specialty TEXT NOT NULL,
            bio       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS classes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            coach_id   INTEGER NOT NULL REFERENCES coaches(id),
            start_time TEXT NOT NULL,
            capacity   INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id  INTEGER NOT NULL REFERENCES members(id),
            class_id   INTEGER NOT NULL REFERENCES classes(id),
            created_at TEXT NOT NULL,
            UNIQUE(member_id, class_id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id  INTEGER NOT NULL REFERENCES members(id),
            coach_id   INTEGER NOT NULL REFERENCES coaches(id),
            body       TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS achievements (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title    TEXT NOT NULL,
            athlete  TEXT NOT NULL,
            year     INTEGER NOT NULL,
            icon     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            kind       TEXT NOT NULL,          -- 'fight' or 'tournament'
            location   TEXT NOT NULL,
            event_date TEXT NOT NULL,
            headline   TEXT NOT NULL           -- main bout / featured matchup
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id  INTEGER NOT NULL REFERENCES members(id),
            message    TEXT NOT NULL,
            due_date   TEXT NOT NULL,
            kind       TEXT NOT NULL DEFAULT 'payment',  -- 'payment' or 'general'
            dismissed  INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id   INTEGER NOT NULL REFERENCES members(id),
            plan_name   TEXT NOT NULL,
            amount      REAL NOT NULL,
            method      TEXT NOT NULL,          -- e.g. 'Revolut Pay (demo)'
            paid_at     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workouts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id   INTEGER NOT NULL REFERENCES members(id),
            kind        TEXT NOT NULL,          -- 'run' or 'gym'
            title       TEXT NOT NULL,
            workout_date TEXT NOT NULL,
            duration_min INTEGER,               -- minutes (both kinds)
            distance_km REAL,                   -- runs only
            notes       TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exercise_sets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
            exercise   TEXT NOT NULL,
            set_no     INTEGER NOT NULL,
            reps       INTEGER,
            weight_kg  REAL
        );

        CREATE TABLE IF NOT EXISTS library_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trainer_id  INTEGER REFERENCES coaches(id),
            kind        TEXT NOT NULL,          -- 'video' or 'workout'
            title       TEXT NOT NULL,
            category    TEXT NOT NULL,          -- e.g. 'K1', 'BJJ', 'Strength'
            description TEXT,
            video_url   TEXT,                   -- videos only
            content     TEXT,                   -- workouts: the plan text
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pt_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id  INTEGER NOT NULL REFERENCES members(id),
            coach_id   INTEGER NOT NULL REFERENCES coaches(id),
            slot_time  TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'booked',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            body       TEXT NOT NULL,
            rating     INTEGER,                -- optional 1-5
            created_at TEXT NOT NULL
            -- intentionally NO member_id: feedback is anonymous
        );

        CREATE TABLE IF NOT EXISTS health_metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id   INTEGER NOT NULL REFERENCES members(id),
            metric_date TEXT NOT NULL,          -- one row per member per day
            steps       INTEGER,
            sleep_hours REAL,
            calories    INTEGER,
            resting_hr  INTEGER,                -- bpm
            source      TEXT NOT NULL DEFAULT 'manual',  -- 'manual' | 'apple' | 'google'
            UNIQUE(member_id, metric_date)
        );

        CREATE TABLE IF NOT EXISTS athletes (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT NOT NULL,
            sport   TEXT NOT NULL,
            record  TEXT                         -- e.g. "12-2-0 (W-L-D)"
        );

        CREATE TABLE IF NOT EXISTS event_participants (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id   INTEGER NOT NULL REFERENCES events(id),
            member_id  INTEGER NOT NULL REFERENCES members(id),
            status     TEXT NOT NULL DEFAULT 'registered',  -- registered | confirmed | waitlist
            created_at TEXT NOT NULL,
            UNIQUE(event_id, member_id)
        );

        CREATE TABLE IF NOT EXISTS timetable (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week INTEGER NOT NULL,        -- 0=Mon .. 6=Sun
            start_hhmm  TEXT NOT NULL,           -- "07:00"
            name        TEXT NOT NULL,
            coach_id    INTEGER REFERENCES coaches(id),
            capacity    INTEGER NOT NULL DEFAULT 20,
            prebook     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS timetable_bookings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id  INTEGER NOT NULL REFERENCES members(id),
            slot_id    INTEGER NOT NULL REFERENCES timetable(id),
            class_date TEXT NOT NULL,            -- the specific date booked
            created_at TEXT NOT NULL,
            UNIQUE(member_id, slot_id, class_date)
        );
        """
    )
    conn.commit()

    _migrate(conn)

    if first_run:
        _seed(conn)

    # These sections were added later. Seed them if empty, so existing
    # databases pick up the new content without being wiped.
    _seed_if_empty(conn)

    conn.close()


def _migrate(conn):
    """Add columns introduced after the original schema, for existing DBs.

    SQLite has no 'ADD COLUMN IF NOT EXISTS', so we check the table info first.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(members)")}
    if "email" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN email TEXT")
    if "auth_provider" not in cols:
        # 'password', 'google', or 'apple'
        conn.execute(
            "ALTER TABLE members ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'password'"
        )
    if "has_library_sub" not in cols:
        # Virtual Training Library subscription (€10/mo) — separate from the gym plan.
        conn.execute(
            "ALTER TABLE members ADD COLUMN has_library_sub INTEGER NOT NULL DEFAULT 0"
        )
    if "library_sub_until" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN library_sub_until TEXT")
    if "ai_consent" not in cols:
        # GDPR: explicit opt-in before any personal context is sent to the AI.
        conn.execute(
            "ALTER TABLE members ADD COLUMN ai_consent INTEGER NOT NULL DEFAULT 0"
        )
    if "health_source" not in cols:
        # Which external app the member "connected" (demo): '', 'apple', 'google'.
        conn.execute("ALTER TABLE members ADD COLUMN health_source TEXT DEFAULT ''")
    # Personal athlete profile (editable on the user's own athlete page).
    for col in ("athlete_sport", "athlete_sport2", "athlete_record", "athlete_record2"):
        if col not in cols:
            conn.execute(f"ALTER TABLE members ADD COLUMN {col} TEXT DEFAULT ''")

    # Athletes: optional second discipline + record.
    acols = {row["name"] for row in conn.execute("PRAGMA table_info(athletes)")}
    if "sport2" not in acols:
        conn.execute("ALTER TABLE athletes ADD COLUMN sport2 TEXT")
    if "record2" not in acols:
        conn.execute("ALTER TABLE athletes ADD COLUMN record2 TEXT")
    conn.commit()


def _seed(conn):
    """Insert demo members, coaches, and classes on first run."""
    today = date.today()

    def iso(d):
        return d.isoformat()

    # Members in three distinct plan states so the tracker visibly differs.
    members = [
        # username, password, full_name, plan, status, start, expiry
        (
            "sarah",
            "monarch",
            "Sarah Jones",
            "Unlimited Annual",
            "active",
            iso(today - timedelta(days=120)),
            iso(today + timedelta(days=245)),
        ),
        (
            "mike",
            "monarch",
            "Mike Chen",
            "Monthly Standard",
            "active",
            iso(today - timedelta(days=25)),
            iso(today + timedelta(days=5)),  # near expiry
        ),
        (
            "ava",
            "monarch",
            "Ava Patel",
            "Monthly Standard",
            "expired",
            iso(today - timedelta(days=60)),
            iso(today - timedelta(days=3)),  # expired
        ),
    ]
    conn.executemany(
        """INSERT INTO members
           (username, password_hash, full_name, plan_name, plan_status, start_date, expiry_date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (u, generate_password_hash(p), fn, pl, st, sd, ed)
            for (u, p, fn, pl, st, sd, ed) in members
        ],
    )

    coaches = [
        ("Joshua", "K1 / Kickboxing", "K1 for all kids and adults. Also runs KickFit and Boxercise (pre-booking)."),
        ("Rowan", "BJJ (Kids & No-Gi)", "Kids Jiu-Jitsu, No-Gi and Open Mat — all levels welcome."),
        ("Julio", "BJJ Gi", "BJJ Gi coach — Monday & Wednesday sessions."),
        ("Dennis", "BJJ Gi (Beginner)", "Tuesday beginner-friendly BJJ Gi. Patient, fundamentals-first."),
    ]
    conn.executemany(
        "INSERT INTO coaches (name, specialty, bio) VALUES (?, ?, ?)",
        coaches,
    )

    # Upcoming classes over the next few days.
    def when(days_ahead, hour, minute=0):
        d = datetime.combine(today + timedelta(days=days_ahead), datetime.min.time())
        return d.replace(hour=hour, minute=minute).isoformat()

    classes = [
        ("K1 Striking", 1, when(1, 7, 0), 16),
        ("BJJ — Gi Fundamentals", 2, when(1, 18, 0), 20),
        ("BJJ — No-Gi", 3, when(2, 19, 0), 20),
        ("K1 Sparring", 4, when(2, 20, 0), 12),
        ("BJJ — Gi Advanced", 2, when(3, 18, 30), 16),
        ("K1 Conditioning", 1, when(4, 7, 0), 18),
    ]
    conn.executemany(
        "INSERT INTO classes (name, coach_id, start_time, capacity) VALUES (?, ?, ?, ?)",
        classes,
    )

    conn.commit()


def _seed_if_empty(conn):
    """Seed achievements and events if their tables are empty.

    Runs on every startup (cheap COUNT checks) so sections added after the
    database already existed still get their demo content.
    """
    today = date.today()

    if conn.execute("SELECT COUNT(*) AS n FROM achievements").fetchone()["n"] == 0:
        achievements = [
            # title, athlete, year, icon
            ("National K1 Champion — Lightweight", "Mike Chen", 2025, "🥇"),
            ("IBJJF No-Gi Gold", "Ava Patel", 2025, "🥇"),
            ("Gym of the Year — State Federation", "Monarch Fight Academy", 2024, "🏆"),
            ("BJJ Gi Silver — National Open", "Sarah Jones", 2024, "🥈"),
            ("K1 Fastest KO of the Night", "Mike Chen", 2024, "⚡"),
            ("Coach of the Year", "Rowan", 2023, "🎖️"),
        ]
        conn.executemany(
            "INSERT INTO achievements (title, athlete, year, icon) VALUES (?, ?, ?, ?)",
            achievements,
        )

    if conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 0:
        def when(days_ahead):
            return (today + timedelta(days=days_ahead)).isoformat()

        events = [
            # name, kind, location, date, headline
            ("Monarch Fight Night 12", "fight", "Monarch Arena", when(9),
             "Mike Chen vs. Diego Alvarez — Lightweight Main Event"),
            ("City Grappling Open", "tournament", "Downtown Convention Center", when(21),
             "Open & masters divisions · gi and no-gi"),
            ("Interclub Sparring Showcase", "fight", "Monarch Arena", when(30),
             "Monarch vs. Ironside Gym — 6 bouts"),
            ("National Muay Thai Championships", "tournament", "National Stadium", when(54),
             "Sarah Jones defends her regional title"),
            ("Rookie Smoker Night", "fight", "Monarch Arena", when(75),
             "First-time amateurs · 8 debut bouts"),
        ]
        conn.executemany(
            """INSERT INTO events (name, kind, location, event_date, headline)
               VALUES (?, ?, ?, ?, ?)""",
            events,
        )

    if conn.execute("SELECT COUNT(*) AS n FROM library_items").fetchone()["n"] == 0:
        # trainer_id, kind, title, category, description, video_url, content
        items = [
            (1, "video", "K1 Low-Kick Fundamentals", "K1",
             "Checking and throwing low kicks under pressure.",
             "https://www.youtube.com/embed/dQw4w9WgXcQ", None),
            (1, "video", "Southpaw Striking Angles", "K1",
             "Footwork and angles for southpaw strikers.",
             "https://www.youtube.com/embed/dQw4w9WgXcQ", None),
            (2, "video", "Closed Guard Attacks (Gi)", "BJJ",
             "Three high-percentage submissions from closed guard.",
             "https://www.youtube.com/embed/dQw4w9WgXcQ", None),
            (3, "workout", "No-Gi Conditioning Circuit", "BJJ", None, None,
             "4 rounds, 5 min each:\n- 20 shrimps\n- 10 sprawls\n- 15 sit-outs\n- 30s plank\nRest 60s between rounds."),
            (4, "workout", "Fighter Strength — Lower Body", "Strength", None, None,
             "5x5 Back Squat\n4x8 Romanian Deadlift\n3x12 Walking Lunges\n3x15 Calf Raises\nFinisher: 100 bodyweight squats for time."),
            (1, "video", "Clinch Entries & Knees", "K1",
             "Entering the clinch safely and landing knees.",
             "https://www.youtube.com/embed/dQw4w9WgXcQ", None),
        ]
        conn.executemany(
            """INSERT INTO library_items
               (trainer_id, kind, title, category, description, video_url, content, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            items,
        )

    # Athletes (competitors the gym fields). Names match achievement athletes
    # so each athlete's card can pull their achievements. Some do two disciplines.
    if conn.execute("SELECT COUNT(*) AS n FROM athletes").fetchone()["n"] == 0:
        athletes = [
            # name, sport, record, sport2, record2
            ("Mike Chen", "K1 Kickboxing", "15-2-0 (W-L-D)", "BJJ Gi", "6-1 (blue belt)"),
            ("Ava Patel", "BJJ No-Gi", "22-5 submissions", "BJJ Gi", "14-3 (W-L)"),
            ("Sarah Jones", "BJJ Gi", "9-3-0 (W-L-D)", None, None),
            ("Diego Alvarez", "K1 Kickboxing", "11-4-1 (W-L-D)", None, None),
        ]
        conn.executemany(
            "INSERT INTO athletes (name, sport, record, sport2, record2) VALUES (?, ?, ?, ?, ?)",
            athletes,
        )

    # Weekly recurring timetable (the real Monarch Fight Academy schedule).
    if conn.execute("SELECT COUNT(*) AS n FROM timetable").fetchone()["n"] == 0:
        # Map coach names -> ids (Joshua, Rowan, Julio, Dennis). Fall back safely.
        cmap = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM coaches")}
        def cid(name):
            return cmap.get(name)
        JO, RO, JU, DE = cid("Joshua"), cid("Rowan"), cid("Julio"), cid("Dennis")
        # (day 0=Mon..6=Sun, time, class name, coach_id, capacity, prebook)
        slots = [
            # Tuesday
            (1, "07:00", "KickFit", JO, 16, 1),
            (1, "08:00", "Kickboxing (K1)", JO, 20, 0),
            (1, "17:00", "Kids Kickboxing (K1)", JO, 16, 0),
            (1, "18:00", "BJJ Gi — Beginner Friendly", DE, 20, 0),
            (1, "19:30", "Kickboxing (K1)", JO, 20, 0),
            # Thursday
            (3, "07:00", "Boxercise", JO, 16, 1),
            (3, "08:00", "Kickboxing (K1)", JO, 20, 0),
            (3, "17:00", "Kids Kickboxing (K1)", JO, 16, 0),
            (3, "18:00", "Kickboxing (K1)", JO, 20, 0),
            (3, "19:30", "No-Gi Jiu Jitsu", RO, 20, 0),
            # Wednesday
            (2, "09:00", "BJJ Gi", JU, 20, 0),
            (2, "17:00", "Kids BJJ Gi", RO, 16, 0),
            (2, "18:00", "No-Gi Jiu Jitsu", RO, 20, 0),
            (2, "19:30", "BJJ Gi", JU, 20, 0),
            # Monday
            (0, "17:00", "Kids BJJ Gi", RO, 16, 0),
            (0, "18:00", "Kickboxing (K1)", JO, 20, 0),
            (0, "19:30", "BJJ Gi", JU, 20, 0),
            # Friday
            (4, "17:00", "Kids BJJ Gi", RO, 16, 0),
            (4, "18:00", "Women-only BJJ", RO, 20, 0),
            (4, "19:30", "Open Mat", RO, 24, 0),
            # Saturday
            (5, "11:00", "Kids Kickboxing (K1)", JO, 16, 0),
            (5, "12:00", "Kickboxing (K1)", JO, 20, 0),
            # Sunday
            (6, "12:00", "Open Mat", RO, 24, 0),
        ]
        conn.executemany(
            """INSERT INTO timetable (day_of_week, start_hhmm, name, coach_id, capacity, prebook)
               VALUES (?, ?, ?, ?, ?, ?)""",
            slots,
        )

    # Register a demo member (sarah = id 1) into a couple of events.
    if conn.execute("SELECT COUNT(*) AS n FROM event_participants").fetchone()["n"] == 0:
        ev = conn.execute("SELECT id FROM events ORDER BY event_date LIMIT 2").fetchall()
        mem = conn.execute("SELECT id FROM members ORDER BY id").fetchall()
        now = datetime.now().isoformat()
        if ev and mem:
            # sarah registered + confirmed; a couple more members on event 1.
            conn.execute(
                "INSERT OR IGNORE INTO event_participants (event_id, member_id, status, created_at) VALUES (?,?,?,?)",
                (ev[0]["id"], mem[0]["id"], "confirmed", now),
            )
            if len(ev) > 1:
                conn.execute(
                    "INSERT OR IGNORE INTO event_participants (event_id, member_id, status, created_at) VALUES (?,?,?,?)",
                    (ev[1]["id"], mem[0]["id"], "registered", now),
                )
            for m in mem[1:3]:
                conn.execute(
                    "INSERT OR IGNORE INTO event_participants (event_id, member_id, status, created_at) VALUES (?,?,?,?)",
                    (ev[0]["id"], m["id"], "registered", now),
                )

    conn.commit()


# ---- Query helpers -------------------------------------------------------

def get_member(member_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    return row


def get_member_by_username(username):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM members WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return row


def days_remaining(expiry_date_str):
    """Whole days from today until expiry (negative if already expired)."""
    expiry = date.fromisoformat(expiry_date_str)
    return (expiry - date.today()).days


def list_classes(member_id):
    """Classes with coach name, booked count, spots left, and whether this member booked."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.start_time, c.capacity,
               co.name AS coach_name,
               (SELECT COUNT(*) FROM bookings b WHERE b.class_id = c.id) AS booked,
               EXISTS(
                   SELECT 1 FROM bookings b
                   WHERE b.class_id = c.id AND b.member_id = ?
               ) AS mine
        FROM classes c
        JOIN coaches co ON co.id = c.coach_id
        ORDER BY c.start_time
        """,
        (member_id,),
    ).fetchall()
    conn.close()
    return rows


def book_class(member_id, class_id):
    """Book a spot. Returns (ok, message)."""
    conn = get_db()
    try:
        cls = conn.execute(
            "SELECT capacity FROM classes WHERE id = ?", (class_id,)
        ).fetchone()
        if cls is None:
            return False, "Class not found."

        booked = conn.execute(
            "SELECT COUNT(*) AS n FROM bookings WHERE class_id = ?", (class_id,)
        ).fetchone()["n"]
        if booked >= cls["capacity"]:
            return False, "Sorry, this class is full."

        conn.execute(
            "INSERT INTO bookings (member_id, class_id, created_at) VALUES (?, ?, ?)",
            (member_id, class_id, datetime.now().isoformat()),
        )
        conn.commit()
        return True, "Class booked!"
    except sqlite3.IntegrityError:
        # UNIQUE(member_id, class_id) violated — already booked.
        return False, "You've already booked this class."
    finally:
        conn.close()


def cancel_booking(member_id, class_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM bookings WHERE member_id = ? AND class_id = ?",
        (member_id, class_id),
    )
    conn.commit()
    conn.close()
    return True, "Booking cancelled."


def list_coaches():
    conn = get_db()
    rows = conn.execute("SELECT * FROM coaches ORDER BY name").fetchall()
    conn.close()
    return rows


def save_message(member_id, coach_id, body):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (member_id, coach_id, body, created_at) VALUES (?, ?, ?, ?)",
        (member_id, coach_id, body, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def list_achievements():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM achievements ORDER BY year DESC, id"
    ).fetchall()
    conn.close()
    return rows


def list_upcoming_events():
    """Future events only, soonest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM events WHERE event_date >= ? ORDER BY event_date",
        (date.today().isoformat(),),
    ).fetchall()
    conn.close()
    return rows


# ---- Social login (demo) -------------------------------------------------

def get_or_create_social_member(provider, email, full_name):
    """Find a member by email, or create one for a social (Google/Apple) login.

    This is a local DEMO: no real OAuth token is verified. New social members
    start with no active plan so they can try the 'buy membership' flow.
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM members WHERE email = ?", (email,)).fetchone()
    if row:
        conn.close()
        return row["id"]

    today = date.today()
    # Username derived from email local part, de-duplicated if needed.
    base = email.split("@")[0]
    username = base
    n = 1
    while conn.execute(
        "SELECT 1 FROM members WHERE username = ?", (username,)
    ).fetchone():
        n += 1
        username = f"{base}{n}"

    cur = conn.execute(
        """INSERT INTO members
           (username, password_hash, full_name, plan_name, plan_status,
            start_date, expiry_date, email, auth_provider)
           VALUES (?, '', ?, 'No active plan', 'expired', ?, ?, ?, ?)""",
        (username, full_name, today.isoformat(), today.isoformat(), email, provider),
    )
    conn.commit()
    member_id = cur.lastrowid
    conn.close()
    return member_id


# ---- Membership plans & purchase -----------------------------------------

# Prototype catalogue. Prices in the app currency (EUR). (duration in days)
PLANS = [
    {"name": "Monthly membership", "price": 100.0, "days": 30, "blurb": "Unlimited access for a month."},
    {"name": "Weekly membership", "price": 25.0, "days": 7, "blurb": "A full week of training."},
    {"name": "Day pass", "price": 15.0, "days": 1, "blurb": "Single-day full access."},
]


def get_plan(plan_name):
    for p in PLANS:
        if p["name"] == plan_name:
            return p
    return None


def purchase_plan(member_id, plan_name, method):
    """Apply a purchased plan to a member and record a (dummy) payment.

    Extends from today (or from current expiry if still active) so renewals
    stack. Returns (ok, message).
    """
    plan = get_plan(plan_name)
    if plan is None:
        return False, "Unknown plan."

    conn = get_db()
    member = conn.execute(
        "SELECT expiry_date, plan_status FROM members WHERE id = ?", (member_id,)
    ).fetchone()
    if member is None:
        conn.close()
        return False, "Member not found."

    today = date.today()
    current_expiry = date.fromisoformat(member["expiry_date"])
    # Stack onto remaining time if the plan is still active.
    base = current_expiry if current_expiry > today else today
    new_expiry = base + timedelta(days=plan["days"])

    conn.execute(
        """UPDATE members
           SET plan_name = ?, plan_status = 'active',
               start_date = ?, expiry_date = ?
           WHERE id = ?""",
        (plan["name"], today.isoformat(), new_expiry.isoformat(), member_id),
    )
    conn.execute(
        """INSERT INTO payments (member_id, plan_name, amount, method, paid_at)
           VALUES (?, ?, ?, ?, ?)""",
        (member_id, plan["name"], plan["price"], method, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return True, f"{plan['name']} activated — valid until {new_expiry.strftime('%d %b %Y')}."


# ---- Reminders -----------------------------------------------------------

def add_reminder(member_id, message, due_date, kind="payment"):
    conn = get_db()
    conn.execute(
        """INSERT INTO reminders (member_id, message, due_date, kind, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (member_id, message, due_date, kind, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def active_reminders_for(member_id):
    """Reminders that are not dismissed and are due today or in the past."""
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM reminders
           WHERE member_id = ? AND dismissed = 0 AND due_date <= ?
           ORDER BY due_date""",
        (member_id, date.today().isoformat()),
    ).fetchall()
    conn.close()
    return rows


def dismiss_reminder(reminder_id, member_id):
    conn = get_db()
    conn.execute(
        "UPDATE reminders SET dismissed = 1 WHERE id = ? AND member_id = ?",
        (reminder_id, member_id),
    )
    conn.commit()
    conn.close()


# ---- Admin CRUD ----------------------------------------------------------

def list_members():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM members ORDER BY full_name"
    ).fetchall()
    conn.close()
    return rows


def admin_create_member(username, password, full_name, plan_name, days):
    """Create a password-based member from the admin panel. Returns (ok, msg)."""
    conn = get_db()
    if conn.execute(
        "SELECT 1 FROM members WHERE username = ?", (username,)
    ).fetchone():
        conn.close()
        return False, "That username already exists."

    today = date.today()
    expiry = today + timedelta(days=int(days))
    conn.execute(
        """INSERT INTO members
           (username, password_hash, full_name, plan_name, plan_status,
            start_date, expiry_date, auth_provider)
           VALUES (?, ?, ?, ?, 'active', ?, ?, 'password')""",
        (
            username,
            generate_password_hash(password),
            full_name,
            plan_name,
            today.isoformat(),
            expiry.isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return True, f"Member '{username}' created."


def admin_add_event(name, kind, location, event_date, headline):
    conn = get_db()
    conn.execute(
        """INSERT INTO events (name, kind, location, event_date, headline)
           VALUES (?, ?, ?, ?, ?)""",
        (name, kind, location, event_date, headline),
    )
    conn.commit()
    conn.close()


def admin_delete_event(event_id):
    conn = get_db()
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


def all_events():
    """Every event (admin view), newest date last."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM events ORDER BY event_date").fetchall()
    conn.close()
    return rows




# ---- Workouts ------------------------------------------------------------

def add_workout(member_id, kind, title, workout_date, duration_min=None,
                distance_km=None, notes=None):
    conn = get_db()
    conn.execute(
        """INSERT INTO workouts
           (member_id, kind, title, workout_date, duration_min, distance_km,
            notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (member_id, kind, title, workout_date, duration_min, distance_km,
         notes, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def list_workouts(member_id):
    """A member's own workouts, most recent first."""
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM workouts WHERE member_id = ?
           ORDER BY workout_date DESC, id DESC""",
        (member_id,),
    ).fetchall()
    conn.close()
    return rows


def workout_summary(member_id):
    """Totals for a member's dashboard: counts, distance, minutes."""
    conn = get_db()
    row = conn.execute(
        """SELECT
               COUNT(*) AS total,
               SUM(CASE WHEN kind = 'run' THEN 1 ELSE 0 END) AS runs,
               SUM(CASE WHEN kind = 'gym' THEN 1 ELSE 0 END) AS gym,
               COALESCE(SUM(distance_km), 0) AS total_km,
               COALESCE(SUM(duration_min), 0) AS total_min
           FROM workouts WHERE member_id = ?""",
        (member_id,),
    ).fetchone()
    conn.close()
    return row


def all_workouts_with_member():
    """Every workout joined to its member — the coach/admin tracking view."""
    conn = get_db()
    rows = conn.execute(
        """SELECT w.*, m.full_name, m.username
           FROM workouts w
           JOIN members m ON m.id = w.member_id
           ORDER BY w.workout_date DESC, w.id DESC""",
    ).fetchall()
    conn.close()
    return rows


def workouts_for_member(member_id):
    """Admin view of one member's workouts with the member's name attached."""
    conn = get_db()
    rows = conn.execute(
        """SELECT w.*, m.full_name, m.username
           FROM workouts w
           JOIN members m ON m.id = w.member_id
           WHERE w.member_id = ?
           ORDER BY w.workout_date DESC, w.id DESC""",
        (member_id,),
    ).fetchall()
    conn.close()
    return rows


# ---- Virtual Training Library & subscription -----------------------------

LIBRARY_SUB_PRICE = 10.0   # EUR / month


def has_active_library_sub(member_id):
    row = get_member(member_id)
    if not row or not row["has_library_sub"]:
        return False
    until = row["library_sub_until"]
    if not until:
        return False
    return date.fromisoformat(until) >= date.today()


def start_library_sub(member_id):
    """Activate / renew the €10/mo library subscription (dummy payment)."""
    conn = get_db()
    row = conn.execute(
        "SELECT library_sub_until FROM members WHERE id = ?", (member_id,)
    ).fetchone()
    today = date.today()
    base = today
    if row and row["library_sub_until"]:
        current = date.fromisoformat(row["library_sub_until"])
        if current > today:
            base = current
    until = base + timedelta(days=30)
    conn.execute(
        "UPDATE members SET has_library_sub = 1, library_sub_until = ? WHERE id = ?",
        (until.isoformat(), member_id),
    )
    conn.execute(
        """INSERT INTO payments (member_id, plan_name, amount, method, paid_at)
           VALUES (?, 'Training Library (monthly)', ?, 'Revolut Pay (demo)', ?)""",
        (member_id, LIBRARY_SUB_PRICE, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return until


def cancel_library_sub(member_id):
    conn = get_db()
    conn.execute(
        "UPDATE members SET has_library_sub = 0 WHERE id = ?", (member_id,)
    )
    conn.commit()
    conn.close()


def list_library_items(kind=None):
    conn = get_db()
    if kind:
        rows = conn.execute(
            """SELECT li.*, c.name AS trainer_name
               FROM library_items li LEFT JOIN coaches c ON c.id = li.trainer_id
               WHERE li.kind = ? ORDER BY li.category, li.title""",
            (kind,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT li.*, c.name AS trainer_name
               FROM library_items li LEFT JOIN coaches c ON c.id = li.trainer_id
               ORDER BY li.category, li.title"""
        ).fetchall()
    conn.close()
    return rows


def get_library_item(item_id):
    conn = get_db()
    row = conn.execute(
        """SELECT li.*, c.name AS trainer_name
           FROM library_items li LEFT JOIN coaches c ON c.id = li.trainer_id
           WHERE li.id = ?""",
        (item_id,),
    ).fetchone()
    conn.close()
    return row


def admin_add_library_item(trainer_id, kind, title, category, description,
                           video_url, content):
    conn = get_db()
    conn.execute(
        """INSERT INTO library_items
           (trainer_id, kind, title, category, description, video_url, content, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (trainer_id or None, kind, title, category, description or None,
         video_url or None, content or None, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def admin_delete_library_item(item_id):
    conn = get_db()
    conn.execute("DELETE FROM library_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


# ---- 1-to-1 (PT) session booking -----------------------------------------

def book_pt_session(member_id, coach_id, slot_time):
    conn = get_db()
    conn.execute(
        """INSERT INTO pt_sessions (member_id, coach_id, slot_time, created_at)
           VALUES (?, ?, ?, ?)""",
        (member_id, coach_id, slot_time, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return True, "1-to-1 session requested — a coach will confirm."


def list_pt_sessions(member_id):
    conn = get_db()
    rows = conn.execute(
        """SELECT p.*, c.name AS coach_name, c.specialty
           FROM pt_sessions p JOIN coaches c ON c.id = p.coach_id
           WHERE p.member_id = ?
           ORDER BY p.slot_time DESC""",
        (member_id,),
    ).fetchall()
    conn.close()
    return rows


def all_pt_sessions():
    """Admin view: every requested 1-to-1 session."""
    conn = get_db()
    rows = conn.execute(
        """SELECT p.*, c.name AS coach_name, m.full_name
           FROM pt_sessions p
           JOIN coaches c ON c.id = p.coach_id
           JOIN members m ON m.id = p.member_id
           ORDER BY p.slot_time DESC""",
    ).fetchall()
    conn.close()
    return rows


# ---- Sets & reps (attached to a gym workout) -----------------------------

def add_workout_with_sets(member_id, title, workout_date, duration_min, notes, sets):
    """Create a gym workout and its set rows in one transaction.

    `sets` is a list of dicts: {exercise, set_no, reps, weight_kg}.
    Returns the new workout id.
    """
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO workouts
           (member_id, kind, title, workout_date, duration_min, distance_km,
            notes, created_at)
           VALUES (?, 'gym', ?, ?, ?, NULL, ?, ?)""",
        (member_id, title, workout_date, duration_min, notes,
         datetime.now().isoformat()),
    )
    workout_id = cur.lastrowid
    for s in sets:
        conn.execute(
            """INSERT INTO exercise_sets (workout_id, exercise, set_no, reps, weight_kg)
               VALUES (?, ?, ?, ?, ?)""",
            (workout_id, s["exercise"], s["set_no"], s.get("reps"), s.get("weight_kg")),
        )
    conn.commit()
    conn.close()
    return workout_id


def sets_for_workout(workout_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM exercise_sets WHERE workout_id = ? ORDER BY id",
        (workout_id,),
    ).fetchall()
    conn.close()
    return rows


# ---- Anonymous feedback --------------------------------------------------

def add_feedback(body, rating=None):
    """Store feedback with NO member link — fully anonymous."""
    conn = get_db()
    conn.execute(
        "INSERT INTO feedback (body, rating, created_at) VALUES (?, ?, ?)",
        (body, rating, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def list_feedback(limit=200):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def feedback_count():
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"]
    conn.close()
    return n


# Common words to exclude from the word cloud.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "to", "of", "in", "on", "for", "with", "at", "by", "it", "this",
    "that", "i", "we", "you", "they", "my", "our", "me", "us", "so", "very",
    "too", "really", "just", "have", "has", "had", "do", "does", "did", "not",
    "no", "yes", "can", "could", "would", "should", "will", "if", "as", "from",
    "about", "there", "here", "all", "more", "some", "than", "then", "them",
    "its", "their", "your", "his", "her", "he", "she", "am", "get", "got",
    "much", "lot", "also", "which", "when", "what", "who", "how", "where",
}


def feedback_word_cloud(top_n=40):
    """Return [(word, count), ...] for the most frequent meaningful words.

    Pure-Python frequency count with stopword filtering — no external service.
    """
    import re
    from collections import Counter

    counter = Counter()
    for row in list_feedback(limit=1000):
        words = re.findall(r"[a-zA-Z']{3,}", (row["body"] or "").lower())
        for w in words:
            if w not in _STOPWORDS:
                counter[w] += 1
    return counter.most_common(top_n)


# ---- AI consent (GDPR opt-in) --------------------------------------------

def set_ai_consent(member_id, consent: bool):
    conn = get_db()
    conn.execute(
        "UPDATE members SET ai_consent = ? WHERE id = ?",
        (1 if consent else 0, member_id),
    )
    conn.commit()
    conn.close()


def has_ai_consent(member_id):
    row = get_member(member_id)
    return bool(row and row["ai_consent"])


# ---- Member activity context (AGGREGATES ONLY — no raw logs, no PII) ------

def member_ai_context(member_id):
    """Return a small dict of NON-identifying aggregate stats for the AI.

    Deliberately excludes name, email, username, and any free-text so that
    nothing personally identifying is ever sent to the AI processor.
    """
    conn = get_db()
    m = conn.execute(
        """SELECT plan_name, plan_status, expiry_date, has_library_sub
           FROM members WHERE id = ?""",
        (member_id,),
    ).fetchone()

    classes_booked = conn.execute(
        "SELECT COUNT(*) AS n FROM bookings WHERE member_id = ?", (member_id,)
    ).fetchone()["n"]

    w = conn.execute(
        """SELECT
               COUNT(*) AS total,
               SUM(CASE WHEN kind='run' THEN 1 ELSE 0 END) AS runs,
               SUM(CASE WHEN kind='gym' THEN 1 ELSE 0 END) AS gym,
               COALESCE(SUM(distance_km),0) AS km,
               COALESCE(SUM(duration_min),0) AS mins
           FROM workouts WHERE member_id = ?""",
        (member_id,),
    ).fetchone()

    pt = conn.execute(
        "SELECT COUNT(*) AS n FROM pt_sessions WHERE member_id = ?", (member_id,)
    ).fetchone()["n"]
    conn.close()

    remaining = days_remaining(m["expiry_date"]) if m else 0
    return {
        "plan": m["plan_name"] if m else "n/a",
        "membership_active": bool(m and m["plan_status"] == "active" and remaining >= 0),
        "days_until_expiry": remaining,
        "library_subscriber": bool(m and m["has_library_sub"]),
        "classes_booked": classes_booked,
        "workouts_total": w["total"] or 0,
        "runs": w["runs"] or 0,
        "gym_sessions": w["gym"] or 0,
        "total_distance_km": round(w["km"] or 0, 1),
        "total_minutes": w["mins"] or 0,
        "pt_sessions": pt,
    }


# ---- Admin business stats (AGGREGATES ONLY — no member names to AI) -------

def admin_business_stats():
    conn = get_db()
    today = date.today().isoformat()

    total = conn.execute("SELECT COUNT(*) AS n FROM members").fetchone()["n"]
    active = conn.execute(
        "SELECT COUNT(*) AS n FROM members WHERE plan_status='active' AND expiry_date >= ?",
        (today,),
    ).fetchone()["n"]
    expired = conn.execute(
        "SELECT COUNT(*) AS n FROM members WHERE plan_status != 'active' OR expiry_date < ?",
        (today,),
    ).fetchone()["n"]
    expiring_7d = conn.execute(
        """SELECT COUNT(*) AS n FROM members
           WHERE plan_status='active' AND expiry_date >= ? AND expiry_date <= date(?, '+7 day')""",
        (today, today),
    ).fetchone()["n"]
    lib_subs = conn.execute(
        "SELECT COUNT(*) AS n FROM members WHERE has_library_sub = 1"
    ).fetchone()["n"]
    revenue = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM payments"
    ).fetchone()["s"]
    pending_pt = conn.execute(
        "SELECT COUNT(*) AS n FROM pt_sessions WHERE status='booked'"
    ).fetchone()["n"]
    fb_count = conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"]
    upcoming_events = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_date >= ?", (today,)
    ).fetchone()["n"]
    conn.close()

    return {
        "total_members": total,
        "active_members": active,
        "expired_or_unpaid": expired,
        "expiring_within_7d": expiring_7d,
        "library_subscribers": lib_subs,
        "total_revenue_eur": round(revenue, 2),
        "pending_pt_requests": pending_pt,
        "feedback_count": fb_count,
        "upcoming_events": upcoming_events,
    }


# ---- GDPR: right to erasure ----------------------------------------------

def erase_member_data(member_id):
    """Delete all personal data for a member (GDPR Art. 17 right to erasure).

    Removes bookings, workouts (and their sets), PT sessions, reminders,
    payments, and the member row itself. Anonymous feedback is untouched
    because it is not linked to any member.
    """
    conn = get_db()
    conn.execute(
        """DELETE FROM exercise_sets WHERE workout_id IN
           (SELECT id FROM workouts WHERE member_id = ?)""",
        (member_id,),
    )
    for tbl in ("bookings", "workouts", "pt_sessions", "reminders", "payments"):
        conn.execute(f"DELETE FROM {tbl} WHERE member_id = ?", (member_id,))
    conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
    conn.commit()
    conn.close()


# ---- Health metrics (sleep, steps, calories, HR) -------------------------

def upsert_health_metric(member_id, metric_date, steps=None, sleep_hours=None,
                         calories=None, resting_hr=None, source="manual"):
    """Insert or update a member's metrics for one day."""
    conn = get_db()
    conn.execute(
        """INSERT INTO health_metrics
             (member_id, metric_date, steps, sleep_hours, calories, resting_hr, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(member_id, metric_date) DO UPDATE SET
             steps       = COALESCE(excluded.steps, steps),
             sleep_hours = COALESCE(excluded.sleep_hours, sleep_hours),
             calories    = COALESCE(excluded.calories, calories),
             resting_hr  = COALESCE(excluded.resting_hr, resting_hr),
             source      = excluded.source""",
        (member_id, metric_date, steps, sleep_hours, calories, resting_hr, source),
    )
    conn.commit()
    conn.close()


def today_health(member_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM health_metrics WHERE member_id = ? AND metric_date = ?",
        (member_id, date.today().isoformat()),
    ).fetchone()
    conn.close()
    return row


def recent_health(member_id, days=7):
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM health_metrics WHERE member_id = ?
           ORDER BY metric_date DESC LIMIT ?""",
        (member_id, days),
    ).fetchall()
    conn.close()
    return list(rows)


def set_health_source(member_id, source):
    conn = get_db()
    conn.execute(
        "UPDATE members SET health_source = ? WHERE id = ?", (source, member_id)
    )
    conn.commit()
    conn.close()


def simulate_sync(member_id, source, days=7):
    """DEMO: generate realistic health data as if synced from Apple/Google.

    Replace this with a real HealthKit / Google Fit import in a native build.
    """
    import random

    set_health_source(member_id, source)
    today = date.today()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        upsert_health_metric(
            member_id,
            d,
            steps=random.randint(4000, 13000),
            sleep_hours=round(random.uniform(5.5, 8.5), 1),
            calories=random.randint(1900, 2900),
            resting_hr=random.randint(52, 68),
            source=source,
        )


# ---- Today's classes (Home screen) ---------------------------------------

# ---- Timetable (recurring weekly schedule) -------------------------------

def _slot_booked_count(conn, slot_id, class_date):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM timetable_bookings WHERE slot_id = ? AND class_date = ?",
        (slot_id, class_date),
    ).fetchone()["n"]


def _week_dates():
    """Return the date for each weekday (Mon..Sun) in the current week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def week_timetable(member_id):
    """The full weekly timetable grouped by day, with booking info for this member."""
    conn = get_db()
    slots = conn.execute(
        """SELECT t.*, co.name AS coach_name
           FROM timetable t LEFT JOIN coaches co ON co.id = t.coach_id
           ORDER BY t.day_of_week, t.start_hhmm"""
    ).fetchall()
    week = _week_dates()
    days = [{"index": i, "label": lbl, "date": week[i], "slots": []}
            for i, lbl in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday",
                                     "Friday", "Saturday", "Sunday"])]
    for s in slots:
        d = week[s["day_of_week"]]
        booked = _slot_booked_count(conn, s["id"], d.isoformat())
        mine = conn.execute(
            "SELECT 1 FROM timetable_bookings WHERE slot_id=? AND class_date=? AND member_id=?",
            (s["id"], d.isoformat(), member_id),
        ).fetchone() is not None
        days[s["day_of_week"]]["slots"].append({
            "id": s["id"], "time": s["start_hhmm"], "name": s["name"],
            "coach": s["coach_name"] or "TBA", "capacity": s["capacity"],
            "prebook": bool(s["prebook"]), "booked": booked,
            "spots_left": s["capacity"] - booked, "mine": mine,
            "date": d.isoformat(),
            "past": d < date.today(),
        })
    conn.close()
    return days


def todays_timetable(member_id):
    """Just today's slots (for the home screen)."""
    all_days = week_timetable(member_id)
    return all_days[date.today().weekday()]["slots"]


def book_slot(member_id, slot_id, class_date):
    """Book a timetable slot for a specific date. Returns (ok, message)."""
    conn = get_db()
    try:
        slot = conn.execute("SELECT * FROM timetable WHERE id = ?", (slot_id,)).fetchone()
        if slot is None:
            return False, "Class not found."
        if _slot_booked_count(conn, slot_id, class_date) >= slot["capacity"]:
            return False, "Sorry, this class is full."
        conn.execute(
            """INSERT INTO timetable_bookings (member_id, slot_id, class_date, created_at)
               VALUES (?, ?, ?, ?)""",
            (member_id, slot_id, class_date, datetime.now().isoformat()),
        )
        conn.commit()
        return True, f"Booked {slot['name']} on {class_date}."
    except sqlite3.IntegrityError:
        return False, "You've already booked this class."
    finally:
        conn.close()


def cancel_slot(member_id, slot_id, class_date):
    conn = get_db()
    conn.execute(
        "DELETE FROM timetable_bookings WHERE member_id=? AND slot_id=? AND class_date=?",
        (member_id, slot_id, class_date),
    )
    conn.commit()
    conn.close()
    return True, "Booking cancelled."


# ---- Leaderboards --------------------------------------------------------

def _lb_rows(conn, sql):
    return [dict(r) for r in conn.execute(sql).fetchall()]


def leaderboard_running(limit=10):
    conn = get_db()
    rows = _lb_rows(conn, f"""
        SELECT m.full_name, ROUND(COALESCE(SUM(w.distance_km),0),1) AS value
        FROM members m JOIN workouts w ON w.member_id = m.id AND w.kind='run'
        GROUP BY m.id HAVING value > 0 ORDER BY value DESC LIMIT {int(limit)}""")
    conn.close()
    return rows


def leaderboard_gym(limit=10):
    conn = get_db()
    rows = _lb_rows(conn, f"""
        SELECT m.full_name, COUNT(*) AS value
        FROM members m JOIN workouts w ON w.member_id = m.id AND w.kind='gym'
        GROUP BY m.id HAVING value > 0 ORDER BY value DESC LIMIT {int(limit)}""")
    conn.close()
    return rows


def leaderboard_weight(limit=10):
    """Total volume lifted = sum(reps * weight_kg) across a member's sets."""
    conn = get_db()
    rows = _lb_rows(conn, f"""
        SELECT m.full_name, ROUND(COALESCE(SUM(es.reps * es.weight_kg),0),0) AS value
        FROM members m
        JOIN workouts w ON w.member_id = m.id
        JOIN exercise_sets es ON es.workout_id = w.id
        GROUP BY m.id HAVING value > 0 ORDER BY value DESC LIMIT {int(limit)}""")
    conn.close()
    return rows


# ---- Personal athlete profile --------------------------------------------

def update_profile(member_id, sport, record, sport2, record2):
    conn = get_db()
    conn.execute(
        """UPDATE members SET athlete_sport=?, athlete_record=?,
           athlete_sport2=?, athlete_record2=? WHERE id=?""",
        (sport, record, sport2, record2, member_id),
    )
    conn.commit()
    conn.close()


# ---- Athletes & their achievements ---------------------------------------

def list_athletes():
    conn = get_db()
    rows = conn.execute("SELECT * FROM athletes ORDER BY name").fetchall()
    conn.close()
    return rows


def achievements_for_athlete(name):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM achievements WHERE athlete = ? ORDER BY year DESC",
        (name,),
    ).fetchall()
    conn.close()
    return rows


# ---- Event participation --------------------------------------------------

def events_for_member(member_id):
    """Events this member is registered for, with their status."""
    conn = get_db()
    rows = conn.execute(
        """SELECT e.*, ep.status
           FROM event_participants ep JOIN events e ON e.id = ep.event_id
           WHERE ep.member_id = ?
           ORDER BY e.event_date""",
        (member_id,),
    ).fetchall()
    conn.close()
    return rows


def get_event(event_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return row


def event_participants(event_id):
    """Participants of an event with names and status."""
    conn = get_db()
    rows = conn.execute(
        """SELECT m.full_name, m.username, ep.status
           FROM event_participants ep JOIN members m ON m.id = ep.member_id
           WHERE ep.event_id = ?
           ORDER BY m.full_name""",
        (event_id,),
    ).fetchall()
    conn.close()
    return rows


def is_registered(member_id, event_id):
    conn = get_db()
    row = conn.execute(
        "SELECT status FROM event_participants WHERE member_id = ? AND event_id = ?",
        (member_id, event_id),
    ).fetchone()
    conn.close()
    return row["status"] if row else None


def register_for_event(member_id, event_id):
    conn = get_db()
    conn.execute(
        """INSERT OR IGNORE INTO event_participants (event_id, member_id, status, created_at)
           VALUES (?, ?, 'registered', ?)""",
        (event_id, member_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def unregister_from_event(member_id, event_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM event_participants WHERE member_id = ? AND event_id = ?",
        (member_id, event_id),
    )
    conn.commit()
    conn.close()
