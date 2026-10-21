# Security requirements (Part One)

21 requirements merged from the members' Assignment 1 work. One GitHub issue per requirement.

> Short titles here are working labels. The report's requirements table uses each member's original Assignment 1 wording.

| ID | Requirement | Priority | Complexity | Slice | Source (A1) |
| --- | --- | --- | --- | --- | --- |
| R-01 | One vote-casting transaction per voter | H | M | A | J SR-01 + P SR-08 + Ri R2 |
| R-02 | Seal ballots only in sets of 20 or more | H | H | B | J SR-02 + Dv SR2 + Dv SR12 |
| R-03 | Voter session expires after 15 min idle or at window close | M | M | A | J SR-04 + Ri R1 + Ri R12 + Dv SR1 |
| R-04 | Replayed submission rejected | H | M | A | J SR-13 |
| R-05 | Privileged actions attributed to a named identity | M | M | C | J SR-05 + D R-05 + P SR-12 + J SR-06 + Ri R10 + Dv SR4 + Dv SR6 |
| R-06 | Ballot served only from the last approved candidate set | H | H | B | J SR-08 |
| R-07 | Explicit confirmation before commit; participation-only code | H | M | B | J SR-07 + D R-04 + P SR-06 + Dv SR14 |
| R-08 | Auditor verifies ballot set without re-linking | H | H | B | J SR-09 + D R-03 + P SR-01 + J SR-11 + Ri R5 + Dv SR9 |
| R-09 | Selections unreadable in transit | H | M | D | J SR-10 + D R-01 + P SR-03 + Ri R3 |
| R-10 | Per-ballot hash chain verified before tally | H | M | D | D R-02 + P SR-05 + Ri R6 + Ri R7 + Dv SR3 |
| R-11 | MFA for staff who can view or release results | H | M | C | D R-06 + Ri R11 |
| R-12 | Recount re-processes source ballots, not a cached tally | H | H | E | D R-07 + Ri R14 |
| R-13 | Overseas access only from approved mission terminals; fails closed | M | H | A | P SR-09 + D R-08 + Ri R13 |
| R-14 | Ballots encrypted at rest | M | H | D | D R-11 + P SR-03 + Ri R4 + Dv SR7 |
| R-15 | No known-vulnerable dependency | L | L | D | D R-14 + Dv SR13 |
| R-17 | Tamper-evident audit log | M | H | C | D R-05/R-12 + P SR-12 + J SR-12 + Ri R15 + Dv SR4 |
| R-18 | Staff least privilege with 90-day recertification | M | M | C | P SR-04 + Dv SR10 |
| R-19 | Two independent tallies must agree before publication | H | H | E | P SR-07 |
| R-20 | Submission survives request floods | H | H | A | P SR-11 + Ri R9 + Dv SR5 |
| R-21 | Candidate exclusion needs two distinct delegates within 15 min | H | M | E | P SR-13 |
| R-22 | Result release signed; public key published | H | M | E | P SR-14 |

**Complexity:** High 9 · Medium 11 · Low 1 (brief: at least 8 High and 8 Medium).
**Source key:** J = Jaewook, D = Daksh, P = Prabh, Ri = Riya, Dv = Dev (A1 requirement IDs). Riya R8 (40,000 terminals) was not carried over: capacity cannot be demonstrated in the prototype. Dev SR8 (in-person resets), SR11 (backups) and SR15 (penetration testing) were not carried over: they are operational procedures, not prototype features. Voter MFA from Dev SR1 is not implemented; MFA applies to staff (R-11).
**Slices:** A Voter access · B Ballot & anonymity · C Staff & audit · D Crypto & pipeline · E Count & publish.
