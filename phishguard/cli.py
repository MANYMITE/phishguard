"""PhishGuard terminal UI — the hacker-console control panel.

A BlackEye-style interface (numbered menu, ANSI colors) driving PhishGuard's
legitimate features: campaigns, participants, personal links, the local
server, tunnels and the safety verification. Deliberately does NOT offer
brand-clone templates; every path keeps the consent gates.
"""
import os
import subprocess
import sys
import webbrowser

from . import create_app, db
from .safety import ValidationError, validate_campaign_name, validate_email, validate_participant_name

BASE_URL = os.environ.get("PHISHGUARD_BASE_URL", "http://127.0.0.1:5000")
PID_FILE = ".pg-server.pid"

# ---------------------------------------------------------------- colors ---
def _ansi_enabled():
    if os.name == "nt":
        # Piped/non-console stdout defaults to cp1252 and would crash on
        # box-drawing characters; force UTF-8 with graceful degradation.
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        os.system("")  # enables VT processing in most Windows terminals
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetConsoleMode(k32.GetStdHandle(-11), 7)
        except Exception:
            pass

GREEN, RED, YELLOW, CYAN, DIM, RESET = (
    "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[2m", "\033[0m")

def ok(msg):   print(f"{GREEN}[✓]{RESET} {msg}")
def warn(msg): print(f"{RED}[!]{RESET} {YELLOW}{msg}{RESET}")
def info(msg): print(f"{CYAN}[i]{RESET} {msg}")

BANNER = f"""{GREEN}
  ____  _   _ ____   ____ _   _    _
 |  _ \\| | | |  _ \\ / ___| | | |  / \\
 | |_) | | | | |_) | |   | |_| | / _ \\
 |  __/| |_| |  __/| |___|  _  |/ ___ \\
 |_|    \\___/|_|    \\____|_| |_/_/   \\_\\{RESET}
{DIM}        consent-based awareness training{RESET}
"""

MENU = f"""
{GREEN}┌─[ PhishGuard ]─[ main menu ]
└──────────►{RESET} {DIM}(type a number — leading zeros welcome){RESET}

   {GREEN}[01]{RESET} Quick drill (pick → link)   {GREEN}[06]{RESET} Campaign stats+links
   {GREEN}[02]{RESET} New campaign                {GREEN}[07]{RESET} Open web panel
   {GREEN}[03]{RESET} Add participant             {GREEN}[08]{RESET} Start / stop local server
   {GREEN}[04]{RESET} List campaigns              {GREEN}[09]{RESET} Share on the network (tunnel)
   {GREEN}[05]{RESET} Template catalog            {GREEN}[10]{RESET} Run safety verification
   {RED}[00]{RESET} Exit
"""

# ------------------------------------------------------------- app context --
_app = create_app({"TESTING": False})


def with_db(fn):
    def wrapper(*a, **kw):
        with _app.app_context():
            return fn(*a, **kw)
    return wrapper


# ---------------------------------------------------------------- helpers ---
def parse_choice(raw: str, limit: int) -> int | None:
    """Accepts '01', '1', ' 2 ' — returns int or None (BlackEye-style)."""
    raw = (raw or "").strip()
    if not raw.isdigit():
        return None
    n = int(raw)
    return n if 0 <= n <= limit else None


def build_link(cid: int, pid: int, token: str) -> str:
    return f"{BASE_URL}/sim/{cid}/{pid}-{token}"


def ask(prompt: str, validator=None):
    raw = input(f"{GREEN}└─►{RESET} {prompt}").strip()
    if validator is not None:
        try:
            return validator(raw)
        except ValidationError as exc:
            warn(str(exc))
            return None
    return raw


def ask_consent(what: str) -> bool:
    ans = input(f"{GREEN}└─►{RESET} Consent: has {what} explicitly agreed to "
                f"this authorised exercise? {YELLOW}(yes/no){RESET} ").strip().lower()
    if ans == "yes":
        return True
    warn("Refusing to continue without explicit consent.")
    return False


def print_template_grid() -> list[str]:
    """BlackEye-style multi-column catalog. Returns keys in display order."""
    from .sim import CATALOG
    keys = [entry["key"] for entry in CATALOG]
    cols = 3
    rows = (len(keys) + cols - 1) // cols
    print(f"\n  {GREEN}Available simulation portals{RESET} {DIM}"
          f"(fictional portals — clones of nothing){RESET}\n")
    for r in range(rows):
        cells = []
        for c in range(cols):
            i = r + c * rows
            if i < len(keys):
                entry = CATALOG[i]
                cells.append(f"   {GREEN}[{i + 1:02d}]{RESET} "
                             f"{entry['icon']} {entry['title']:<22}")
            else:
                cells.append(" " * 30)
        print("".join(cells))
    print()
    return keys


