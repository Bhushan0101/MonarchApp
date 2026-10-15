"""Flask application factory for the Monarch gym prototype."""

import os

from flask import Flask
from markupsafe import Markup

# Templates and static assets live at the project root, one level up from
# this app package.
_ROOT = os.path.dirname(os.path.dirname(__file__))


def _render_markdown(text):
    """Render AI/Markdown text to safe HTML (bold, lists, tables).

    Output is sanitized by bleach-style allow-listing: python-markdown only
    emits a known set of tags, and we strip raw HTML in the source so a model
    response can't inject scripts.
    """
    if not text:
        return ""
    import re
    import markdown as _md

    text = str(text)
    # Models often emit a list with no blank line before the first item, e.g.
    #   Key points:
    #   - a
    # python-markdown needs a blank line there to start a <ul>. Insert one.
    text = re.sub(r"(?m)^(?P<prev>[^\s\-*|].*\S)\n(?=[-*] )", r"\g<prev>\n\n", text)

    html = _md.markdown(
        text,
        extensions=["tables", "sane_lists"],
        output_format="html5",
    )
    return Markup(html)


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
        static_folder=os.path.join(_ROOT, "static"),
    )
    # Secret key: from the environment in production; a dev fallback locally.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "monarch-dev-secret-change-me")
    # Shared admin-panel password (demo). Override via env for anything real.
    app.config["ADMIN_PASSWORD"] = os.environ.get("MONARCH_ADMIN_PASSWORD", "admin123")

    # Jinja filter so templates can do {{ answer | markdown }}.
    app.jinja_env.filters["markdown"] = _render_markdown

    from .auth import bp as auth_bp
    from .routes import bp as main_bp
    from .admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    # Create tables / seed demo data on startup. Safe to call every boot
    # (idempotent) — this also runs under Gunicorn on Render, not just locally.
    from .db import init_db
    init_db()

    return app
