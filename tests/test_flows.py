"""End-to-end flow tests: consent gates, dashboard, simulation lifecycle."""
import os
import tempfile
import unittest

from phishguard import create_app

ADMIN_PASSWORD = "dev-only-change-me"  # default dev secret doubles as password


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

    # -- helpers ----------------------------------------------------------
    def login(self):
        return self.client.post("/login",
                                data={"password": ADMIN_PASSWORD},
                                follow_redirects=True)

    def make_campaign_and_participant(self, email="amy@example.com",
                                      name="Amy"):
        with self.app.app_context():
            from phishguard import db
            cid = db.create_campaign("Drill", "acme_webmail", consent=True)
            pid = db.create_participant(cid, name, email, consent=True)
        return cid, pid

    def sim_path(self, cid, pid, token=None):
        """Tokenized path for a participant (token fetched from DB by default)."""
        with self.app.app_context():
            from phishguard import db
            if token is None:
                token = db.get_participant(pid, cid)["sim_token"]
        return f"/sim/{cid}/{pid}-{token}"


class ConsentGates(Base):
    def test_campaign_requires_consent(self):
        self.login()
        resp = self.client.post("/campaigns", data={
            "name": "No-consent campaign",
            "template_key": "acme_webmail",
            # no consent checkbox
        }, follow_redirects=True)
        self.assertIn(b"Consent is required", resp.data)
        with self.app.app_context():
            from phishguard import db
            self.assertEqual(len(db.list_campaigns()), 0)

    def test_campaign_with_consent_is_created(self):
        self.login()
        resp = self.client.post("/campaigns", data={
            "name": "Q1 drill",
            "template_key": "acme_webmail",
            "consent": "yes",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            from phishguard import db
            campaigns = db.list_campaigns()
            self.assertEqual(len(campaigns), 1)
            self.assertEqual(campaigns[0]["consent_confirmed"], 1)

    def test_participant_requires_consent(self):
        self.login()
        cid, _ = self.make_campaign_and_participant()
        resp = self.client.post(f"/campaigns/{cid}/participants", data={
            "name": "Rory", "email": "rory@example.com",  # no consent
        }, follow_redirects=True)
        self.assertIn(b"consented", resp.data)
        with self.app.app_context():
            from phishguard import db
            emails = [p["email"] for p in db.list_participants(cid)]
        self.assertNotIn("rory@example.com", emails)  # nothing was added

    def test_db_layer_refuses_unconsented_creation(self):
        """The DB layer is the second line of defence — test it directly."""
        with self.app.app_context():
            from phishguard import db
            with self.assertRaises(ValueError):
                db.create_campaign("Sneaky", "acme_webmail", consent=False)
            with self.assertRaises(ValueError):
                db.create_participant(1, "X", "x@x.com", consent=False)


class SimulationLifecycle(Base):
    def test_landing_clicks_and_submit_redirects_to_caught(self):
        cid, pid = self.make_campaign_and_participant()
        path = self.sim_path(cid, pid)
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Acme Webmail", resp.data)
        self.assertIn(b"Training exercise", resp.data)  # honest banner

        resp = self.client.post(path, data={
            "username": "amy@example.com", "password": "whatever",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/caught", resp.headers["Location"])

        resp = self.client.get(resp.headers["Location"])
        self.assertIn(b"that was the drill", resp.data)
        self.assertIn(b"Nothing you typed was saved", resp.data)

    def test_stats_track_clicks_and_submissions(self):
        cid, pid = self.make_campaign_and_participant()
        path = self.sim_path(cid, pid)
        self.client.get(path)
        self.client.post(path, data={"username": "a", "password": "b"})
        with self.app.app_context():
            from phishguard import db
            stats = db.campaign_stats(cid)
            self.assertEqual(stats["participants"], 1)
            self.assertEqual(stats["clicks"], 1)
            self.assertEqual(stats["submissions"], 1)
            self.assertEqual(stats["click_rate"], 100.0)
            self.assertEqual(stats["submit_rate"], 100.0)

    def test_unknown_participant_is_404(self):
        self.assertEqual(self.client.get("/sim/999/999-abc").status_code, 404)

    def test_dashboard_requires_login_and_renders_after(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)  # redirected to /login
        self.login()
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"PhishGuard", resp.data)
        self.assertIn(b"passwords stored", resp.data)

    def test_global_stats_on_dashboard(self):
        self.login()
        cid, pid = self.make_campaign_and_participant()
        self.client.get(self.sim_path(cid, pid))
        resp = self.client.get("/")
        self.assertIn(b"campaigns</span>", resp.data)

    def test_every_catalog_template_renders_end_to_end(self):
        """Each catalog portal must serve its page, take a submission, and
        land on the caught page — with its own title and honest banner."""
        from phishguard.sim import CATALOG
        self.login()
        for entry in CATALOG:
            with self.subTest(template=entry["key"]):
                with self.app.app_context():
                    from phishguard import db
                    cid = db.create_campaign(
                        f"Drill {entry['key']}", entry["key"], consent=True)
                    pid = db.create_participant(
                        cid, "Sam", f"sam-{entry['key']}@example.com",
                        consent=True)
                    token = db.get_participant(pid, cid)["sim_token"]
                path = f"/sim/{cid}/{pid}-{token}"
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)
                self.assertIn(entry["title"].encode(), page.data)
                self.assertIn(b"Training exercise", page.data)  # honest banner
                sub = self.client.post(path, data={
                    "username": "sam", "password": "canary-never-stored"})
                self.assertEqual(sub.status_code, 302)
                caught = self.client.get(sub.headers["Location"])
                self.assertEqual(caught.status_code, 200)
                self.assertIn(b"that was the drill", caught.data)

    def test_dashboard_lists_catalog_titles(self):
        self.login()
        resp = self.client.get("/")
        self.assertIn(b"Acme Webmail", resp.data)
        self.assertIn(b"Meridian Bank", resp.data)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"phishguard", resp.data)


if __name__ == "__main__":
    unittest.main()