def pick_template() -> str | None:
    keys = print_template_grid()
    raw = input(f"{GREEN}└─►{RESET} Template number: ").strip()
    n = parse_choice(raw, len(keys))
    if not n:
        warn("Invalid template choice.")
        return None
    return keys[n - 1]


def action_show_catalog():
    """Print the template catalog, BlackEye-style."""
    from .sim import CATALOG
    keys = print_template_grid()
    for i, entry in enumerate(CATALOG, 1):
        print(f"   {GREEN}[{i:02d}]{RESET} {entry['title']:<22} "
              f"{DIM}{entry['description']}{RESET}")
    info(f"{len(keys)} portals available. Pick one when creating a campaign.")


@with_db
def action_quick_drill():
    """BlackEye-speed flow: pick a portal -> consent -> link. That's it."""
    from .sim import CATALOG, TEMPLATES
    keys = print_template_grid()
    raw = input(f"{GREEN}└─►{RESET} Choose a portal: ").strip()
    n = parse_choice(raw, len(keys))
    if not n:
        warn("Invalid choice.")
        return
    entry = CATALOG[n - 1]
    name = ask("Campaign name (Enter = auto): ") or (
        f"Quick drill — {entry['title']}")
    try:
        name = validate_campaign_name(name)
    except ValidationError as exc:
        warn(str(exc))
        return
    if not ask_consent("every participant you will add"):
        return
    cid = db.create_campaign(name, entry["key"], consent=True)
    ok(f"Campaign #{cid} '{name}' created on {entry['title']}.")
    # Immediately offer adding the first participant (the usual next step).
    ans = input(f"{GREEN}└─►{RESET} Add the first participant now? "
                f"{YELLOW}(yes/no){RESET} ").strip().lower()
    if ans != "yes":
        info(f"Add participants later via menu [03] — campaign ID is {cid}.")
        return
    pname = ask("Participant name: ", validate_participant_name)
    if not pname:
        return
    pemail = ask("Participant email: ", validate_email)
    if not pemail:
        return
    if not ask_consent(pname):
        return
    try:
        pid = db.create_participant(cid, pname, pemail, consent=True)
    except ValidationError as exc:
        warn(str(exc))
        return
    p = db.get_participant(pid, cid)
    ok("Done. Personal, unguessable link — send it as agreed:")
    print(f"\n  {CYAN}{build_link(cid, pid, p['sim_token'])}{RESET}\n")


def server_running() -> bool:
    r = subprocess.run(["curl", "-s", "--max-time", "2", f"{BASE_URL}/health"],
                       capture_output=True, text=True)
    return "phishguard" in (r.stdout or "")


# ------------------------------------------------------------------ actions -
@with_db
def action_new_campaign():
    name = ask("Campaign name: ", validate_campaign_name)
    if not name:
        return
    key = pick_template()
    if not key:
        return
    if not ask_consent("every participant you will add"):
        return
    cid = db.create_campaign(name, key, consent=True)
    ok(f"Campaign #{cid} '{name}' created — add participants next.")


@with_db
def action_list_campaigns():
    rows = db.list_campaigns()
    if not rows:
        info("No campaigns yet — create one first.")
        return
    print(f"\n  {'ID':<4}{'NAME':<28}{'TEMPLATE':<16}{'PEOPLE':<8}"
          f"{'OPENED':<8}{'SUBMITTED':<10}")
    for c in rows:
        s = db.campaign_stats(c["id"])
        print(f"  {c['id']:<4}{c['name'][:26]:<28}{c['template_key']:<16}"
              f"{s['participants']:<8}{s['clicks']:<8}{s['submissions']:<10}")


@with_db
def action_add_participant():
    if not db.list_campaigns():
        info("Create a campaign first.")
        return
    try:
        cid = int(ask("Campaign ID: ", lambda v: int(v)))
    except (ValueError, TypeError):
        warn("Invalid campaign ID.")
        return
    if not db.get_campaign(cid):
        warn("No such campaign.")
        return
    name = ask("Participant name: ", validate_participant_name)
    if not name:
        return
    email = ask("Participant email: ", validate_email)
    if not email:
        return
    if not ask_consent(name):
        return
    try:
        pid = db.create_participant(cid, name, email, consent=True)
    except ValidationError as exc:
        warn(str(exc))
        return
    p = db.get_participant(pid, cid)
    ok("Participant added. Personal, unguessable link:")
    print(f"\n  {CYAN}{build_link(cid, pid, p['sim_token'])}{RESET}\n")
    info("Deliver it yourself, as agreed with the participant.")


