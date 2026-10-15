# Monarch Fight Academy — app prototype

A local, mobile-first prototype: membership, class booking, events, workout
tracking (sets/reps + timer), a €10/mo Virtual Training Library, 1-to-1
booking, anonymous feedback, and AI features (member coach + admin assistant).

---

## Run it (test setup)

**1. Install dependencies** (one time):
```bash
.venv/bin/pip install -r requirements.txt
```

**2. Add your AI key** (optional but recommended):
```bash
cp .env.example .env
```
Open `.env` and paste your free Groq key:
```
GROQ_API_KEY=gsk_your_key_here
```
> Get a free key at https://console.groq.com → **API Keys** → Create.
> `.env` is git-ignored — your key is never committed.

**3. Start the app:**
```bash
.venv/bin/python main.py
```

The startup banner shows everything you need:
```
On this computer : http://127.0.0.1:5000
On your phone     : http://<your-ip>:5000   (same Wi-Fi)
AI features       : ON ✓
Member login      : sarah / mike / ava   (password: monarch)
Admin panel       : http://127.0.0.1:5000/admin   (password: admin123)
```

---

## Test logins

| Who    | Username / password      | Notes                          |
|--------|--------------------------|--------------------------------|
| Member | `sarah` / `monarch`      | Active membership              |
| Member | `mike`  / `monarch`      | Expiring soon                  |
| Member | `ava`   / `monarch`      | Expired                        |
| Admin  | password `admin123`      | at `/admin`                    |

You can also use the **Continue with Google / Apple** buttons (demo accounts).

---

## What to test

**Member app** (log in at `/`):
- Membership card, buy/renew a plan (dummy Revolut Pay)
- Book a class; log a workout (Quick, or Sets & Reps with the timer)
- Virtual Training Library (subscribe → videos & plans)
- Book a 1-to-1 session
- Ask the **AI Coach** (toggle "personalize" on to use your activity)
- Give **anonymous feedback**; view **Privacy & my data** (incl. delete)

**Admin panel** (`/admin`, password `admin123`):
- **AI business assistant** — conversational briefing + stats
- View member workouts; manage library content & 1-to-1 requests
- **Feedback & word cloud** with AI summary
- Add members, events; set payment reminders

---

## Notes
- Data persists in `monarch.db` (git-ignored). Delete it to reset to demo data.
- Without `GROQ_API_KEY`, AI features show non-AI fallbacks — the app still works.
- Prototype-grade security (demo passwords, dummy payments). Not for production.

---

## Deploy to Render (so others can see it online)

The app is production-ready: `gunicorn main:app`, `$PORT`, env-based secret key,
`DB_PATH` for a persistent disk, and a `render.yaml` blueprint.

### Steps
1. **Rotate your Groq key** at console.groq.com (the old one was shared in chat). Do NOT commit `.env`.
2. Push this project to a **GitHub repo** (`.gitignore` already excludes `.env` and `monarch.db`).
3. On **render.com**: *New → Blueprint* → pick your repo. Render reads `render.yaml`.
4. In the Render dashboard, set the secret env vars it asks for:
   - `GROQ_API_KEY` = your new key
   - `MONARCH_ADMIN_PASSWORD` = a password you choose (not the default)
5. Deploy. You get a public URL like `https://monarch-fight-academy.onrender.com` to share.

### Free-plan note
`render.yaml` includes a **persistent disk** (keeps the database) — that needs a **paid**
plan. For the **free** plan: delete the `disk:` block and the `DB_PATH` env var in
`render.yaml` before deploying. The app then uses an ephemeral DB that resets on each
redeploy/restart (fine for a demo), and the free instance **sleeps after ~15 min idle**
(first visit wakes it in ~30s).

### Security before sharing
Demo logins (`sarah`/`monarch`, admin `admin123`) and dummy payments are fine for a friend
demo, but change the admin password and don't put real personal data in a public instance.
