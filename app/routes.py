"""Main app screens: membership dashboard, classes, coaches."""

from datetime import date, datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import ai, db
from .auth import login_required

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def membership():
    member = db.get_member(session["member_id"])
    remaining = db.days_remaining(member["expiry_date"])

    # Treat a plan as effectively expired if the date has passed, regardless
    # of the stored status label.
    is_active = member["plan_status"] == "active" and remaining >= 0

    # Today's classes for the home screen (from the recurring timetable).
    classes_today = db.todays_timetable(session["member_id"])

    return render_template(
        "membership.html",
        member=member,
        remaining=remaining,
        is_active=is_active,
        start_date=date.fromisoformat(member["start_date"]),
        expiry_date=date.fromisoformat(member["expiry_date"]),
        reminders=db.active_reminders_for(member["id"]),
        classes_today=classes_today,
    )


@bp.route("/reminders/<int:reminder_id>/dismiss", methods=["POST"])
@login_required
def dismiss_reminder(reminder_id):
    db.dismiss_reminder(reminder_id, session["member_id"])
    return redirect(url_for("main.membership"))


# ---- Membership buying (dummy payment) -----------------------------------

@bp.route("/plans")
@login_required
def plans():
    member = db.get_member(session["member_id"])
    active = member["plan_name"] if member["plan_status"] == "active" and \
        db.days_remaining(member["expiry_date"]) >= 0 else None
    return render_template("plans.html", plans=db.PLANS, active_plan=active)


@bp.route("/plans/<plan_name>/checkout")
@login_required
def checkout(plan_name):
    plan = db.get_plan(plan_name)
    if plan is None:
        flash("Unknown plan.", "error")
        return redirect(url_for("main.plans"))
    return render_template("checkout.html", plan=plan)


@bp.route("/plans/<plan_name>/pay", methods=["POST"])
@login_required
def pay(plan_name):
    # DUMMY payment. No money moves. Intended to be replaced by Revolut Pay:
    # create an order via Revolut's Merchant API, redirect to their checkout,
    # then confirm on the webhook/return before calling purchase_plan().
    ok, msg = db.purchase_plan(
        session["member_id"], plan_name, method="Revolut Pay (demo)"
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("main.membership"))


@bp.route("/classes")
@login_required
def classes():
    week = db.week_timetable(session["member_id"])
    return render_template("classes.html", week=week, today_index=date.today().weekday())


@bp.route("/classes/<int:slot_id>/book", methods=["POST"])
@login_required
def book(slot_id):
    class_date = request.form.get("class_date", "")
    ok, msg = db.book_slot(session["member_id"], slot_id, class_date)
    flash(msg, "success" if ok else "error")
    return redirect(request.form.get("next") or url_for("main.classes"))


@bp.route("/classes/<int:slot_id>/cancel", methods=["POST"])
@login_required
def cancel(slot_id):
    class_date = request.form.get("class_date", "")
    _, msg = db.cancel_slot(session["member_id"], slot_id, class_date)
    flash(msg, "success")
    return redirect(request.form.get("next") or url_for("main.classes"))


@bp.route("/coaches")
@login_required
def coaches():
    return render_template("coaches.html", coaches=db.list_coaches())


@bp.route("/coaches/<int:coach_id>/message", methods=["POST"])
@login_required
def message_coach(coach_id):
    body = request.form.get("body", "").strip()
    if body:
        db.save_message(session["member_id"], coach_id, body)
        flash("Message sent to your coach!", "success")
    else:
        flash("Please type a message first.", "error")
    return redirect(url_for("main.coaches"))


@bp.route("/events")
@login_required
def events():
    member_id = session["member_id"]
    # Events the member is participating in (with their status).
    mine_rows = db.events_for_member(member_id)
    mine = []
    for r in mine_rows:
        d = date.fromisoformat(r["event_date"])
        start = datetime.fromisoformat(r["event_date"]) if "T" in r["event_date"] else None
        mine.append(
            {
                "id": r["id"],
                "name": r["name"],
                "kind": r["kind"],
                "location": r["location"],
                "when": d.strftime("%a %d %b %Y"),
                "time": start.strftime("%I:%M %p").lstrip("0") if start else "TBA",
                "status": r["status"],
                "headline": r["headline"],
            }
        )

    # All upcoming events (to browse / register).
    rows = db.list_upcoming_events()
    events_view = []
    for r in rows:
        d = date.fromisoformat(r["event_date"])
        days = (d - date.today()).days
        events_view.append(
            {
                "id": r["id"],
                "name": r["name"],
                "kind": r["kind"],
                "location": r["location"],
                "when": d.strftime("%a %d %b %Y"),
                "days": days,
                "headline": r["headline"],
                "registered": db.is_registered(member_id, r["id"]) is not None,
            }
        )
    return render_template(
        "events.html",
        mine=mine,
        events=events_view,
        achievements=db.list_achievements(),
    )


