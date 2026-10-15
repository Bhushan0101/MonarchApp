"""Authentication: login, logout, and a login_required guard."""

from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from . import db

bp = Blueprint("auth", __name__)


def login_required(view):
    """Redirect to the login page if there is no logged-in member."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("member_id") is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("member_id"):
        return redirect(url_for("main.membership"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        member = db.get_member_by_username(username)

        if member and check_password_hash(member["password_hash"], password):
            session.clear()
            session["member_id"] = member["id"]
            return redirect(url_for("main.membership"))

        flash("Incorrect username or password.", "error")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# ---- Social login (demo / simulated) -------------------------------------
#
# A real Google/Apple sign-in needs OAuth app registration, client secrets,
# HTTPS redirect URIs, and (for Apple) a paid developer account — none of
# which run in a local-only prototype. These routes SIMULATE the result of a
# successful social sign-in: they create or reuse a member keyed by a demo
# email, then log them in. Swap the body for a real OAuth callback later; the
# rest of the app is already provider-agnostic (see members.auth_provider).

_DEMO_SOCIAL = {
    "google": {"email": "demo.google@gmail.com", "name": "Google Demo User"},
    "apple": {"email": "demo.apple@icloud.com", "name": "Apple Demo User"},
}


@bp.route("/auth/<provider>")
def social_login(provider):
    info = _DEMO_SOCIAL.get(provider)
    if info is None:
        flash("Unknown sign-in provider.", "error")
        return redirect(url_for("auth.login"))

    member_id = db.get_or_create_social_member(
        provider, info["email"], info["name"]
    )
    session.clear()
    session["member_id"] = member_id
    flash(f"Signed in with {provider.title()} (demo).", "success")
    return redirect(url_for("main.membership"))
