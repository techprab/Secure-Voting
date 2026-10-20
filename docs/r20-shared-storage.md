# R-20 shared rate-limit storage

## Configuration
The application already reads RATELIMIT_STORAGE_URI.
To share counters between application processes, configure:

    RATELIMIT_ENABLED=true
    RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0

All application processes must use the same Redis backend and consistent
rate-limit configuration. Redis must be running and reachable.
The memory:// backend remains suitable only for isolated local testing.

Keep Redis restricted to trusted application hosts. Remote deployments
need appropriate network controls, authentication and transport security.
Do not expose an unauthenticated Redis service publicly.

## Automated verification
Install the Python requirements and ensure redis-server is on PATH.

    python -m pytest -v -s --tb=short tests/test_r20_shared_storage.py

Tests start a temporary loopback Redis process with persistence disabled.
They use isolated test databases and stop Redis afterwards.
They do not require a permanent Redis service.

The tests verify:
1. A fresh application process inherits the remaining voter allowance.
2. Two application processes share one allowance during a 40-request burst.

Observed local results:
- 4 shared-storage tests passed.
- Full branch suite: 85 passed.
- Burst: 10 requests reached validation; 30 received HTTP 429.
- Burst elapsed time: 0.45 seconds, including process startup.

## Interpretation and limits
The requests intentionally contain empty ballots. HTTP 400 means the
request reached ballot validation; it does not mean a vote was accepted.

This is a bounded application-level throttling test, not a network load
test or proof that legitimate voting remains available during an attack.
It does not measure production throughput or distributed flood resilience.

The test verifies application-process restart while Redis remains running.
Redis restart, persistence and failover behaviour are not demonstrated.

Upstream traffic protection, successful voting under load and deployment
capacity testing remain outstanding. R-20 is therefore partially met.

If redis-server is absent, these tests are skipped. A skipped run is not
evidence that shared-storage behaviour passed.

## Additional valid-ballot and CI checks
A valid voter on a separate IP successfully submitted a confirmed ballot
while a 40-request burst was scheduled in another application process.
The valid submission created one participation record, one ballot and
one nonce. Each process used an isolated test database, so this does not
demonstrate shared-database contention or network-level load resilience.

The shared-IP test uses three different voters making ten requests each
to exhaust the 30-request IP allowance. A further valid voter on that IP
receives HTTP 429 with no submission records written. This documents a
limitation for legitimate voters sharing a public IP.

The CI workflow installs Redis and runs the shared-storage tests with
R20_REQUIRE_REDIS=1. Missing redis-server fails that required test run
instead of skipping it. GitHub Actions results must be checked separately.
