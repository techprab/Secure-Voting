import pytest
from flask_jwt_extended import create_access_token

from app import create_app, db, limiter
from app.config import TestConfig
from app.models import Voter, Participation, PendingBallot, Ballot, UsedNonce


class EndpointLimitConfig(TestConfig):
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "memory://"
    WINDOW_CLOSE = "2099-01-01T00:00:00+00:00"


@pytest.fixture()
def limited():
    app = create_app(EndpointLimitConfig)
    with app.app_context():
        db.create_all()
        limiter.reset()
        voters = [
            Voter(
                name="limit-voter-" + str(i),
                division="Test Division",
                eligible=True, overseas=False, password_hash="unused",
            )
            for i in range(4)
        ]
        db.session.add_all(voters)
        db.session.commit()

        def token(index=0):
            return create_access_token(
                identity=str(voters[index].id),
                additional_claims={
                    "type": "voter", "division": "Test Division",
                },
            )

        try:
            yield app.test_client(), token
        finally:
            limiter.reset()
            db.session.remove()
            db.drop_all()


def submit(client, token, ip="192.0.2.10"):
    return client.post(
        "/ballot/submit", json={},
        headers={"Authorization": "Bearer " + token},
        environ_overrides={"REMOTE_ADDR": ip},
    )


def lookup(client, code, ip="192.0.2.10"):
    return client.get(
        "/participation/" + code,
        environ_overrides={"REMOTE_ADDR": ip},
    )


def test_r20_eleventh_submit_blocked_without_writes(limited):
    client, token = limited
    session = token()
    for _ in range(10):
        assert submit(client, session).status_code == 400
    assert submit(client, session).status_code == 429
    for model in (Participation, PendingBallot, Ballot, UsedNonce):
        assert db.session.query(model).count() == 0


def test_r20_new_token_and_ip_do_not_reset_voter_limit(limited):
    client, token = limited
    for _ in range(10):
        assert submit(client, token()).status_code == 400
    assert submit(client, token(), "192.0.2.11").status_code == 429


def test_r20_other_voter_has_separate_allowance(limited):
    client, token = limited
    session = token(0)
    for _ in range(10):
        assert submit(client, session).status_code == 400
    assert submit(client, session).status_code == 429
    assert submit(client, token(1)).status_code == 400


def test_r20_ip_limit_applies_across_voters(limited):
    client, token = limited
    for voter in range(3):
        session = token(voter)
        for _ in range(10):
            assert submit(client, session).status_code == 400
    assert submit(client, token(3)).status_code == 429


def test_r20_receipt_limit_spans_codes_but_separates_ips(limited):
    client, _ = limited
    for i in range(30):
        assert lookup(client, "missing-" + str(i)).status_code == 404
    assert lookup(client, "another-code").status_code == 429
    assert lookup(client, "another-code", "192.0.2.11").status_code == 404
