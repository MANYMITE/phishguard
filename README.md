# PhishGuard 🛡️

**A consent-based phishing-awareness training platform.** Run realistic phishing
simulations for people who have agreed to be tested — and never store their
credentials, ever.

Inspired by [GoPhish](https://github.com/gophish/gophish) (not affiliated).
PhishGuard exists because credential-harvesting toolkits like BlackEye ship
the same mechanics with none of the guardrails. PhishGuard keeps the training
value and hard-codes the ethics into the source.

---

## The three safety invariants

These are enforced in code and covered by automated tests:

1. **Credentials are never stored.** The submission handler never reads the
   password field. Form values are discarded the moment Flask parses the
   request. A test posts a canary password and then scans the raw SQLite file
   bytes to prove it was never written anywhere.
2. **The database layer refuses credential-shaped data.** Any attempt to log
   an event with a field like `password`, `passwd`, `pwd`, `pin`, `otp`,
   `secret` or `token` raises an error instead of persisting.
3. **Consent is required at every step.** Campaigns and participants cannot be
   created without an explicit consent confirmation, and simulation pages
   display an honest banner: *this is a training exercise, nothing you type
   is saved.*

## Quickstart

```bash
git clone https://github.com/<you>/phishguard.git
cd phishguard
./install.sh          # any distro: apt, dnf, pacman, zypper
. .venv/bin/activate
python run.py
```

Open <http://127.0.0.1:5000>:

1. **New campaign** — name it, pick a template, tick the consent box.
2. **Add participants** — the people who agreed to the drill (name + email).
3. Copy each participant's simulation link and deliver it however you like
   (email, chat). V1 is deliberately manual: *you* are the sending engine.
4. Watch clicks and submissions appear on the campaign dashboard — then walk
   each person through their personal "caught" page, which turns the moment
   into a lesson instead of a breach.

## Run the safety tests

```bash
python -m unittest discover -s tests -v
```

## Architecture

```
phishguard/
├── run.py                  # entry point (python run.py)
├── install.sh              # cross-distro dependency installer
├── requirements.txt        # Flask. That's it.
└── phishguard/
    ├── __init__.py         # create_app() application factory
    ├── db.py               # SQLite schema + helpers
    ├── safety.py           # field sanitiser + storage-level guard
    ├── admin.py            # dashboard, campaigns, participants
    ├── sim.py              # simulation landing / submit / caught pages
    ├── templates/          # admin UI + simulation templates
    └── static/
```

- **Stack:** Python 3 + Flask + stdlib `sqlite3`. No ORM, no build step,
  no Docker required — runs on any Linux, macOS, WSL or Windows.
- **Simulation templates** are plain Jinja pages registered in
  `phishguard/sim.py::TEMPLATES`. The bundled `acme_webmail` template is a
  realistic-but-generic portal login. Fork it to match your org's real SSO
  look (never copy a real brand's logo without permission).
- **Events** are the only thing recorded: `clicked` and `submitted`, with
  metadata limited to user agent and timestamp.

## Roadmap

- [ ] CSV participant import
- [ ] Consent-based SMTP sending (the GoPhish-style sending engine)
- [ ] More simulation templates (HR memo, invoice, shared doc)
- [ ] Per-participant completion certificates
- [ ] Programmatic reporting export (JSON/CSV)
- [ ] Optional admin authentication for shared deployments

## Legal & ethical use

PhishGuard is for **authorised awareness training only**: simulations sent to
people in your organisation who have consented, on systems you own. Using
this — or any tool — to phish real credentials from unconsenting people is
illegal in most jurisdictions. The code above is designed to make misuse
structurally difficult; please don't try to undo that.

## License

MIT — see [LICENSE](LICENSE).
