"""Security hardening tests: auth, CSRF, link tokens, validation, headers."""
import os
import tempfile
import unittest

from phishguard import create_app
from phishguard.safety import (
    ValidationError,
    validate_campaign_name,
    validate_email,
    validate_participant_name,
)

ADMIN_PASSWORD = "dev-only-change-me"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({
            "DATABASE": os.path.join(self.tmp.name, "test.db"),
            "TESTING": True,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self):
        return self.client.post("/login", data={"password": ADMIN_PASSWORD},
                                follow_redirects=True)


class AdminAuth(Base):
    def test_dashboard_redirects_anonymous(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_login_success_and_failure(self):
        bad = self.client.post("/login", data={"password": "wrong"})
        self.assertIn(b"Wrong admin password", bad.data)
        good = self.client.post("/login", data={"password": ADMIN_PASSWORD})
        self.assertEqual(good.status_code, 302)  # redirected to dashboard
        self.assertIn("/", good.headers["Location"])

    def test_wrong_password_cannot_create_campaign(self):
        self.client.post("/login", data={"password": "nope"})
        # Not logged in -> POST is redirected to login, nothing created.
        resp = self.client.post("/campaigns", data={
            "name": "Sneaky", "template_key": "acme_webmail", "consent": "yes",
        })
        self.assertEqual(resp.status_code, 302)
        with self.app.app_context():
            from phishguard import db
            self.assertEqual(len(db.list_campaigns()), 0)


class CSRFProtection(Base):
    def setUp(self):
        super().setUp()
        self.app.config["FORCE_CSRF"] = True  # re-enable the real behaviour
        self.client = self.app.test_client()

    def test_post_without_token_is_rejected(self):
        self.login()
        resp = self.client.post("/campaigns", data={
            "name": "CSRF drill", "template_key": "acme_webmail",
            "consent": "yes",
        })
        self.assertEqual(resp.status_code, 302)  # bounced with a flash
        with self.app.app_context():
            from phishguard import db
            self.assertEqual(len(db.list_campaigns()), 0)

    def test_post_with_token_succeeds(self):
        # Mirror a real browser: mint a token, log in (CSRF-protected too),
        # then use the FRESH token minted by the login's session rotation.
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testtoken123"
        self.client.post("/login", data={
            "password": ADMIN_PASSWORD, "csrf_token": "testtoken123",
        })
        with self.client.session_transaction() as sess:
            fresh = sess["_csrf_token"]
        self.assertIsNotNone(fresh)
        resp = self.client.post("/campaigns", data={
            "name": "CSRF drill", "template_key": "acme_webmail",
            "consent": "yes", "csrf_token": fresh,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            from phishguard import db
            self.assertEqual(len(db.list_campaigns()), 1)

    def test_simulation_posts_are_exempt(self):
        """Participants must be able to submit from an emailed link."""
        with self.app.app_context():
            from phishguard import db
            cid = db.create_campaign("C", "acme_webmail", consent=True)
            pid = db.create_participant(cid, "A", "a@x.com", consent=True)
            token = db.get_participant(pid, cid)["sim_token"]
        resp = self.client.post(f"/sim/{cid}/{pid}-{token}",
                                data={"username": "a@x.com",
                                      "password": "x"})
        self.assertEqual(resp.status_code, 302)


class LinkTokens(Base):
    def test_old_style_links_are_gone(self):
        with self.app.app_context():
            from phishguard import db
            cid = db.create_campaign("C", "acme_webmail", consent=True)
            pid = db.create_participant(cid, "A", "a@x.com", consent=True)
            token = db.get_participant(pid, cid)["sim_token"]
        # Correct token works...
        self.assertEqual(
            self.client.get(f"/sim/{cid}/{pid}-{token}").status_code, 200)
        # ...wrong token and missing token look like missing pages.
        self.assertEqual(
            self.client.get(f"/sim/{cid}/{pid}-WRONGTOKEN").status_code, 404)
        self.assertEqual(self.client.get(f"/sim/{cid}/{pid}").status_code, 404)

    def test_tokens_are_unique_and_long(self):
        with self.app.app_context():
            from phishguard import db
            cid = db.create_campaign("C", "acme_webmail", consent=True)
            t1 = db.create_participant(cid, "A", "a@x.com", consent=True)
            t2 = db.create_participant(cid, "B", "b@x.com", consent=True)
            p1 = db.get_participant(t1, cid)
            p2 = db.get_participant(t2, cid)
            self.assertNotEqual(p1["sim_token"], p2["sim_token"])
            self.assertGreaterEqual(len(p1["sim_token"]), 32)


class InputValidation(Base):
    def test_campaign_name_rules(self):
        self.assertEqual(validate_campaign_name("  Q3   drill "), "Q3 drill")
        with self.assertRaises(ValidationError):
            validate_campaign_name("ab")
        self.assertEqual(len(validate_campaign_name("x" * 500)), 80)

    def test_participant_name_rules(self):
        with self.assertRaises(ValidationError):
            validate_participant_name("A")

    def test_email_rules(self):
        self.assertEqual(validate_email("AMY@Example.com "),
                         "amy@example.com")
        for bad in ("nope", "a@b", "a b@c.com", "", None):
            with self.subTest(email=bad):
                with self.assertRaises(ValidationError):
                    validate_email(bad)

    def test_admin_rejects_bad_participant(self):
        self.login()
        with self.app.app_context():
            from phishguard import db
            cid = db.create_campaign("C", "acme_webmail", consent=True)
        resp = self.client.post(f"/campaigns/{cid}/participants", data={
            "name": "Zed", "email": "not-an-email", "consent": "yes",
        }, follow_redirects=True)
        self.assertIn(b"valid email", resp.data)

    def test_duplicate_participant_is_friendly_error(self):
        self.login()
        with self.app.app_context():
            from phishguard import db
            cid = db.create_campaign("C", "acme_webmail", consent=True)
            db.create_participant(cid, "Amy", "amy@example.com", consent=True)
        resp = self.client.post(f"/campaigns/{cid}/participants", data={
            "name": "Amy 2", "email": "amy@example.com", "consent": "yes",
        }, follow_redirects=True)
        self.assertIn(b"already a participant", resp.data)


class RateLimit(Base):
    def test_login_rate_limited_after_five_failures(self):
        for _ in range(5):
            self.client.post("/login", data={"password": "wrong"})
        resp = self.client.post("/login", data={"password": "wrong"})
        self.assertEqual(resp.status_code, 429)
        self.assertIn(b"Too many attempts", resp.data)

    def test_correct_password_after_failures_still_limited(self):
        for _ in range(5):
            self.client.post("/login", data={"password": "wrong"})
        resp = self.client.post("/login", data={"password": ADMIN_PASSWORD})
        self.assertEqual(resp.status_code, 429)


class SecurityHeaders(Base):
    def test_headers_present(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp.headers["X-Frame-Options"], "DENY")
        self.assertEqual(resp.headers["Referrer-Policy"], "no-referrer")
        self.assertIn("default-src 'self'", resp.headers["Content-Security-Policy"])

    def test_404_is_friendly(self):
        resp = self.client.get("/definitely-not-a-page")
        self.assertEqual(resp.status_code, 404)
        self.assertIn(b"404", resp.data)
        self.assertIn(b"Back to the dashboard", resp.data)

    def test_oversized_form_is_rejected(self):
        self.login()
        resp = self.client.post("/campaigns",
                                data={"name": "x" * 100000,
                                      "template_key": "acme_webmail",
                                      "consent": "yes"})
        self.assertEqual(resp.status_code, 413)


class TunnelProxySupport(Base):
    """Behind a tunnel/reverse proxy, links must carry the public host."""

    PROXY_HEADERS = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "demo-drill.trycloudflare.com",
    }

    def _app_with_proxy(self):
        self.tmp2 = tempfile.TemporaryDirectory()
        app = create_app({
            "DATABASE": os.path.join(self.tmp2.name, "p.db"),
            "TESTING": True,
            "BEHIND_PROXY": True,
        })
        self.addCleanup(self.tmp2.cleanup)
        return app

    def test_proxy_mode_wraps_wsgi_and_secures_cookies(self):
        app = self._app_with_proxy()
        from werkzeug.middleware.proxy_fix import ProxyFix
        self.assertIsInstance(app.wsgi_app, ProxyFix)
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])

    def test_default_mode_ignores_forwarded_headers(self):
        # No BEHIND_PROXY: forwarded headers must NOT be trusted.
        from werkzeug.middleware.proxy_fix import ProxyFix
        self.assertNotIsInstance(self.app.wsgi_app, ProxyFix)

    def test_participant_links_use_public_tunnel_host(self):
        app = self._app_with_proxy()
        client = app.test_client()
        client.post("/login", data={"password": ADMIN_PASSWORD},
                    headers=self.PROXY_HEADERS)
        with app.app_context():
            from phishguard import db
            cid = db.create_campaign("Tunnel drill", "acme_webmail",
                                     consent=True)
            pid = db.create_participant(cid, "A", "a@x.com", consent=True)
            token = db.get_participant(pid, cid)["sim_token"]
        resp = client.get(f"/campaigns/{cid}", headers=self.PROXY_HEADERS)
        self.assertIn(
            f"https://demo-drill.trycloudflare.com/sim/{cid}/{pid}-{token}"
            .encode(), resp.data)


class TemplateIntegrity(Base):
    def test_templates_contain_honest_banner(self):
        import phishguard.sim as sim
        for key, tpl in sim.TEMPLATES.items():
            path = os.path.join(os.path.dirname(sim.__file__),
                                "templates", tpl["file"])
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("Training exercise", text, key)


if __name__ == "__main__":
    unittest.main()