@bp.route("/events/<int:event_id>")
@login_required
def event_detail(event_id):
    ev = db.get_event(event_id)
    if ev is None:
        flash("Event not found.", "error")
        return redirect(url_for("main.events"))
    d = date.fromisoformat(ev["event_date"])
    participants = db.event_participants(event_id)
    return render_template(
        "event_detail.html",
        ev=ev,
        when=d.strftime("%a %d %b %Y"),
        participants=participants,
        count=len(participants),
        my_status=db.is_registered(session["member_id"], event_id),
    )


@bp.route("/events/<int:event_id>/register", methods=["POST"])
@login_required
def event_register(event_id):
    db.register_for_event(session["member_id"], event_id)
    flash("You're registered for this event.", "success")
    return redirect(url_for("main.event_detail", event_id=event_id))


@bp.route("/events/<int:event_id>/unregister", methods=["POST"])
@login_required
def event_unregister(event_id):
    db.unregister_from_event(session["member_id"], event_id)
    flash("You've withdrawn from this event.", "success")
    return redirect(url_for("main.event_detail", event_id=event_id))


# ---- Athletes ------------------------------------------------------------

@bp.route("/athletes")
@login_required
def athletes():
    rows = db.list_athletes()
    athletes_view = []
    for a in rows:
        disciplines = [{"sport": a["sport"], "record": a["record"]}]
        if a["sport2"]:
            disciplines.append({"sport": a["sport2"], "record": a["record2"]})
        athletes_view.append({
            "name": a["name"],
            "disciplines": disciplines,
            "achievements": db.achievements_for_athlete(a["name"]),
        })
    return render_template(
        "athletes.html",
        athletes=athletes_view,
        lb_running=db.leaderboard_running(),
        lb_gym=db.leaderboard_gym(),
        lb_weight=db.leaderboard_weight(),
    )


@bp.route("/me/athlete", methods=["GET", "POST"])
@login_required
def my_athlete():
    member_id = session["member_id"]
    if request.method == "POST":
        db.update_profile(
            member_id,
            sport=request.form.get("sport", "").strip(),
            record=request.form.get("record", "").strip(),
            sport2=request.form.get("sport2", "").strip(),
            record2=request.form.get("record2", "").strip(),
        )
        flash("Your athlete profile was updated.", "success")
        return redirect(url_for("main.my_athlete"))

    member = db.get_member(member_id)
    summary = db.workout_summary(member_id)
    # Compute this member's rank on each leaderboard.
    def rank_of(rows):
        for i, r in enumerate(rows, 1):
            if r["full_name"] == member["full_name"]:
                return i, r["value"]
        return None, 0
    run_rank, run_val = rank_of(db.leaderboard_running(limit=100))
    gym_rank, gym_val = rank_of(db.leaderboard_gym(limit=100))
    wt_rank, wt_val = rank_of(db.leaderboard_weight(limit=100))

    return render_template(
        "my_athlete.html",
        member=member,
        summary=summary,
        achievements=db.achievements_for_athlete(member["full_name"]),
        ranks={
            "running": (run_rank, run_val),
            "gym": (gym_rank, gym_val),
            "weight": (wt_rank, wt_val),
        },
    )


# ---- Workouts (member logs runs & gym sessions) --------------------------

@bp.route("/workouts")
@login_required
def workouts():
    member_id = session["member_id"]
    rows = db.list_workouts(member_id)
    workouts_view = []
    for r in rows:
        sets = db.sets_for_workout(r["id"])
        workouts_view.append(
            {
                "kind": r["kind"],
                "title": r["title"],
                "when": date.fromisoformat(r["workout_date"]).strftime("%a %d %b %Y"),
                "duration_min": r["duration_min"],
                "distance_km": r["distance_km"],
                "notes": r["notes"],
                "sets": sets,
            }
        )
    return render_template(
        "workouts.html",
        workouts=workouts_view,
        summary=db.workout_summary(member_id),
        today=date.today().isoformat(),
    )


@bp.route("/workouts/add", methods=["POST"])
@login_required
def add_workout():
    f = request.form
    kind = f.get("kind", "gym")
    title = f.get("title", "").strip()
    workout_date = f.get("workout_date", "").strip() or date.today().isoformat()

    if not title:
        flash("Give your workout a title.", "error")
        return redirect(url_for("main.workouts"))

    # Parse optional numeric fields safely.
    def num(name, cast):
        raw = f.get(name, "").strip()
        if not raw:
            return None
        try:
            return cast(raw)
        except ValueError:
            return None

    db.add_workout(
        member_id=session["member_id"],
        kind=kind,
        title=title,
        workout_date=workout_date,
        duration_min=num("duration_min", int),
        distance_km=num("distance_km", float) if kind == "run" else None,
        notes=f.get("notes", "").strip() or None,
    )
    flash("Workout logged! Your coach can see it now.", "success")
    return redirect(url_for("main.workouts"))


