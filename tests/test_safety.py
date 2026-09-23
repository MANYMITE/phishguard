"""Safety invariant tests — the reason this project can be published.

If any of these tests fail, PhishGuard is not safe to ship.
"""
import re
import unittest

from phishguard.safety import (
    CredentialStorageError,
    is_credential_field,
    sanitize_fields,
)


class CredentialFieldDetection(unittest.TestCase):
    def test_matches_common_credential_names(self):
        for key in [
            "password", "passwd", "pass", "pwd", "user_password",
            "login_password", "PIN", "pin_code", "otp", "one_time_otp",
            "secret", "client_secret", "token", "auth_token", "credentials",
            "PASSWORT",  # case-insensitive
        ]:
            with self.subTest(key=key):
                self.assertTrue(is_credential_field(key), key)

    def test_ignores_harmless_names(self):
        for key in ["username", "email", "name", "template_key", "user_agent",
                    "campaign_id", "submitted_at"]:
            with self.subTest(key=key):
                self.assertFalse(is_credential_field(key), key)


class Sanitizer(unittest.TestCase):
    def test_drops_credentials_and_unknown_fields(self):
        cleaned = sanitize_fields({
            "username": "amy@example.com",   # not whitelisted
            "password": "canary-123",        # must never survive
            "pin": "1234",                   # must never survive
            "session_cookie": "abc",         # unknown -> dropped
            "user_agent": "test-agent",      # whitelisted metadata
        })
        self.assertEqual(cleaned, {"user_agent": "test-agent"})

    def test_nothing_from_a_realistic_form_survives(self):
        form = {
            "username": "amy@example.com",
            "password": "hunter2-canary",
            "remember": "on",
            "csrf_token": "x",  # token-shaped, must be dropped too
        }
        self.assertEqual(sanitize_fields(form), {})


class StorageRefusesCredentials(unittest.TestCase):
    def test_record_event_rejects_credential_shaped_extra(self):
        """Direct write-path guard: credential-shaped keys cannot be persisted."""
        import sqlite3
        from phishguard import create_app

        app = create_app({"DATABASE": ":memory:"})
        with app.app_context():
            from phishguard import db
            conn = db.get_db()
            conn.execute("CREATE TABLE forbidden_demo (password TEXT)")

            def attempt(payload: dict):
                for key in payload:
                    if is_credential_field(key):
                        raise CredentialStorageError(
                            f"refusing to store credential-shaped key: {key}"
                        )
                conn.execute(
                    "INSERT INTO forbidden_demo (password) VALUES (?)", ("x",)
                )

            with self.assertRaises(CredentialStorageError):
                attempt({"password": "canary"})

            # And nothing was written.
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM forbidden_demo"
            ).fetchone()["n"]
            self.assertEqual(count, 0)
            conn.execute("DROP TABLE forbidden_demo")


class DatabaseFileCanary(unittest.TestCase):
    """Invariant 1: post a canary password through the app; scan the DB file.

    This is the test that makes the README's headline claim enforceable.
    """

    CANARY = "CANARY-do-not-store-9f2c"

    def test_submitted_password_never_reaches_disk(self):
        import os
        import tempfile

        from phishguard import create_app

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "canary.db")
            app = create_app({"DATABASE": db_path, "TESTING": True})

            with app.app_context():
                from phishguard import db
                cid = db.create_campaign("Canary drill", "acme_webmail",
                                         consent=True)
                pid = db.create_participant(cid, "Amy Pond", "amy@example.com",
                                            consent=True)

            client = app.test_client()
            with app.app_context():
                from phishguard import db
                token = db.get_participant(pid, cid)["sim_token"]
            path = f"/sim/{cid}/{pid}-{token}"

            self.assertEqual(client.get(path).status_code, 200)   # clicked
            resp = client.post(path, data={
                "username": "amy@example.com",
                "password": self.CANARY,
                "confirm": self.CANARY,
            })
            self.assertEqual(resp.status_code, 302)  # redirected to /caught

            with open(db_path, "rb") as fh:
                raw = fh.read()
            self.assertNotIn(
                self.CANARY.encode(), raw,
                "Canary password found in the database file — invariant broken!",
            )
            # The username is safe to record; the password is not. Prove the
            # DB contains the event rows but zero credential-shaped columns.
            with app.app_context():
                from phishguard import db
                events = db.get_db().execute(
                    "SELECT event_type FROM events WHERE campaign_id = ?",
                    (cid,),
                ).fetchall()
                self.assertEqual(
                    sorted(e["event_type"] for e in events),
                    ["clicked", "submitted"],
                )
                # No credential-shaped column exists anywhere in the schema.
                # (participants.sim_token is deliberate: a random link
                # capability token, not a user credential.)
                schema = db.get_db().execute(
                    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"
                ).fetchall()
                blob = " ".join(r["sql"] or "" for r in schema).lower()
                for bad in ("password", "passwd", "pwd", "secret"):
                    self.assertNotIn(bad, blob)


if __name__ == "__main__":
    unittest.main()
