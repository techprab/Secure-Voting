"""Counting from sealed ballots. Owner: Prabh (Slice E).

R-12  Every count decrypts the sealed ballots again. CountCache is written for display
      only and nothing in this module reads it, so a poisoned cache cannot change a result.

Counting rule for the prototype: first-preference totals per division. A ballot counts
for its highest-ranked candidate who has not been excluded (R-21); a ballot whose every
preference is excluded counts for nobody.
"""
from .. import db
from ..models import Candidate, CountCache
from ..security.crypto import open_ballot
from .ballots import sealed_ballots


class UnknownDivision(LookupError):
    pass


def _division_candidates(division: str) -> list[Candidate]:
    candidates = (
        Candidate.query.filter_by(division=division).order_by(Candidate.id).all()
    )
    if not candidates:
        raise UnknownDivision(division)
    return candidates


def count_a(division: str) -> dict[int, int]:
    """Tally 1: walk every sealed ballot and add one to its first non-excluded preference."""
    totals = {}
    for candidate in _division_candidates(division):
        if not candidate.excluded:
            totals[candidate.id] = 0

    for ballot in sealed_ballots(division):
        preferences = open_ballot(ballot.blob)  # raises ValueError on a failed GCM tag
        for candidate_id in preferences:
            if candidate_id in totals:
                totals[candidate_id] += 1
                break
    return totals


def count_b(division: str):
    raise NotImplementedError("count_b is not implemented yet")  # STUB until R-19


def release_check(division: str):
    raise NotImplementedError("release_check is not implemented yet")  # STUB until R-19


def write_display_cache(division: str, totals: dict[int, int]) -> None:
    """Replace the division's CountCache rows. Display only: never read back for counting."""
    CountCache.query.filter_by(division=division).delete()
    for candidate_id, votes in totals.items():
        db.session.add(
            CountCache(division=division, candidate_id=candidate_id, votes=votes)
        )
    db.session.flush()