@bp.route("/workouts/add-sets", methods=["POST"])
@login_required
def add_workout_sets():
    """Log a strength workout with structured exercise / set / rep rows.

    The form posts parallel arrays: exercise[], reps[], weight[]. Each filled
    row becomes an exercise_sets record, numbered per exercise.
    """
    f = request.form
    title = f.get("title", "").strip()
    workout_date = f.get("workout_date", "").strip() or date.today().isoformat()
    if not title:
        flash("Give your workout a title.", "error")
        return redirect(url_for("main.workouts"))

    exercises = f.getlist("exercise")
    reps_list = f.getlist("reps")
    weight_list = f.getlist("weight")

    def to_num(raw, cast):
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            return cast(raw)
        except ValueError:
            return None

    sets = []
    per_exercise_count = {}
    for i, ex in enumerate(exercises):
        ex = (ex or "").strip()
        if not ex:
            continue
        per_exercise_count[ex] = per_exercise_count.get(ex, 0) + 1
        sets.append(
            {
                "exercise": ex,
                "set_no": per_exercise_count[ex],
                "reps": to_num(reps_list[i] if i < len(reps_list) else "", int),
                "weight_kg": to_num(weight_list[i] if i < len(weight_list) else "", float),
            }
        )

    if not sets:
        flash("Add at least one exercise set.", "error")
        return redirect(url_for("main.workouts"))

    dur = f.get("duration_min", "").strip()
    db.add_workout_with_sets(
        member_id=session["member_id"],
        title=title,
        workout_date=workout_date,
        duration_min=int(dur) if dur.isdigit() else None,
        notes=f.get("notes", "").strip() or None,
        sets=sets,
    )
    flash(f"Logged {len(sets)} set(s). Your coach can see it now.", "success")
    return redirect(url_for("main.workouts"))


# ---- Virtual Training Library --------------------------------------------

@bp.route("/library")
@login_required
def library():
    member_id = session["member_id"]
    subscribed = db.has_active_library_sub(member_id)
    if not subscribed:
        # Show the paywall instead of the content.
        return render_template(
            "library_locked.html",
            price=db.LIBRARY_SUB_PRICE,
            member=db.get_member(member_id),
        )

    items = db.list_library_items()
    videos = [i for i in items if i["kind"] == "video"]
    plans = [i for i in items if i["kind"] == "workout"]
    return render_template(
        "library.html",
        videos=videos,
        plans=plans,
        member=db.get_member(member_id),
    )


@bp.route("/library/<int:item_id>")
@login_required
def library_item(item_id):
    if not db.has_active_library_sub(session["member_id"]):
        return redirect(url_for("main.library"))
    item = db.get_library_item(item_id)
    if item is None:
        flash("Item not found.", "error")
        return redirect(url_for("main.library"))
    return render_template("library_item.html", item=item)


@bp.route("/library/subscribe", methods=["POST"])
@login_required
def library_subscribe():
    # DUMMY payment — would go through Revolut Pay like the plan checkout.
    until = db.start_library_sub(session["member_id"])
    flash(f"Training Library unlocked — subscription active until {until.strftime('%d %b %Y')}.", "success")
    return redirect(url_for("main.library"))


@bp.route("/library/cancel", methods=["POST"])
@login_required
def library_cancel():
    db.cancel_library_sub(session["member_id"])
    flash("Training Library subscription cancelled.", "success")
    return redirect(url_for("main.library"))


# ---- 1-to-1 (personal training) booking ----------------------------------

@bp.route("/pt")
@login_required
def pt():
    member_id = session["member_id"]
    return render_template(
        "pt.html",
        coaches=db.list_coaches(),
        sessions=db.list_pt_sessions(member_id),
        today=date.today().isoformat(),
    )


@bp.route("/pt/book", methods=["POST"])
@login_required
def pt_book():
    f = request.form
    coach_id = f.get("coach_id")
    slot_date = f.get("slot_date", "").strip()
    slot_hour = f.get("slot_hour", "").strip()
    if not (coach_id and slot_date and slot_hour):
        flash("Pick a coach, date and time.", "error")
        return redirect(url_for("main.pt"))
    slot_time = f"{slot_date} {slot_hour}"
    _, msg = db.book_pt_session(session["member_id"], int(coach_id), slot_time)
    flash(msg, "success")
    return redirect(url_for("main.pt"))



# ---- Anonymous feedback --------------------------------------------------