@with_db
def action_campaign_details():
    try:
        cid = int(ask("Campaign ID: ", lambda v: int(v)))
    except (ValueError, TypeError):
        warn("Invalid campaign ID.")
        return
    c = db.get_campaign(cid)
    if not c:
        warn("No such campaign.")
        return
    s = db.campaign_stats(cid)
    print(f"\n  {GREEN}{c['name']}{RESET} {DIM}({c['template_key']}) — "
          f"consent: yes{RESET}")
    print(f"  participants={s['participants']}  opened={s['clicks']} "
          f"({s['click_rate']}%)  submitted={s['submissions']} ({s['submit_rate']}%)  "
          f"{GREEN}passwords stored: 0{RESET}")
    parts = db.list_participants(cid)
    if parts:
        print(f"\n  {'ID':<5}{'NAME':<22}{'LINK'}")
        for p in parts:
            print(f"  {p['id']:<5}{p['name'][:20]:<22}"
                  f"{CYAN}{build_link(cid, p['id'], p['sim_token'])}{RESET}")
    events = db.participant_events(cid)[:8]
    if events:
        print(f"\n  {DIM}recent activity:{RESET}")
        for e in events:
            print(f"   {DIM}{e['created_at']}{RESET}  {e['name']:<18} {e['event_type']}")


def action_open_panel():
    url = f"{BASE_URL}/login"
    info(f"Opening {url}")
    webbrowser.open(url)


def action_toggle_server():
    if server_running():
        warn("Server is already running.")
        ans = input(f"{GREEN}└─►{RESET} Stop it? {YELLOW}(yes/no){RESET} ").strip().lower()
        if ans == "yes":
            try:
                pid = int(open(PID_FILE).read().strip())
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True)
                else:
                    subprocess.run(["kill", str(pid)], capture_output=True)
                os.remove(PID_FILE)
                ok("Server stopped.")
            except Exception:
                warn("Could not stop (was it started outside this CLI?).")
        return
    env = dict(os.environ,
               PHISHGUARD_SECRET_KEY=os.environ.get("PHISHGUARD_SECRET_KEY", ""),
               PHISHGUARD_HOST="127.0.0.1", PORT=os.environ.get("PORT", "5000"))
    if not env["PHISHGUARD_SECRET_KEY"]:
        warn("Set PHISHGUARD_SECRET_KEY first (it is the admin password).")
        return
    log = open(".pg-server.log", "w")
    proc = subprocess.Popen([sys.executable, "run.py"], env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    open(PID_FILE, "w").write(str(proc.pid))
    import time
    for _ in range(30):
        time.sleep(0.5)
        if server_running():
            break
    ok(f"Server started (pid {proc.pid}) — panel: {BASE_URL}/login")
    info("Log: .pg-server.log")


def action_share():
    print(f"\n  {GREEN}[1]{RESET} lan          {DIM}http://<your-ip>:5000{RESET}")
    print(f"  {GREEN}[2]{RESET} cloudflare   {DIM}trycloudflare.com (no account){RESET}")
    print(f"  {GREEN}[3]{RESET} pinggy       {DIM}SSH over 443 (no account){RESET}")
    print(f"  {GREEN}[4]{RESET} ngrok        {DIM}needs authtoken{RESET}")
    print(f"  {GREEN}[5]{RESET} localtunnel  {DIM}loca.lt{RESET}")
    raw = input(f"{GREEN}└─►{RESET} Method: ").strip()
    modes = {"1": "lan", "2": "cloudflare", "3": "pinggy", "4": "ngrok",
             "5": "localtunnel"}
    mode = modes.get(parse_choice(raw, 5) and str(parse_choice(raw, 5)), "")
    if not mode:
        warn("Invalid method.")
        return
    script = "share.bat" if os.name == "nt" and os.path.exists("scripts/share.bat") \
        else "scripts/share.sh"
    info(f"Launching {mode} — Ctrl+C returns to the menu when done.")
    subprocess.run(["bash", script, mode] if script.endswith(".sh")
                   else ["bash", script, mode])


def action_verify():
    info("Running the full test suite + live end-to-end verification...")
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    if r.returncode == 0 and os.path.exists("scripts/verify.sh"):
        subprocess.run(["bash", "scripts/verify.sh"])


ACTIONS = {
    1: action_quick_drill, 2: action_new_campaign,
    3: action_add_participant, 4: action_list_campaigns,
    5: action_show_catalog, 6: action_campaign_details,
    7: action_open_panel, 8: action_toggle_server,
    9: action_share, 10: action_verify,
}


def main() -> None:
    _ansi_enabled()
    while True:
        print(BANNER)
        print(MENU)
        raw = input(f"{GREEN}┌─[ Choose an option: ]─[~]\n└──────────►{RESET} ")
        n = parse_choice(raw, 10)
        if n == 0:
            ok("Stay sharp out there. Goodbye.")
            return
        action = ACTIONS.get(n)
        if action is None:
            warn("Invalid option — pick 0-10.")
            continue
        try:
            action()
        except KeyboardInterrupt:
            print()
        input(f"{DIM}press Enter for the menu...{RESET}")


if __name__ == "__main__":
    main()
