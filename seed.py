"""Idempotent local development seed for Secure Voting.

Creates two divisions, candidates and approvals, 60 seed voters,
four staff roles, and 20 encrypted ballots per division.

Run from the repository root with:
    python seed.py

Requires BALLOT_KEY to be configured in the environment or .env.
Never use this seed data or its credentials in production.
"""

import base64
import secrets
from datetime import date, datetime, timedelta, timezone

import bcrypt

from app import create_app, db
from app.models import (
    Ballot,
    Candidate,
    CandidateSetApproval,
    Participation,
    Staff,
    Voter,
)
from app.security.crypto import (
    chain_hash,
    seal_ballot,
    verify_chain,
)
from app.services.ballot_def import candidate_set_hash


DIVISIONS = ("Division 1", "Division 2")
VOTERS_PER_DIVISION = 30
BALLOTS_PER_DIVISION = 20
STAFF_ROLES = ("admin", "delegate", "auditor", "officer")
ZERO_HASH = "0" * 64


def ensure_staff(role):
    """Return the development staff account for a role, creating it if needed."""
    username = f"seed-{role}"

    staff = Staff.query.filter_by(username=username).first()

    if staff is None:
        staff = Staff(
            username=username,
            role=role,
            password_hash=bcrypt.hashpw(
                f"LocalOnly-{role}-{secrets.token_urlsafe(12)}".encode("utf-8"),
                bcrypt.gensalt(),
            ).decode("utf-8"),
            # Local development placeholder only.
            # Replace with a properly provisioned TOTP secret if testing MFA.
            totp_secret="JBSWY3DPEHPK3PXP",
            recertified_until=date.today() + timedelta(days=90),
        )
        db.session.add(staff)
        db.session.flush()

    elif staff.role != role:
        raise RuntimeError(
            f"Username {username!r} exists with unexpected role "
            f"{staff.role!r}."
        )

    return staff


def ensure_candidates(division):
    """Ensure exactly three seed candidates exist for a division."""
    candidates = (
        Candidate.query.filter_by(division=division)
        .order_by(Candidate.id.asc())
        .all()
    )

    if len(candidates) > 3:
        raise RuntimeError(
            f"{division} already has more than three candidates. "
            "Review the existing rows before seeding; none were deleted."
        )

    names = ("Candidate A", "Candidate B", "Candidate C")

    for index, candidate in enumerate(candidates):
        candidate.position = str(index + 1)

    for index in range(len(candidates), 3):
        candidate = Candidate(
            division=division,
            name=names[index],
            position=str(index + 1),
            excluded=False,
        )
        db.session.add(candidate)
        candidates.append(candidate)

    db.session.flush()
    return sorted(candidates, key=lambda candidate: (int(candidate.position), candidate.id))


def ensure_voters():
    """Create 30 seed voters per division, reusing the original demo voter."""
    demo_voter = Voter.query.filter_by(name="Demo Voter").first()
    existing_first = Voter.query.filter_by(name="Seed Voter 01").first()

    if demo_voter is not None and existing_first is None:
        demo_voter.name = "Seed Voter 01"
        demo_voter.division = DIVISIONS[0]
        demo_voter.eligible = True
        demo_voter.overseas = True
        demo_voter.password_hash=bcrypt.hashpw(
            b"LocalOnly-Voter-ChangeMe",
            bcrypt.gensalt(),
        ).decode("utf-8")

    for division_index, division in enumerate(DIVISIONS):
        for number in range(1, VOTERS_PER_DIVISION + 1):
            name = f"Seed Voter {division_index * VOTERS_PER_DIVISION + number:02d}"
            voter = Voter.query.filter_by(name=name).first()

            if voter is None:
                voter = Voter(
                    name=name,
                    division=division,
                    eligible=True,
                    overseas=(
                        division_index == 0 and number <= 5
                    ),
                    password_hash=bcrypt.hashpw(
                        b"LocalOnly-Voter-ChangeMe",
                        bcrypt.gensalt(),
                    ).decode("utf-8"),
                )
                db.session.add(voter)
            else:
                voter.division = division
                voter.eligible = True
                voter.overseas = (
                    division_index == 0 and number <= 5
                )

    db.session.flush()


def ensure_approval(division, delegate_id):
    """Approve the current candidate set if it is not already approved."""
    set_hash = candidate_set_hash(division)

    approval = (
        CandidateSetApproval.query.filter_by(division=division)
        .order_by(CandidateSetApproval.id.desc())
        .first()
    )

    if approval is None or approval.set_hash != set_hash:
        db.session.add(
            CandidateSetApproval(
                division=division,
                set_hash=set_hash,
                approved_by=delegate_id,
            )
        )
        db.session.flush()



