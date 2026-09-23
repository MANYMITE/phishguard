"""End-to-end flow tests: consent gates, dashboard, simulation lifecycle."""
import os
import tempfile
import unittest

from phishguard import create_app


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({
            "DATABASE": os.path.join(self.tmp.name, "test.db"),
            "TESTING": True,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            from phishguard import db
            db.init_app(self.app)  # idempotent

    def tearDown(self):
        self.tmp.cleanup()


class ConsentGates(Base):
    def test_campaign_requires_consent(self):
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
        with self.app.app_context():
            from phishguard import db
            cid = db.create_campaign("C", "acme_webmail", consent=True)
        resp = self.client.post(f"/campaigns/{cid}/participants", data={
            "name": "Rory", "email": "rory@example.com",  # no consent
        }, follow_redirects=True)
        self.assertIn(b"consented", resp.data)
        with self.app.app_context():
            from phishguard import db
            self.assertEqual(len(db.list_participants(cid)), 0)


class SimulationLifecycle(Base):
    def make_campaign_and_participant(self):
        with self.app.app_context():
            from phishguard import db
            cid = db.create_campaign("Drill", "acme_webmail", consent=True)
            pid = db.create_participant(cid, "Amy", "amy@example.com", consent=True)
        return cid, pid

    def test_landing_clicks_and_submit_redirects_to_caught(self):
        cid, pid = self.make_campaign_and_participant()
        resp = self.client.get(f"/sim/{cid}/{pid}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Acme Webmail", resp.data)
        self.assertIn(b"Training exercise", resp.data)  # honest banner

        resp = self.client.post(f"/sim/{cid}/{pid}", data={
            "username": "amy@example.com", "password": "whatever",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/caught", resp.headers["Location"])

        resp = self.client.get(f"/sim/{cid}/{pid}/caught")
        self.assertIn(b"that was the drill", resp.data)
        self.assertIn(b"Nothing you typed was saved", resp.data)

    def test_stats_track_clicks_and_submissions(self):
        cid, pid = self.make_campaign_and_participant()
        self.client.get(f"/sim/{cid}/{pid}")
        self.client.post(f"/sim/{cid}/{pid}", data={"username": "a", "password": "b"})
        with self.app.app_context():
            from phishguard import db
            stats = db.campaign_stats(cid)
            self.assertEqual(stats["participants"], 1)
            self.assertEqual(stats["clicks"], 1)
            self.assertEqual(stats["submissions"], 1)
            self.assertEqual(stats["click_rate"], 100.0)
            self.assertEqual(stats["submit_rate"], 100.0)

    def test_unknown_participant_is_404(self):
        resp = self.client.get("/sim/999/999")
        self.assertEqual(resp.status_code, 404)

    def test_dashboard_renders(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"PhishGuard", resp.data)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"phishguard", resp.data)


if __name__ == "__main__":
    unittest.main()
