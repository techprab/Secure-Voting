"""R-12: a recount re-processes the sealed source ballots, never a cached tally."""
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import db
from app.models import Ballot, Candidate, CountCache
from app.services.count import count_a

DIVISION = "Division E"  # same value as tests/slice_e/conftest.py


def test_r12_recount_counts_first_preferences(client, candidates, add_ballots, staff_token, auth):
    a, b, c = candidates
    add_ballots([[a, b, c]] * 3 + [[b, a, c]] * 2 + [[c, b, a]])

    resp = client.post(f"/count/recount/{DIVISION}", headers=auth(staff_token("officer")))

    assert resp.status_code == 200
    assert resp.get_json()["totals"] == {str(a): 3, str(b): 2, str(c): 1}


def test_r12_poisoned_cache_ignored(client, candidates, add_ballots, staff_token, auth):
    a, b, c = candidates
    add_ballots([[a, b, c]] * 4 + [[b, c, a]])
    headers = auth(staff_token("officer"))
    first = client.post(f"/count/recount/{DIVISION}", headers=headers).get_json()["totals"]

    # An attacker with database access rewrites the display cache.
    for row in CountCache.query.filter_by(division=DIVISION):
        row.votes = 9999 if row.candidate_id == c else 0
    db.session.commit()

    second = client.post(f"/count/recount/{DIVISION}", headers=headers).get_json()["totals"]
    assert second == first == {str(a): 4, str(b): 1, str(c): 0}
    # The recount also overwrote the poisoned cache with the true numbers.
    cache = {r.candidate_id: r.votes for r in CountCache.query.filter_by(division=DIVISION)}
    assert cache == {a: 4, b: 1, c: 0}


def test_r12_no_counting_path_reads_count_cache(app, candidates, add_ballots):
    a, b, c = candidates
    add_ballots([[a, b, c], [c, a, b]])
    cache_reads = []

    def watch(state):
        if state.is_select and any(m.class_ is CountCache for m in state.all_mappers):
            cache_reads.append(str(state.statement))

    event.listen(Session, "do_orm_execute", watch)
    try:
        count_a(DIVISION)
    finally:
        event.remove(Session, "do_orm_execute", watch)

    assert cache_reads == []


def test_r12_excluded_candidate_not_counted(client, candidates, add_ballots, staff_token, auth):
    a, b, c = candidates
    add_ballots([[a, b, c]] * 3 + [[b, a, c]] + [[c, a, b]])
    db.session.get(Candidate, a).excluded = True
    db.session.commit()

    totals = client.post(f"/count/recount/{DIVISION}",
                         headers=auth(staff_token("officer"))).get_json()["totals"]

    # Alpha's three ballots move to their second preference (Bravo).
    assert str(a) not in totals
    assert totals == {str(b): 4, str(c): 1}


def test_r12_tampered_ballot_stops_recount(client, candidates, add_ballots, staff_token, auth):
    a, b, c = candidates
    add_ballots([[a, b, c], [b, c, a]])
    ballot = Ballot.query.filter_by(division=DIVISION).first()
    blob = bytearray(ballot.blob)
    blob[-1] ^= 0x01
    ballot.blob = bytes(blob)
    db.session.commit()

    resp = client.post(f"/count/recount/{DIVISION}", headers=auth(staff_token("officer")))
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "ballot_integrity"


def test_r12_recount_needs_officer_with_mfa(client, candidates, staff_token, auth):
    url = f"/count/recount/{DIVISION}"
    assert client.post(url).status_code == 401
    assert client.post(url, headers=auth(staff_token("delegate"))).status_code == 403
    assert client.post(url, headers=auth(staff_token("officer", mfa=False))).status_code == 403


def test_r12_unknown_division_404(client, staff_token, auth):
    resp = client.post("/count/recount/Nowhere", headers=auth(staff_token("officer")))
    assert resp.status_code == 404
