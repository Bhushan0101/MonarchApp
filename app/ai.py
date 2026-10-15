"""Lightweight AI helper for the Monarch prototype.

Uses Groq's FREE API tier (OpenAI-compatible chat endpoint) running an open
Llama model. No paid service and no SDK dependency — just urllib.

Set a free key to enable it:
    export GROQ_API_KEY="gsk_..."      # from https://console.groq.com (free)

If no key is set, both features degrade gracefully:
  - summarize_feedback() falls back to a simple keyword-based summary
  - ask_workout_question() returns a message explaining how to enable it

Swap MODEL / endpoint here to use any other OpenAI-compatible free provider.
"""

import json
import os
import ssl
import urllib.error
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Free, fast open model on Groq. Override with GROQ_MODEL if this is retired;
# list current ones at GET https://api.groq.com/openai/v1/models.
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")


def _ssl_context():
    """TLS context using certifi's CA bundle.

    Python on macOS often can't find system CA certs, which breaks HTTPS to
    external APIs. Prefer certifi; fall back to the default context.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL_CTX = _ssl_context()


def ai_enabled():
    return bool(os.environ.get("GROQ_API_KEY"))


def _chat(system, user, max_tokens=400, temperature=0.4):
    """Call the free Groq chat endpoint. Returns text, or None on failure."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None

    payload = json.dumps(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode()

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Groq sits behind Cloudflare, which blocks the default
            # "Python-urllib" agent (HTTP 403 / error 1010). Use a normal UA.
            "User-Agent": "Monarch-Gym-App/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError):
        return None


# ---- Admin: summarize anonymous feedback ---------------------------------

def summarize_feedback(feedback_texts):
    """Summarize members' anonymous feedback for the admin.

    Returns (summary_text, used_ai: bool).
    """
    if not feedback_texts:
        return "No feedback yet.", False

    joined = "\n".join(f"- {t}" for t in feedback_texts[:150])
    out = _chat(
        system=(
            "You are an assistant for a fight-gym owner. Summarize anonymous "
            "member feedback into a short, honest briefing: 3-5 bullet points "
            "covering the main themes, praise, and complaints. Be concise and "
            "neutral. Do not invent details."
        ),
        user=f"Member feedback:\n{joined}\n\nSummary:",
        max_tokens=350,
    )
    if out:
        return out, True

    # Fallback: naive extractive summary (no AI key / call failed).
    return _fallback_summary(feedback_texts), False


def _fallback_summary(feedback_texts):
    """Keyword-based summary when AI is unavailable."""
    from .db import _STOPWORDS
    import re
    from collections import Counter

    counter = Counter()
    for t in feedback_texts:
        for w in re.findall(r"[a-zA-Z']{3,}", (t or "").lower()):
            if w not in _STOPWORDS:
                counter[w] += 1
    top = ", ".join(w for w, _ in counter.most_common(8)) or "n/a"
    return (
        f"(Keyword summary — set GROQ_API_KEY for a full AI summary.)\n"
        f"{len(feedback_texts)} pieces of feedback. "
        f"Most mentioned: {top}."
    )


# ---- Member: general workout Q&A -----------------------------------------

def ask_workout_question(question, context=None):
    """Answer a training question for a member.

    `context` is an OPTIONAL dict of aggregate, non-identifying stats (classes
    booked, workout counts, etc.) — passed ONLY when the member has given
    consent. It never contains name, email, or raw logs.

    Returns (answer_text, used_ai: bool).
    """
    system = (
        "You are a friendly coach at Monarch Fight Academy (K1 kickboxing "
        "and Brazilian Jiu-Jitsu, plus strength training). Answer general "
        "workout, technique, nutrition, and recovery questions clearly and "
        "safely. Keep answers short and practical. If a question needs a "
        "doctor or in-person coaching, say so. Do not give medical advice."
    )
    if context:
        # Only aggregate numbers — no identity. Tell the model to personalize.
        stats = "; ".join(f"{k}={v}" for k, v in context.items())
        system += (
            "\n\nThe member has consented to share their anonymous activity "
            "summary so you can personalize advice. Use it where relevant, but "
            "never ask for or reveal personal identity. Their stats: " + stats
        )

    out = _chat(system=system, user=question, max_tokens=450, temperature=0.6)
    if out:
        return out, True

    return (
        "The AI coach isn't configured yet. To enable it, get a free API key "
        "from console.groq.com and set GROQ_API_KEY before starting the app. "
        "In the meantime, ask one of our coaches on the Coaches tab!"
    ), False


# ---- Admin: business assistant -------------------------------------------

def admin_business_chat(question, stats):
    """Conversational business assistant for admins.

    `stats` is a dict of aggregate business metrics (counts and totals only —
    no member names or emails). Returns (answer_text, used_ai: bool).
    """
    stats_text = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in stats.items())
    system = (
        "You are a concise operations assistant for the owner of Monarch Fight "
        "Academy, a combat-sports gym. You are given aggregate business metrics "
        "(no personal data about individuals). Answer the owner's question "
        "conversationally and suggest concrete next actions (e.g. who to remind, "
        "what to follow up). Base everything strictly on the numbers given; do "
        "not invent specifics or name individuals."
    )
    user = f"Current business metrics:\n{stats_text}\n\nQuestion: {question}"
    out = _chat(system=system, user=user, max_tokens=500, temperature=0.5)
    if out:
        return out, True

    # Fallback: a plain rule-based briefing when AI isn't configured.
    lines = [
        "(Set GROQ_API_KEY for a conversational AI briefing. Here are the raw numbers.)",
        f"Total members: {stats.get('total_members', 0)} "
        f"({stats.get('active_members', 0)} active, "
        f"{stats.get('expired_or_unpaid', 0)} expired/unpaid).",
    ]
    if stats.get("expiring_within_7d"):
        lines.append(f"⚠️ {stats['expiring_within_7d']} membership(s) expire within 7 days — send renewal reminders.")
    if stats.get("expired_or_unpaid"):
        lines.append(f"⚠️ {stats['expired_or_unpaid']} member(s) expired/unpaid — follow up on payment.")
    if stats.get("pending_pt_requests"):
        lines.append(f"📋 {stats['pending_pt_requests']} 1-to-1 request(s) awaiting confirmation.")
    lines.append(f"Revenue to date: €{stats.get('total_revenue_eur', 0)}.")
    return "\n".join(lines), False

