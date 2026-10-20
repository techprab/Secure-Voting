"""R-19: two independently written tallies must agree, and the chain must verify, before release."""
import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

import app.services.count as count_service
from app import db
from app.errors import ReleaseBlocked
from app.models import Ballot, Candidate, CountCache
from app.services.count import count_a, count_b, release_check

DIVISION = "Division E"  # same value as tests/slice_e/conftest.py


def test_r19_agree_allows_release(candidates, add_ballots):
    a, b, c = candidates
    add_ballots([[a, b, c]] * 2 + [[c, b, a]] * 5)

    assert count_a(DIVISION) == count_b(DIVISION) == {a: 2, b: 0, c: 5}
    assert release_check(DIVISION) == {a: 2, b: 0, c: 5}


def test_r19_tallies_agree_with_exclusions_and_exhausted_ballots(candidates, add_ballots):
    a, b, c = candidates
    add_ballots([[a], [a, c], [b, a, c], [a, b]])
    db.session.get(Candidate, a).excluded = True
    db.session.commit()

    # [a] is exhausted once Alpha is excluded: it counts for nobody in both tallies.
    assert count_a(DIVISION) == count_b(DIVISION) == {b: 2, c: 1}


def test_r19_bug_in_one_blocks_release(candidates, add_ballots, monkeypatch):
    a, b, c = candidates
    add_ballots([[a, b, c]] * 3 + [[b, a, c]])
    real_count_b = count_service.count_b

    def count_b_drops_a_ballot(division):
        totals = real_count_b(division)
        totals[a] -= 1
        return totals

    monkeypatch.setattr(count_service, "count_b", count_b_drops_a_ballot)

    with pytest.raises(ReleaseBlocked):
        release_check(DIVISION)


def test_r19_broken_chain_blocks_release(candidates, add_ballots):
    a, b, c = candidates
    add_ballots([[a, b, c]] * 3)
    ballot = Ballot.query.order_by(Ballot.id).first()
    ballot.hash = "f" * 64
    db.session.commit()

    with pytest.raises(ReleaseBlocked):
        release_check(DIVISION)


def test_r19_release_gate_never_reads_count_cache(candidates, add_ballots):
    a, b, c = candidates
    add_ballots([[a, b, c], [c, a, b]])
    cache_reads = []

    def watch(state):
        if state.is_select and any(m.class_ is CountCache for m in state.all_mappers):
            cache_reads.append(str(state.statement))

    event.listen(Session, "do_orm_execute", watch)
    try:
        count_b(DIVISION)
        release_check(DIVISION)
    finally:
        event.remove(Session, "do_orm_execute", watch)

    assert cache_reads == []
