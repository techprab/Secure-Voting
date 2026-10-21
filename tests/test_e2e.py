
"""End-to-end test for the supported election voting workflow."""

import uuid
from datetime import date, timedelta

from app import db, models
from app.services.ballot_def import candidate_set_hash


def auth_headers(voter_token, staff_token, voter_id=None, role=None):
    """Build authorization headers using the root test fixtures."""
    token = (
        voter_token(voter_id)
        if voter_id is not None
        else staff_token(role=role)
    )
    return {"Authorization": f"Bearer {token}"}

def test_full_election(app, client, voter_token, staff_token):
    division_name = "E2E-TEST"

    # 1. Create a delegate, candidates, and an eligible voter.
    delegate = models.Staff(
        username=f"e2e-delegate-{uuid.uuid4().hex}",
        role="delegate",
        password_hash="unused",
        totp_secret="unused",
        recertified_until=date.today() + timedelta(days=90),
    )
    candidates = [
        models.Candidate(
            division=division_name,
            name=name,
            position=str(position),
            excluded=False,
        )
        for position, name in enumerate(
            ["Alpha", "Bravo", "Charlie"], start=1
        )
    ]
    voter = models.Voter(
        name="E2E Test Voter",
        division=division_name,
        eligible=True,
        overseas=False,
        password_hash="unused",
    )

    db.session.add_all([delegate, *candidates, voter])
    db.session.flush()

    # 2. Approve the candidate set through the delegate endpoint.
    approval_response = client.post(
        "/staff/candidates/approve",
        json={"division": division_name},
        headers=auth_headers(voter_token, staff_token, role="delegate"),
    )
    assert approval_response.status_code == 201

    # Refresh the expected ranking in the application's ballot order.
    candidate_ids = [
        candidate.id
        for candidate in models.Candidate.query.filter_by(
            division=division_name
        ).order_by(models.Candidate.position, models.Candidate.id).all()
    ]

    # 3. Retrieve the approved ballot.
    ballot_response = client.get(
        "/ballot",
        headers=auth_headers(voter_token, staff_token, voter_id=voter.id),
    )
    assert ballot_response.status_code == 200
    assert [
        candidate["id"]
        for candidate in ballot_response.get_json()["candidates"]
    ] == candidate_ids

    # 4. Preview the ranking.
    preview_response = client.post(
        "/ballot/preview",
        json={"preferences": candidate_ids},
        headers=auth_headers(voter_token, staff_token, voter_id=voter.id),
    )
    assert preview_response.status_code == 200
    preview = preview_response.get_json()
    assert [
        row["candidate_id"] for row in preview["summary"]
    ] == candidate_ids

    # 5. Explicitly confirm and submit the same ranking.
    submit_response = client.post(
        "/ballot/submit",
        json={
            "preferences": candidate_ids,
            "preview_token": preview["preview_token"],
            "confirm": True,
            "nonce": str(uuid.uuid4()),
        },
        headers=auth_headers(voter_token, staff_token, voter_id=voter.id),
    )
    assert submit_response.status_code == 201
    submission = submit_response.get_json()
    assert set(submission) == {"participation_code"}

    # 6. Verify the receipt without exposing the ranking.
    receipt_response = client.get(
        f"/participation/{submission['participation_code']}"
    )
    assert receipt_response.status_code == 200
    assert receipt_response.get_json() == {"voted": True}

    # 7. Check that participation and the pending ballot were persisted.
    participation = models.Participation.query.filter_by(
        voter_id=voter.id
    ).one()
    assert participation.code == submission["participation_code"]

    assert models.PendingBallot.query.filter_by(
        division=division_name
    ).count() == 1

    # Ensure the candidate approval matches the current candidate set.
    approval = models.CandidateSetApproval.query.filter_by(
        division=division_name
    ).order_by(models.CandidateSetApproval.id.desc()).first()
    assert approval is not None
    assert approval.set_hash == candidate_set_hash(division_name)
