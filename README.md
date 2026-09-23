# PhishGuard 🛡️

[![tests](https://github.com/MANYMITE/phishguard/actions/workflows/tests.yml/badge.svg)](https://github.com/MANYMITE/phishguard/actions/workflows/tests.yml)
[![website](https://img.shields.io/badge/site-manymite.github.io%2Fphishguard-39ff5a)](https://manymite.github.io/phishguard/)

**A consent-based phishing-awareness training platform.** Run realistic phishing
simulations for people who agreed to be trained — and never store their
credentials, ever.

🌐 **Website:** https://manymite.github.io/phishguard/
🚀 **Live demo:** https://phishguard-xxen.onrender.com

---

## What it does

1. **You (the trainer) create a campaign** and pick one of the **10 fictional
   portals** — Acme Webmail, Meridian Bank, CorpNet VPN, CloudVault Drive,
   PayHub Payroll, IT HelpDesk, MedCare Portal, JetStream Rewards, SwiftParcel,
   Learnly e-Learning.
2. **Add consenting participants** — consent is mandatory and enforced at
   three layers (form, route, database).
3. **Each participant gets a personal, unguessable link.** Deliver it to them
   however you agreed.
4. **They click, maybe "sign in"** — and land on a friendly teaching page
   explaining what just happened. Only `clicked` / `submitted` events are
   recorded. **The database has no column that could hold a password** — the
   test suite posts a canary credential and byte-scans the DB file to prove it.
5. **Watch the stats** — open rate, submit rate, activity log — and coach
   instead of punish.

Two ways to drive it: the **web dashboard**, or the **hacker-console terminal
UI** (`python phishguard-cli.py`) with a numbered menu and template grid.

---

## Quick start (Linux / macOS / WSL)

```bash
git clone https://github.com/MANYMITE/phishguard.git
cd phishguard
./install.sh                      # creates .venv + installs Flask
. .venv/bin/activate
export PHISHGUARD_SECRET_KEY="pick-a-long-random-string"   # = admin password
python run.py                     # → http://127.0.0.1:5000
```

Windows: double-click **`start.bat`** (after `git clone` + `install.sh`).
The terminal UI: `python phishguard-cli.py`.

## Running tests

```bash
python -m unittest discover -s tests        # 50 tests
bash scripts/verify.sh                      # 13 live end-to-end checks
```

## Hosting

- **Render (free, one click):** [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/MANYMITE/phishguard) — the generated `PHISHGUARD_SECRET_KEY` is your admin password (Render → Environment). Free tier sleeps after ~15 min idle; SQLite resets on redeploy.
- **Share on any network:** `bash scripts/share.sh` — auto-picks a tunnel (Cloudflare → Pinggy → ngrok → localtunnel), or `bash scripts/share.sh lan` for Wi-Fi-only.

---

## Safety & ethical use

PhishGuard is for **authorised awareness training only**: simulations sent to
people in your organisation who have consented, on systems you own.

- **It cannot work as a credential harvester.** The submission handler never
  reads the password field and the database has nowhere to put one — enforced
  by 50 automated tests.
- **Every simulation page shows an honest banner** — "training exercise,
  nothing you type is saved" — and submitters get an education page, not a
  harvest.
- **All portals are fictional** (clones of nothing) — realistic mechanics, no
  trademark cloning.
- Phishing real credentials from unconsenting people is **illegal** in most
  jurisdictions. Don't.

## Project structure (basics)

```
phishguard/
├── run.py               # start the web app
├── phishguard-cli.py    # start the terminal UI
├── wsgi.py + render.yaml# production hosting (Render/gunicorn)
├── install.sh           # one-command setup
├── start.bat            # Windows launcher
├── phishguard/          # the app (factory, db, admin, sim, cli, safety)
├── templates/           # web UI + the themed portal template
├── tests/               # 50 tests incl. canary-never-stored
├── scripts/             # verify.sh (self-test), share.sh (tunnels)
└── docs/                # the website (GitHub Pages)
```

## License

MIT — see [LICENSE](LICENSE).