def ensure_ballots(division, candidate_ids, previous_hash):
    """Ensure 20 ballots and 20 participation records for a division."""
    existing_count = Ballot.query.filter_by(division=division).count()

    participating_voter_ids = {
        voter_id
        for (voter_id,) in (
            db.session.query(Participation.voter_id)
            .join(Voter, Participation.voter_id == Voter.id)
            .filter(Voter.division == division)
            .all()
        )
    }
    participation_count = len(participating_voter_ids)

    if existing_count > BALLOTS_PER_DIVISION:
        raise RuntimeError(
            f"{division} already has more than "
            f"{BALLOTS_PER_DIVISION} ballots."
        )

    if participation_count > BALLOTS_PER_DIVISION:
        raise RuntimeError(
            f"{division} already has more than "
            f"{BALLOTS_PER_DIVISION} participation records."
        )

    voters = (
        Voter.query.filter_by(division=division, eligible=True)
        .order_by(Voter.id.asc())
        .all()
    )
    unused_voters = [
        voter for voter in voters
        if voter.id not in participating_voter_ids
    ]

    ballots_to_add = BALLOTS_PER_DIVISION - existing_count
    participations_to_add = BALLOTS_PER_DIVISION - participation_count

    if len(unused_voters) < max(ballots_to_add, participations_to_add):
        raise RuntimeError(f"Not enough unused eligible voters in {division}.")

    # Append new ballots to the existing global hash chain.
    for index in range(ballots_to_add):
        blob = seal_ballot(candidate_ids)
        ballot_hash = chain_hash(previous_hash, blob)

        db.session.add(
            Ballot(
                division=division,
                blob=blob,
                prev_hash=previous_hash,
                hash=ballot_hash,
                batch_id="seed-development",
            )
        )
        previous_hash = ballot_hash

        # Add only as many participation records as are needed.
        if index < participations_to_add:
            voter = unused_voters[index]
            db.session.add(
                Participation(
                    voter_id=voter.id,
                    code=secrets.token_hex(16),
                    voted_hour=datetime.now(timezone.utc).strftime(
                        "%Y-%m-%d %H"
                    ),
                )
            )
            participating_voter_ids.add(voter.id)

    # Repair a participation deficit when enough ballots already exist.
    if participations_to_add > ballots_to_add:
        remaining_voters = [
            voter for voter in voters
            if voter.id not in participating_voter_ids
        ]
        extra_needed = participations_to_add - ballots_to_add

        for voter in remaining_voters[:extra_needed]:
            db.session.add(
                Participation(
                    voter_id=voter.id,
                    code=secrets.token_hex(16),
                    voted_hour=datetime.now(timezone.utc).strftime(
                        "%Y-%m-%d %H"
                    ),
                )
            )

    db.session.flush()
    return previous_hash



def main():
    app = create_app()

    with app.app_context():
        db.create_all()

        encoded_key = app.config.get("BALLOT_KEY", "").strip()
        if not encoded_key:
            raise RuntimeError(
                "BALLOT_KEY is missing. Configure it in your local .env."
            )

        try:
            decoded_key = base64.b64decode(encoded_key, validate=True)
        except Exception as exc:
            raise RuntimeError("BALLOT_KEY must be valid Base64.") from exc

        if len(decoded_key) != 32:
            raise RuntimeError(
                "BALLOT_KEY must decode to exactly 32 bytes."
            )

        # Preserve existing ballot data; never silently extend a broken chain.
        if not verify_chain():
            raise RuntimeError(
                "The existing ballot hash chain is invalid. "
                "Investigate it before running the seed."
            )

        # Ensure the required staff accounts exist.
        staff_by_role = {
            role: ensure_staff(role)
            for role in STAFF_ROLES
        }
        db.session.flush()

        # Create candidates and approvals after candidate rows have IDs.
        candidates_by_division = {}

        for division in DIVISIONS:
            candidates = ensure_candidates(division)
            candidates_by_division[division] = candidates

        ensure_voters()
        db.session.flush()

        for division in DIVISIONS:
            ensure_approval(
                division,
                staff_by_role["delegate"].id,
            )

        db.session.commit()

        # Continue the single global hash chain from the final existing ballot.
        last_ballot = (
            Ballot.query.order_by(Ballot.id.desc()).first()
        )
        previous_hash = last_ballot.hash if last_ballot else ZERO_HASH

        # Seed each division in sequence, maintaining one global chain.
        for division in DIVISIONS:
            candidate_ids = [
                candidate.id
                for candidate in candidates_by_division[division]
            ]

            previous_hash = ensure_ballots(
                division,
                candidate_ids,
                previous_hash,
            )
            db.session.commit()

        if not verify_chain():
            raise RuntimeError("Seed finished, but ballot chain verification failed.")

        print("Seed complete.")
        print(f"Divisions: {len(DIVISIONS)}")
        print("Seed voters: 60 (5 overseas)")
        print("Candidates: 3 per division")
        print("Staff roles: admin, delegate, auditor, officer")
        print("Encrypted ballots: 20 per division")
        print("Ballot chain verified successfully.")
        print("Development-only accounts; do not use in production.")


if __name__ == "__main__":
    main()
