import pytest
from app.security.voter_guard import begin_single_cast
from app.errors import AlreadyVotedError
from app import db
from app.models import Voter, Participation

def test_r01_second_cast_same_voter_raises(app):
    with app.app_context():
        # Create a dummy voter
        voter = Voter(
            name="Test Voter", 
            division="Test Division", 
            eligible=True, 
            password_hash="fake_hash_for_testing"
        )
        db.session.add(voter)
        db.session.commit()

        # First cast should succeed
        code1 = begin_single_cast(voter.id)
        db.session.commit()
        assert code1 is not None

        # Capture the initial participation record to ensure it remains intact
        initial_participation = Participation.query.filter_by(voter_id=voter.id).first()
        assert initial_participation is not None
        initial_code = initial_participation.code

        # Second cast for the same voter should fail
        with pytest.raises(AlreadyVotedError):
            begin_single_cast(voter.id)

        # Verify the original record remains intact after the duplicate attempt
        db.session.expire_all()  # Refresh session to pull latest from DB
        final_participation = Participation.query.filter_by(voter_id=voter.id).first()
        assert final_participation is not None
        assert final_participation.code == initial_code