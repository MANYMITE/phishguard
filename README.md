# PhishGuard 🛡️

**A consent-based phishing-awareness training platform.** Run realistic phishing
simulations for people who have agreed to be tested — and never store their
credentials, ever.

Inspired by [GoPhish](https://github.com/gophish/gophish) (not affiliated).
PhishGuard exists because credential-harvesting toolkits ship the same mechanics
with none of the guardrails. PhishGuard keeps the training value and hard-codes
the ethics into the source — and its test suite.

## What PhishGuard does

1. **Trainer creates a campaign** (e.g. "Q4 finance-team drill") and picks a
   simulation template — a realistic-but-generic login page.
2. **Trainer adds consenting participants** by name and email. Every creation
   path demands an explicit consent confirmation, twice (route + database).
3. **Each participant gets a personal, unguessable link** containing a random
   token. Wrong or missing tokens look exactly like missing pages — links
   can't be enumerated.
4. **The trainer delivers the link** as agreed (email, chat). V1 delivery is
   deliberately manual: *you* are the sending engine.
5. **If the participant "falls" for the drill**, they land on a friendly
   *you were caught* teaching page. The platform records only `clicked` /
   `submitted` events — never what was typed.
6. **The dashboard shows the numbers** — open rate, submit rate, activity log —
   so the trainer can coach instead of punish.

## Features

- 🧪 **Zero-credential storage, enforced by tests** — a canary password is
  posted through the real app and the SQLite file is byte-scanned to prove it
  never touched disk
- 🧱 **Storage-level guard** — the data layer refuses credential-shaped
  fields (`password`, `pin`, `otp`, `secret`, `token`, …) with an error
- ✅ **Consent gates everywhere** — campaigns and participants require an
  explicit confirmation checkbox, re-validated in the database layer
- 🔗 **Tokenized simulation links** — random per-participant tokens,
  enumeration-proof
- 🔐 **Admin authentication** with rate-limited login and CSRF protection on
  every admin form
- 🛡️ **Security headers** — CSP, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy: no-referrer`; request size limits
- 📝 **Audit trail** — logins, campaign and participant actions to `audit.log`
- 🖥️ **Two ways to drive it** — a clean web admin UI, or a **hacker-console
terminal UI** (`python phishguard-cli.py`): ASCII banner, numbered menu,
ANSI colors, and a BlackEye-style template grid with a quick
*pick → consent → link* flow
- 🎭 **Template catalog of 10 fictional portals** — webmail, VPN, banking,
file drive, payroll, helpdesk, health, airline, parcel, e-learning — all
rendered from one themed template, all clone-of-nothing, all carrying the
honest banner
- 🌍 **Works on any network** — one command (`scripts/share.sh`) publishes a
  HTTPS tunnel via Cloudflare (no account), ngrok, or localtunnel; participant
  links automatically use the public host. LAN mode included.
- 🐘 **Boring stack** — Python 3 + Flask + stdlib SQLite. No ORM, no build
  step, no Docker. Runs on any Linux distro, macOS, WSL or Windows.

## Installation

```bash
git clone https://github.com/MANYMITE/phishguard.git
cd phishguard
./install.sh          # any distro: apt, dnf, pacman, zypper
. .venv/bin/activate
```

Or by hand:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running locally

```bash
export PHISHGUARD_SECRET_KEY="a-long-random-string"   # REQUIRED — doubles as the admin password
python run.py
```

Open <http://127.0.0.1:5000>, sign in with your secret key, and run your first
drill. `PORT=8000 python run.py` changes the port; the server binds to
`127.0.0.1` only.

> **Before letting anyone else use the server:** set a real
> `PHISHGUARD_SECRET_KEY` (it is both the session secret and the admin
> password), run behind a proper WSGI server + reverse proxy with TLS, and
> keep admin access internal.

## Sharing beyond localhost (any network)

The server binds to `127.0.0.1` by design — participants on other devices
need a tunnel (or LAN) to reach it. One command does everything:

```bash
bash scripts/share.sh              # auto-pick: cloudflare → ngrok → localtunnel
bash scripts/share.sh cloudflare   # Cloudflare quick tunnel — no account needed
bash scripts/share.sh ngrok        # ngrok (set NGROK_AUTHTOKEN once)
bash scripts/share.sh localtunnel  # localtunnel via npx
bash scripts/share.sh lan          # LAN only: http://<your-ip>:5000
```

The script starts PhishGuard, brings up the tunnel, and prints the public
HTTPS URL. Create participant links in the admin panel as usual — they
automatically carry the public host (`PHISHGUARD_BEHIND_PROXY=1` is set for
you, which also enables `ProxyFix` and secure cookies).

Notes:
- **Cloudflare quick tunnels** (`trycloudflare.com`) need no account and give
  a random URL each run — ideal for a one-hour drill.
- On restrictive networks that block QUIC/UDP (symptom: Cloudflare error
  **1033** in the browser), force TCP with:
  `TUNNEL_PROTOCOL=http2 bash scripts/share.sh cloudflare`.
- **ngrok** free accounts get stable URLs; configure `NGROK_AUTHTOKEN`.
- **localtunnel** shows visitors a one-time password page (your public IP).
- The admin panel becomes **public** in tunnel mode. Use a strong secret key
  and press Ctrl+C to tear the tunnel down when the drill is over.
- Behind your own reverse proxy instead? Set `PHISHGUARD_BEHIND_PROXY=1` and
  forward `X-Forwarded-Proto/Host`.

## Hosting on Render (free, one click)

The repo ships a Render blueprint (`render.yaml`) and a WSGI entry point
(`wsgi.py`). Easiest path — sign in to [render.com](https://render.com) with
your GitHub account, then:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/MANYMITE/phishguard)

Render clones the repo, installs requirements, and serves the app with
gunicorn on a public HTTPS URL like `https://phishguard-xxxx.onrender.com`.
The **admin password** is the generated `PHISHGUARD_SECRET_KEY` — read/change
it under your service → **Environment**.

Notes for the free tier: the service sleeps after ~15 idle minutes (first
visit takes ~30s to wake), and the SQLite database resets on redeploy — fine
for demos and short drills; for a persistent deployment attach a Render disk
or run on a VPS. Because it's public HTTPS, tunnel mode is unnecessary: the
admin panel and participant links work from any network as-is.

## Running tests

```bash
python -m unittest discover -s tests -v
```

Four suites: `test_safety` (credential-storage invariants), `test_flows`
(consent gates, simulation lifecycle, stats, every-catalog-template E2E),
`test_security` (auth, CSRF, link tokens, validation, rate limiting,
headers), `test_cli` (terminal UI parsing, consent gate, catalog registry).

## The terminal UI

```bash
python phishguard-cli.py        # after . .venv/bin/activate
```

```
┌─[ PhishGuard ]─[ main menu ]
   [01] Quick drill (pick → link)   [06] Campaign stats+links
   [02] New campaign                [07] Open web panel
   [03] Add participant             [08] Start / stop local server
   [04] List campaigns              [09] Share on the network (tunnel)
   [05] Template catalog            [10] Run safety verification
   [00] Exit
```

Option [01] is the BlackEye-style flow: pick a portal from the numbered
catalog grid, confirm consent, and you get the participant's personal link.
All portals are fictional (Acme Webmail, Meridian Bank, CorpNet VPN, …) —
that is a deliberate safety line: realistic mechanics, no trademark cloning,
nothing that could harvest real credentials.

## Project structure

```
phishguard/
├── run.py                  # entry point (python run.py)
├── phishguard-cli.py       # terminal UI entry (python phishguard-cli.py)
├── install.sh              # cross-distro dependency installer
├── scripts/
│   ├── verify.sh           # one-command end-to-end verification
│   └── share.sh            # tunnel launcher (cloudflare/ngrok/localtunnel/LAN)
├── requirements.txt        # Flask. That's it.
├── phishguard/
│   ├── __init__.py         # app factory, security headers, error handlers
│   ├── db.py               # SQLite schema + queries + audit trail
│   ├── safety.py           # credential-field guard + input validators
│   ├── admin.py            # auth, CSRF, dashboard, campaigns, participants
│   ├── sim.py              # template catalog + tokenized simulation routes
│   ├── cli.py              # hacker-console terminal UI
│   ├── templates/          # admin UI + sim_portal.html (all templates)
│   └── static/
└── tests/
    ├── test_safety.py      # canary-password, schema, sanitizer tests
    ├── test_flows.py       # consent gates, lifecycle, stats
    └── test_security.py    # auth, CSRF, tokens, validation, headers
```

## Security & ethical-use notes

PhishGuard is for **authorised awareness training only**: simulations sent to
people in your organisation who have consented, on systems you own.

- **It cannot be used as a credential harvester.** The submission handler
  never reads the password field, the database has no column that could hold
  one, and the test suite fails if that ever changes.
- **Simulation pages always show an honest banner** — "training exercise,
  nothing you type is saved" — and the education page afterwards explains
  what happened and why it matters.
- **Deliver links only to people who agreed** to take part. Using this — or
  any tool — to phish real credentials from unconsenting people is illegal in
  most jurisdictions.
- **Privacy by design**: stored data is limited to names, work emails the
  trainer already has, event counts and a hashed user agent. Delete the
  SQLite file when the exercise is over and everything is gone.

## Roadmap

- [ ] CSV participant import
- [ ] Consent-logged SMTP sending (the GoPhish-style sending engine)
- [ ] More catalog portals (HR memo, invoice, shared doc) — one themed file,
      so adding a portal is one CATALOG entry
- [ ] Per-participant completion certificates
- [ ] JSON/CSV report export
- [ ] Multi-admin accounts with proper password hashing

## License

MIT — see [LICENSE](LICENSE).
