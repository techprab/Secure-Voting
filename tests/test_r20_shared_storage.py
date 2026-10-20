"""Separate app processes sharing a real temporary Redis backend."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis


WORKER = """
import json
import sys
from flask_jwt_extended import create_access_token
from app import create_app, db
from app.config import TestConfig
from app.models import Voter

class SharedConfig(TestConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    JWT_SECRET_KEY = "shared-storage-test-only-" + "x" * 32
    WINDOW_CLOSE = "2099-01-01T00:00:00+00:00"
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = sys.argv[1]
    RATELIMIT_KEY_PREFIX = sys.argv[2]
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_SWALLOW_ERRORS = False
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = False

app = create_app(SharedConfig)
with app.app_context():
    db.create_all()
    db.session.add(Voter(
        id=int(sys.argv[4]), name="shared-voter", division="Test Division",
        eligible=True, overseas=False, password_hash="unused",
    ))
    db.session.commit()
    token = create_access_token(
        identity=sys.argv[4],
        additional_claims={"type": "voter", "division": "Test Division"},
    )
    client = app.test_client()
    statuses = []
    for _ in range(int(sys.argv[3])):
        response = client.post(
            "/ballot/submit", json={},
            headers={"Authorization": "Bearer " + token},
            environ_overrides={"REMOTE_ADDR": "192.0.2.10"},
        )
        statuses.append(response.status_code)
    print(json.dumps(statuses))
    db.session.remove()
    db.drop_all()
"""


@pytest.fixture()
def redis_backend(tmp_path):
    executable = shutil.which("redis-server")
    if executable is None:
        if os.environ.get("R20_REQUIRE_REDIS") == "1":
            pytest.fail("Redis is required for this verification run.")
        pytest.skip("Live Redis tests require redis-server on PATH")

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    logfile = (tmp_path / "redis.log").open("w")
    process = subprocess.Popen([
        executable,
        "--bind", "127.0.0.1",
        "--port", str(port),
        "--protected-mode", "yes",
        "--save", "",
        "--appendonly", "no",
        "--dir", str(tmp_path),
    ], stdout=logfile, stderr=subprocess.STDOUT)

    uri = f"redis://127.0.0.1:{port}/0"
    client = redis.Redis.from_url(
        uri, socket_connect_timeout=0.5, socket_timeout=0.5
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            if process.poll() is not None:
                pytest.fail("Temporary Redis exited; inspect its test log.")
            try:
                if client.ping():
                    break
            except redis.exceptions.ConnectionError:
                pass
            if time.monotonic() >= deadline:
                pytest.fail("Temporary Redis did not start within 10 seconds.")
            time.sleep(0.05)
        yield uri, "r20-test-" + uuid.uuid4().hex
    finally:
        client.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        logfile.close()


def run_worker(backend, requests, voter_id=1):
    uri, prefix = backend
    result = subprocess.run(
        [sys.executable, "-c", WORKER, uri, prefix, str(requests), str(voter_id)],
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_r20_limit_survives_application_process_restart(redis_backend):
    # First app process consumes six of the voter's ten requests.
    assert run_worker(redis_backend, 6) == [400] * 6

    # A fresh process and token must inherit the remaining allowance.
    assert run_worker(redis_backend, 5) == [400] * 4 + [429]


def test_r20_two_process_burst_shares_one_allowance(redis_backend):
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run_worker, redis_backend, 20)
            for _ in range(2)
        ]
        statuses = [status for future in futures for status in future.result()]

    assert statuses.count(400) == 10, statuses
    assert statuses.count(429) == 30, statuses
    print(
        f"\n40 requests across 2 app processes: "
        f"10 reached validation, 30 throttled; "
        f"{time.monotonic() - start:.2f}s including process startup."
    )


# Reuse the same Redis configuration, but submit a real confirmed ballot.
VALID_WORKER = WORKER.split("app = create_app(SharedConfig)")[0] + """
import uuid
from datetime import date, datetime, timedelta
from app.models import (
    Candidate, CandidateSetApproval, Staff,
    Participation, PendingBallot, Ballot, UsedNonce,
)
from app.services.ballot_def import candidate_set_hash

app = create_app(SharedConfig)
with app.app_context():
    db.create_all()
    division = "Test Division"
    staff = Staff(
        username="test-delegate", role="delegate",
        password_hash="unused", totp_secret="unused",
        recertified_until=date.today() + timedelta(days=90),
    )
    voter = Voter(
        id=2, name="legitimate-voter", division=division,
        eligible=True, overseas=False, password_hash="unused",
    )
    candidates = [
        Candidate(
            division=division, name=name,
            position=str(index + 1), excluded=False,
        )
        for index, name in enumerate(["Alpha", "Bravo", "Charlie"])
    ]
    db.session.add_all([staff, voter] + candidates)
    db.session.flush()
    db.session.add(CandidateSetApproval(
        division=division,
        set_hash=candidate_set_hash(division),
        approved_by=staff.id,
        approved_at=datetime.utcnow(),
    ))
    db.session.commit()
    preferences = [candidate.id for candidate in candidates]
    token = create_access_token(
        identity="2",
        additional_claims={"type": "voter", "division": division},
    )
    headers = {"Authorization": "Bearer " + token}
    environ = {"REMOTE_ADDR": sys.argv[3]}
    client = app.test_client()
    preview = client.post(
        "/ballot/preview",
        json={"preferences": preferences},
        headers=headers, environ_overrides=environ,
    )
    assert preview.status_code == 200, preview.get_json()
    response = client.post(
        "/ballot/submit",
        json={
            "preferences": preferences,
            "preview_token": preview.get_json()["preview_token"],
            "confirm": True,
            "nonce": str(uuid.uuid4()),
        },
        headers=headers, environ_overrides=environ,
    )
    print(json.dumps({
        "status": response.status_code,
        "participation": db.session.query(Participation).count(),
        "ballots": (
            db.session.query(PendingBallot).count()
            + db.session.query(Ballot).count()
        ),
        "nonces": db.session.query(UsedNonce).count(),
    }))
    db.session.remove()
    db.drop_all()
"""


def run_valid_worker(backend, ip):
    uri, prefix = backend
    result = subprocess.run(
        [sys.executable, "-c", VALID_WORKER, uri, prefix, ip],
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_r20_valid_vote_with_separate_ip_during_scheduled_burst(redis_backend):
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        burst = pool.submit(run_worker, redis_backend, 40)
        valid = pool.submit(run_valid_worker, redis_backend, "192.0.2.20")
        statuses = burst.result()
        result = valid.result()

    assert statuses.count(400) == 10, statuses
    assert statuses.count(429) == 30, statuses
    assert result == {
        "status": 201, "participation": 1, "ballots": 1, "nonces": 1,
    }
    print(
        f"\nValid vote and 40-request burst scheduled concurrently: "
        f"vote accepted, 30 requests throttled; "
        f"{time.monotonic() - start:.2f}s including process startup."
    )


def test_r20_exhausted_shared_ip_blocks_valid_voter(redis_backend):
    # Three distinct voters each consume ten requests on the same IP.
    # Voter 2 is reserved for the valid-ballot worker.
    for voter_id in (1, 3, 4):
        assert run_worker(redis_backend, 10, voter_id=voter_id) == [400] * 10
    result = run_valid_worker(redis_backend, "192.0.2.10")
    assert result == {
        "status": 429, "participation": 0, "ballots": 0, "nonces": 0,
    }
