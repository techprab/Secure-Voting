import pytest
from app.security.voter_guard import begin_single_cast
from app.errors import AlreadyVotedError
from app import db
from app.models import Voter

def test_r01_second_cast_same_voter_raises(app):
    with app.app_context():
        # Create a dummy voter (now with a dummy password)
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

        # Second cast for the same voter should fail
        with pytest.raises(AlreadyVotedError):
            begin_single_cast(voter.id)