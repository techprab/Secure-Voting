"""Counting from sealed ballots. Owner: Prabh (Slice E).

R-12  Every count decrypts the sealed ballots again. CountCache is written for display
      only and nothing in this module reads it, so a poisoned cache cannot change a result.
R-19  Two tallies written in different ways (count_a: plain loop, count_b: Counter) must
      give the same totals, and the ballot hash chain must verify, before a result can be
      released. release_check() is the single gate the release route goes through.

Counting rule for the prototype: first-preference totals per division. A ballot counts
for its highest-ranked candidate who has not been excluded (R-21); a ballot whose every
preference is excluded counts for nobody.
"""
from collections import Counter

from .. import db
from ..errors import ReleaseBlocked
from ..models import Candidate, CountCache
from ..security.crypto import open_ballot, verify_chain
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


def count_b(division: str) -> dict[int, int]:
    """Tally 2: written differently on purpose. Collect the first valid preference of each
    ballot into a list, then count the list with collections.Counter."""
    still_standing = {
        c.id for c in _division_candidates(division) if not c.excluded
    }

    first_choices = []
    for ballot in sealed_ballots(division):
        ranking = open_ballot(ballot.blob)
        first = next((cid for cid in ranking if cid in still_standing), None)
        if first is not None:
            first_choices.append(first)

    tally = Counter(first_choices)
    return {cid: tally[cid] for cid in sorted(still_standing)}


def release_check(division: str) -> dict[int, int]:
    """Return the agreed totals, or raise ReleaseBlocked.

    Blocks when the ballot chain fails verification (R-10), when a ballot fails to
    decrypt, or when the two tallies disagree.
    """
    if not verify_chain():
        raise ReleaseBlocked("ballot hash chain failed verification")
    try:
        first = count_a(division)
        second = count_b(division)
    except ValueError as exc:
        raise ReleaseBlocked("a sealed ballot failed authentication") from exc
    if first != second:
        raise ReleaseBlocked("independent tallies disagree")
    return first


def write_display_cache(division: str, totals: dict[int, int]) -> None:
    """Replace the division's CountCache rows. Display only: never read back for counting."""
    CountCache.query.filter_by(division=division).delete()
    for candidate_id, votes in totals.items():
        db.session.add(
            CountCache(division=division, candidate_id=candidate_id, votes=votes)
        )
    db.session.flush()
