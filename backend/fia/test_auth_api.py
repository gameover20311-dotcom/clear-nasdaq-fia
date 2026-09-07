from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fia import auth_api


def run() -> None:
    with tempfile.TemporaryDirectory() as td:
        os.environ['CLEAR_NASDAQ_AUTH_STATE_DIR'] = td
        os.environ['CLEAR_NASDAQ_AUTH_DB_PATH'] = str(Path(td) / 'auth.sqlite3')
        os.environ['CLEAR_NASDAQ_AUTH_SECRET'] = 'test-secret-' + ('x' * 64)

        user = auth_api.create_user('Test User', 'Test@Example.com', 'SecurePass123')
        assert user['email'] == 'test@example.com'
        assert user['plan'] == 'FULL_ACCESS'
        assert user['status'] == 'ACTIVE'

        try:
            auth_api.create_user('Another User', 'test@example.com', 'SecurePass123')
            raise AssertionError('duplicate email accepted')
        except ValueError as exc:
            assert str(exc) == 'EMAIL_ALREADY_REGISTERED'

        logged = auth_api.authenticate_user('TEST@example.com', 'SecurePass123')
        assert logged['id'] == user['id']

        token = auth_api.issue_session_token(logged, now=1_000_000)
        decoded = auth_api.decode_session_token(token, now=1_000_001)
        assert decoded['user']['id'] == user['id']
        assert decoded['payload']['plan'] == 'FULL_ACCESS'

        revoked_token = auth_api.issue_session_token(logged, now=1_000_010)
        auth_api.revoke_session_token(revoked_token, now=1_000_011)
        try:
            auth_api.decode_session_token(revoked_token, now=1_000_012)
            raise AssertionError('revoked token accepted')
        except ValueError as exc:
            assert str(exc) == 'SESSION_REVOKED'

        left, right = token.split('.', 1)
        tampered = left[:-1] + ('A' if left[-1:] != 'A' else 'B') + '.' + right
        try:
            auth_api.decode_session_token(tampered, now=1_000_001)
            raise AssertionError('tampered token accepted')
        except ValueError:
            pass

        try:
            auth_api.decode_session_token(token, now=1_000_000 + auth_api.SESSION_SECONDS + 1)
            raise AssertionError('expired token accepted')
        except ValueError as exc:
            assert str(exc) == 'SESSION_EXPIRED'

        for _ in range(auth_api.LOCK_AFTER_FAILURES):
            try:
                auth_api.authenticate_user('test@example.com', 'wrong-password')
            except ValueError:
                pass
        try:
            auth_api.authenticate_user('test@example.com', 'SecurePass123')
            raise AssertionError('lockout failed')
        except ValueError as exc:
            assert str(exc) == 'ACCOUNT_TEMPORARILY_LOCKED'

    print('AUTH_V3_TESTS_PASS')


if __name__ == '__main__':
    run()
