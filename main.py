"""Monarch — local gym membership mobile prototype.

Run with:  python main.py
Then open the printed URL on this computer, or the LAN URL on your phone
(same Wi-Fi network).
"""

import os
import socket
import subprocess


def _load_dotenv():
    """Load KEY=VALUE lines from a .env file into the environment.

    Tiny, dependency-free loader so testers can just paste their GROQ_API_KEY
    into a .env file instead of exporting it each time. Existing environment
    variables win (so `GROQ_API_KEY=... python main.py` still overrides .env).
    """
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()

from app import create_app          # noqa: E402  (import after .env load)
from app.ai import ai_enabled       # noqa: E402


def _lan_ip():
    """Best-effort local Wi-Fi/LAN IP so you can open the app on a phone.

    Prefers a real physical interface (en0 = Wi-Fi on most Macs). This avoids
    picking a VPN tunnel address (utunN / 10.x), which a phone on the same
    Wi-Fi cannot reach.
    """
    # 1) Try the physical interfaces directly (macOS: en0 is Wi-Fi, en1 wired).
    for iface in ("en0", "en1"):
        try:
            ip = subprocess.run(
                ["ipconfig", "getifaddr", iface],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip()
            if ip:
                return ip
        except (OSError, subprocess.SubprocessError):
            pass

    # 2) Fallback: ask the OS which source IP it would use for an outbound
    #    connection (works cross-platform, but can pick a VPN interface).
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no packets actually sent
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


app = create_app()

if __name__ == "__main__":
    # Local dev server. In production (Render) Gunicorn imports `app` directly
    # and this block does not run — see the Procfile.
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    ip = _lan_ip()
    ai_status = "ON ✓" if ai_enabled() else "OFF (add GROQ_API_KEY to .env to enable)"
    print("\n  👑 Monarch is running!")
    print(f"     On this computer : http://127.0.0.1:{port}")
    print(f"     On your phone     : http://{ip}:{port}   (same Wi-Fi)")
    print("     If the phone can't connect, allow Python through the macOS")
    print("     firewall (System Settings → Network → Firewall), or turn off")
    print("     any VPN on this Mac.\n")
    print(f"  AI features : {ai_status}")
    print("  Member login: sarah / mike / ava   (password: monarch)")
    print(f"  Admin panel : http://127.0.0.1:{port}/admin   (password: admin123)\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
