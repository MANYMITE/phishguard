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
- 🖥️ **Clean admin UI** — stats cards, one-click link copying, friendly
  error pages
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

## Running tests

```bash
python -m unittest discover -s tests -v
```

Three suites: `test_safety` (credential-storage invariants), `test_flows`
(consent gates, simulation lifecycle, stats), `test_security` (auth, CSRF,
link tokens, validation, rate limiting, headers).

## Project structure

```
phishguard/
├── run.py                  # entry point (python run.py)
├── install.sh              # cross-distro dependency installer
├── requirements.txt        # Flask. That's it.
├── phishguard/
│   ├── __init__.py         # app factory, security headers, error handlers
│   ├── db.py               # SQLite schema + queries + audit trail
│   ├── safety.py           # credential-field guard + input validators
│   ├── admin.py            # auth, CSRF, dashboard, campaigns, participants
│   ├── sim.py              # tokenized simulation/submit/caught routes
│   ├── templates/          # admin UI + simulation templates
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
- [ ] More simulation templates (HR memo, invoice, shared doc)
- [ ] Per-participant completion certificates
- [ ] JSON/CSV report export
- [ ] Multi-admin accounts with proper password hashing

## License

MIT — see [LICENSE](LICENSE).
