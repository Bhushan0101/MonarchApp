"""Admin backend: a password-protected area to manage the gym.

Admins can:
  - view all members
  - add new members
  - set a payment (or general) reminder for a member — the member sees it in-app
  - add and delete fights / tournaments

This is prototype-grade: a single shared admin password held in config, kept in
its own session key so admin and member sessions don't collide.
"""

from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import ai, db

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("is_admin"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        if request.form.get("password", "") == current_app.config["ADMIN_PASSWORD"]:
            session["is_admin"] = True
            return redirect(url_for("admin.dashboard"))
        flash("Wrong admin password.", "error")

    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin.login"))


@bp.route("/")
@admin_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        members=db.list_members(),
        events=db.all_events(),
    )


# ---- Workouts (coach tracking view) --------------------------------------
@bp.route("/workouts")
@admin_required
def workouts():
    # Optional filter by a single member.
    member_id = request.args.get("member_id", type=int)
    if member_id:
        rows = db.workouts_for_member(member_id)
    else:
        rows = db.all_workouts_with_member()
    return render_template(
        "admin/workouts.html",
        workouts=rows,
        members=db.list_members(),
        selected=member_id,
    )


# ---- Members -------------------------------------------------------------

@bp.route("/members/add", methods=["POST"])
@admin_required
def add_member():
    f = request.form
    ok, msg = db.admin_create_member(
        username=f.get("username", "").strip(),
        password=f.get("password", "").strip() or "monarch",
        full_name=f.get("full_name", "").strip() or "New Member",
        plan_name=f.get("plan_name", "Monthly Standard"),
        days=f.get("days", 30),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("admin.dashboard"))


# ---- Reminders -----------------------------------------------------------

@bp.route("/reminders/add", methods=["POST"])
@admin_required
def add_reminder():
    f = request.form
    member_id = f.get("member_id")
    message = f.get("message", "").strip()
    due_date = f.get("due_date", "").strip()
    if not (member_id and message and due_date):
        flash("Reminder needs a member, message, and date.", "error")
    else:
        db.add_reminder(int(member_id), message, due_date, kind=f.get("kind", "payment"))
        flash("Reminder set — the member will see it in-app.", "success")
    return redirect(url_for("admin.dashboard"))


# ---- Events (fights & tournaments) ---------------------------------------

@bp.route("/events/add", methods=["POST"])
@admin_required
def add_event():
    f = request.form
    name = f.get("name", "").strip()
    event_date = f.get("event_date", "").strip()
    if not (name and event_date):
        flash("Event needs at least a name and date.", "error")
    else:
        db.admin_add_event(
            name=name,
            kind=f.get("kind", "fight"),
            location=f.get("location", "").strip() or "Monarch Arena",
            event_date=event_date,
            headline=f.get("headline", "").strip() or "TBA",
        )
        flash(f"Event '{name}' added.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
@admin_required
def delete_event(event_id):
    db.admin_delete_event(event_id)
    flash("Event deleted.", "success")
    return redirect(url_for("admin.dashboard"))


# ---- Training Library (trainers create content) --------------------------

@bp.route("/library")
@admin_required
def library():
    return render_template(
        "admin/library.html",
        items=db.list_library_items(),
        coaches=db.list_coaches(),
        pt_sessions=db.all_pt_sessions(),
    )


@bp.route("/library/add", methods=["POST"])
@admin_required
def add_library_item():
    f = request.form
    title = f.get("title", "").strip()
    kind = f.get("kind", "video")
    if not title:
        flash("Give the item a title.", "error")
        return redirect(url_for("admin.library"))
    db.admin_add_library_item(
        trainer_id=f.get("trainer_id") or None,
        kind=kind,
        title=title,
        category=f.get("category", "").strip() or "General",
        description=f.get("description", "").strip(),
        video_url=f.get("video_url", "").strip(),
        content=f.get("content", "").strip(),
    )
    flash(f"Library {kind} '{title}' added.", "success")
    return redirect(url_for("admin.library"))


@bp.route("/library/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_library_item(item_id):
    db.admin_delete_library_item(item_id)
    flash("Library item deleted.", "success")
    return redirect(url_for("admin.library"))


# ---- Anonymous feedback: word cloud + AI summary -------------------------

@bp.route("/feedback")
@admin_required
def feedback():
    rows = db.list_feedback()
    texts = [r["body"] for r in rows]

    # Word cloud: scale counts to a font-size range for display.
    cloud_raw = db.feedback_word_cloud(top_n=40)
    cloud = []
    if cloud_raw:
        max_c = cloud_raw[0][1]
        min_c = cloud_raw[-1][1]
        span = max(max_c - min_c, 1)
        for word, count in cloud_raw:
            # size between 0.9rem and 2.6rem
            size = 0.9 + (count - min_c) / span * 1.7
            weight = 400 + int((count - min_c) / span * 400)  # 400-800
            cloud.append({"word": word, "count": count,
                          "size": round(size, 2), "weight": weight})

    summary, used_ai = ai.summarize_feedback(texts)

    return render_template(
        "admin/feedback.html",
        count=len(rows),
        cloud=cloud,
        summary=summary,
        used_ai=used_ai,
        recent=rows[:30],
    )


# ---- AI business assistant (admin) ---------------------------------------

@bp.route("/assistant", methods=["GET", "POST"])
@admin_required
def assistant():
    stats = db.admin_business_stats()
    answer = None
    question = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            answer, _ = ai.admin_business_chat(question, stats)
    else:
        # On first load, auto-generate an overview briefing.
        answer, _ = ai.admin_business_chat(
            "Give me a short overview of the gym's current status and the top "
            "3 things I should action today.",
            stats,
        )
    return render_template(
        "admin/assistant.html",
        stats=stats,
        answer=answer,
        question=question,
        ai_enabled=ai.ai_enabled(),
    )
