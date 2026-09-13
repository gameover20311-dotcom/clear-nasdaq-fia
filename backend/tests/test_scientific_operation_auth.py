import contextlib
import io
import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class ScientificOperationAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ.pop("DATABASE_URL", None)
        os.environ["CLEAR_NASDAQ_AUTH_STATE_DIR"] = cls.tmp.name
        os.environ["CLEAR_NASDAQ_AUTH_SECRET"] = "membership-signing-secret-abcdefghijklmnopqrstuvwxyz-123456"
        os.environ["FIA_SCIENTIFIC_OPERATION_SECRET"] = "science-secret-abcdefghijklmnopqrstuvwxyz-123456789"
        import main
        cls.main = main
        from fia.auth_api import create_user, issue_session_token
        user = create_user("Regression Member", "member@example.test", "Password12345")
        cls.member_token = issue_session_token(user)
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.calls = 0

        async def fake_resolve(*args, **kwargs):
            self.calls += 1
            return 7

        self.main.resolve_due_forward_records = fake_resolve
        self.main.build_learning_status = lambda: {"ok": True, "records": 0}

    def test_missing_secret_refused(self):
        r = self.client.post("/api/learning/resolve")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("detail"), "SCIENTIFIC_OPERATION_AUTH_REQUIRED")
        self.assertEqual(self.calls, 0)

    def test_wrong_secret_refused_and_not_echoed(self):
        wrong = "wrong-scientific-secret-never-echo-123456789"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r = self.client.post(
                "/api/learning/resolve",
                headers={"x-fia-scientific-operation": wrong},
            )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("detail"), "SCIENTIFIC_OPERATION_AUTH_FAILED")
        self.assertNotIn(wrong, r.text)
        self.assertNotIn(wrong, buf.getvalue())
        self.assertEqual(self.calls, 0)

    def test_valid_scientific_secret_allowed(self):
        secret = os.environ["FIA_SCIENTIFIC_OPERATION_SECRET"]
        r = self.client.post(
            "/api/learning/resolve",
            headers={"x-fia-scientific-operation": secret},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("resolved_fields_updated"), 7)
        self.assertEqual(self.calls, 1)

    def test_membership_bearer_alone_insufficient(self):
        r = self.client.post(
            "/api/learning/resolve",
            headers={"authorization": "Bearer " + self.member_token},
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("detail"), "SCIENTIFIC_OPERATION_AUTH_REQUIRED")
        self.assertEqual(self.calls, 0)

    def test_learning_status_is_read_only_without_secret(self):
        r = self.client.get("/api/learning/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.calls, 0)

    def test_health_read_only_unaffected(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))

    def test_secret_not_in_generic_errors(self):
        secret = os.environ["FIA_SCIENTIFIC_OPERATION_SECRET"]
        r = self.client.post("/api/learning/resolve")
        self.assertNotIn(secret, r.text)


if __name__ == "__main__":
    unittest.main()
