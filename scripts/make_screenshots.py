"""Regenerate the website screenshots in docs/screenshots/.

Renders real pages through Flask's test client with seeded demo data,
inlines the stylesheet, then photographs each HTML file with headless
Edge/Chrome. Safe to re-run; uses a throwaway database only.

    python scripts/make_screenshots.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from phishguard import create_app  # noqa: E402
from phishguard import db  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "screenshots")

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/microsoft-edge", "/usr/bin/google-chrome", "/usr/bin/chromium",
]

SHOTS = [
    ("login", "01-login"),
    ("dashboard", "02-dashboard"),
    ("campaign", "03-campaign"),
    ("sim", "04-sim-page"),
    ("caught", "05-caught-page"),
]


def find_browser():
    for path in EDGE_CANDIDATES:
        if os.path.exists(path):
            return path
    return shutil.which("msedge") or shutil.which("google-chrome") or shutil.which("chromium")


def seed_demo(app):
    """Realistic demo dataset in the throwaway DB."""
    with app.app_context():
        cid = db.create_campaign("Q4 Finance drill", "acme_webmail", consent=True)
        people = [("Amy Chen", "amy@example.com", True, True),
                  ("Rory Patel", "rory@example.com", True, False),
                  ("Sam Okafor", "sam@example.com", False, False)]
        first_token = None
        for name, email, clicked, submitted in people:
            pid = db.create_participant(cid, name, email, consent=True)
            if first_token is None:
                first_token = db.get_participant(pid, cid)["sim_token"]
            if clicked:
                db.record_event(pid, cid, "clicked")
            if submitted:
                db.record_event(pid, cid, "submitted")
        cid2 = db.create_campaign("IT onboarding batch", "corpnet_vpn", consent=True)
        pid2 = db.create_participant(cid2, "Dana Fox", "dana@example.com", consent=True)
        db.record_event(pid2, cid2, "clicked")
        return cid, first_token, cid2


def get_csrf(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else ""


def inline_css(html):
    css_path = os.path.join(ROOT, "phishguard", "static", "style.css")
    if not os.path.exists(css_path):
        return html
    with open(css_path, encoding="utf-8") as fh:
        css = fh.read()
    static_url = "file:///" + os.path.join(ROOT, "phishguard", "static").replace("\\", "/") + "/"
    html = html.replace('href="/static/style.css"', "href='__CSS__'")
    html = re.sub(r"<link[^>]*href='__CSS__'[^>]*>",
                  "<style>" + css.replace("\\", "\\\\") + "</style>", html)
    return html.replace(static_url, "") if False else html


def shoot(browser, html_path, png_path, width=1280, height=860):
    # Unique profile dir per shot: a shared one makes Edge forward the command
    # to the user's running instance, and back-to-back launches race on the
    # profile lock (the detached previous process may still hold it).
    profile = os.path.join(tempfile.gettempdir(),
                           "pg-edge-" + os.path.basename(png_path))
    subprocess.run([
        browser, "--headless=new", "--disable-gpu", "--no-first-run",
        f"--user-data-dir={profile}",
        f"--screenshot={png_path}", f"--window-size={width},{height}",
        "file:///" + html_path.replace("\\", "/"),
    ], capture_output=True, timeout=60)
    # Windows Chromium quirk: the launcher detaches and returns rc=0 while the
    # real browser process writes the PNG asynchronously. Poll for it.
    if os.path.exists(png_path):
        return
    for _ in range(40):
        time.sleep(0.5)
        if os.path.exists(png_path):
            return


def main():
    browser = find_browser()
    if not browser:
        print("No headless-capable browser found; screenshots skipped.")
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="pg-shots-")
    app = create_app({"DATABASE": os.path.join(tmp, "shots.db"), "TESTING": False})
    cid, token, cid2 = seed_demo(app)
    client = app.test_client()

    # -- login page -------------------------------------------------------
    login_html = client.get("/login").data.decode("utf-8")
    csrf = get_csrf(login_html)

    pages = {"login": login_html}

    # -- authed pages -----------------------------------------------------
    resp = client.post("/login", data={"password": "dev-only-change-me",
                                       "csrf_token": csrf},
                       follow_redirects=True)
    pages["dashboard"] = resp.data.decode("utf-8")

    pages["campaign"] = client.get(f"/campaigns/{cid}").data.decode("utf-8")

    # -- participant-facing pages ------------------------------------------
    with app.app_context():
        sim_url = f"/sim/{cid}/1-{token}"
    pages["sim"] = client.get(sim_url).data.decode("utf-8")
    sub = client.post(sim_url, data={"username": "amy@example.com",
                                     "password": "never-stored"})
    pages["caught"] = client.get(sub.headers["Location"]).data.decode("utf-8")

    # -- write + shoot ------------------------------------------------------
    ok = 0
    for key, fname in SHOTS:
        html_path = os.path.join(tmp, f"{fname}.html")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(inline_css(pages[key]))
        png_path = os.path.join(OUT_DIR, f"{fname}.png")
        shoot(browser, html_path, png_path)
        if os.path.exists(png_path) and os.path.getsize(png_path) > 5000:
            ok += 1
            print(f"  [ok] {fname}.png")
        else:
            print(f"  [MISS] {fname}.png")

    print(f"{ok}/{len(SHOTS)} screenshots written to docs/screenshots/")
    return 0 if ok == len(SHOTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