@bp.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        rating = request.form.get("rating", "").strip()
        if not body:
            flash("Please write some feedback first.", "error")
        else:
            db.add_feedback(body, int(rating) if rating.isdigit() else None)
            # No member id is stored — reassure the user.
            flash("Thanks! Your feedback was submitted anonymously.", "success")
        return redirect(url_for("main.feedback"))

    return render_template("feedback.html")


# ---- AI workout Q&A (member) ---------------------------------------------

@bp.route("/coach-ai", methods=["GET", "POST"])
@login_required
def coach_ai():
    member_id = session["member_id"]
    answer = None
    question = ""
    used_context = False
    consent = db.has_ai_consent(member_id)

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            # Only attach personal context if the member has opted in.
            context = db.member_ai_context(member_id) if consent else None
            used_context = context is not None
            answer, _ = ai.ask_workout_question(question, context=context)

    return render_template(
        "coach_ai.html",
        answer=answer,
        question=question,
        ai_enabled=ai.ai_enabled(),
        consent=consent,
        used_context=used_context,
    )


@bp.route("/coach-ai/ask", methods=["POST"])
@login_required
def coach_ai_ask():
    """JSON endpoint for the chat UI so it can show a 'thinking' loader.

    Returns the answer rendered to HTML plus whether personal context was used.
    """
    member_id = session["member_id"]
    question = (request.form.get("question") or "").strip()
    if not question:
        return jsonify({"error": "empty"}), 400

    consent = db.has_ai_consent(member_id)
    context = db.member_ai_context(member_id) if consent else None
    answer, used_ai = ai.ask_workout_question(question, context=context)

    # Render markdown to HTML with the same filter the templates use.
    html = current_app.jinja_env.filters["markdown"](answer)
    return jsonify(
        {
            "answer_html": str(html),
            "used_context": context is not None,
            "used_ai": used_ai,
        }
    )


@bp.route("/ai-consent", methods=["POST"])
@login_required
def ai_consent():
    # Toggle the GDPR opt-in for sharing aggregate activity with the AI.
    on = request.form.get("consent") == "on"
    db.set_ai_consent(session["member_id"], on)
    flash(
        "AI personalization enabled — only anonymous activity totals are shared."
        if on else "AI personalization turned off. No activity data is shared.",
        "success",
    )
    return redirect(url_for("main.coach_ai"))


# ---- Privacy & GDPR ------------------------------------------------------

@bp.route("/privacy")
@login_required
def privacy():
    return render_template("privacy.html", ai_enabled=ai.ai_enabled())


@bp.route("/privacy/erase", methods=["POST"])
@login_required
def privacy_erase():
    # GDPR right to erasure. Confirm with a typed word to avoid accidents.
    if request.form.get("confirm", "").strip().upper() != "DELETE":
        flash("Type DELETE to confirm erasure.", "error")
        return redirect(url_for("main.privacy"))
    db.erase_member_data(session["member_id"])
    session.clear()
    flash("Your data has been permanently erased.", "success")
    return redirect(url_for("auth.login"))



# ---- Health metrics (sleep, steps, calories, HR) -------------------------

@bp.route("/health")
@login_required
def health():
    member_id = session["member_id"]
    member = db.get_member(member_id)
    today = db.today_health(member_id)
    recent = db.recent_health(member_id, days=7)

    # Build a simple 7-day steps sparkline (oldest -> newest).
    spark = list(reversed([(r["steps"] or 0) for r in recent]))
    spark_max = max(spark) if spark else 1

    return render_template(
        "health.html",
        member=member,
        today=today,
        recent=recent,
        spark=spark,
        spark_max=spark_max or 1,
        today_date=date.today().isoformat(),
    )


@bp.route("/health/connect", methods=["POST"])
@login_required
def health_connect():
    source = request.form.get("source", "")
    if source not in ("apple", "google"):
        flash("Unknown source.", "error")
        return redirect(url_for("main.health"))
    db.simulate_sync(session["member_id"], source, days=7)
    label = "Apple Health" if source == "apple" else "Google Fit"
    flash(f"Connected to {label} — last 7 days synced (demo data).", "success")
    return redirect(url_for("main.health"))


@bp.route("/health/log", methods=["POST"])
@login_required
def health_log():
    f = request.form

    def num(name, cast):
        raw = (f.get(name) or "").strip()
        if not raw:
            return None
        try:
            return cast(raw)
        except ValueError:
            return None

    db.upsert_health_metric(
        session["member_id"],
        metric_date=date.today().isoformat(),
        steps=num("steps", int),
        sleep_hours=num("sleep_hours", float),
        calories=num("calories", int),
        resting_hr=num("resting_hr", int),
        source="manual",
    )
    flash("Today's metrics saved.", "success")
    return redirect(url_for("main.health"))
