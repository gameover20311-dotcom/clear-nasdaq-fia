#!/usr/bin/env python3
from __future__ import annotations
import json, os, time, urllib.error, urllib.request

BASE = os.environ['E2E_BASE_URL'].rstrip('/')
SCI = os.environ['FIA_SCIENTIFIC_OPERATION_SECRET']
MEMBER_PASSWORD = os.environ['E2E_MEMBER_TEST_PASSWORD']
EMAIL = 'foundation-e2e-%s@example.test' % os.environ.get('GITHUB_RUN_ID', str(int(time.time())))


def call(path, method='GET', headers=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


assert call('/api/health')[0] == 200
assert call('/api/learning/status')[0] == 200

code, body = call('/api/learning/resolve', 'POST')
assert code == 403 and SCI not in body, (code, body)

wrong = 'ci-invalid-scientific-credential'
code, body = call('/api/learning/resolve', 'POST', {'x-fia-scientific-operation': wrong})
assert code == 403 and wrong not in body and SCI not in body, (code, body)

code, body = call('/api/learning/resolve', 'POST', {'x-fia-scientific-operation': SCI})
assert code == 200, (code, body)

code, signup = call('/api/auth/signup', 'POST', body={
    'display_name': 'Foundation E2E Member', 'email': EMAIL, 'password': MEMBER_PASSWORD})
assert code == 200, (code, signup)
token = json.loads(signup)['token']
code, body = call('/api/learning/resolve', 'POST', {'Authorization': 'Bearer ' + token})
assert code == 403 and SCI not in body, (code, body)

code, body = call('/api/forward-oos/run-once', 'POST')
assert code == 403 and SCI not in body, (code, body)

print('REAL_HTTP_SCIENTIFIC_AUTH_E2E=PASS')
