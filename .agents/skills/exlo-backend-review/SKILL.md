---
name: exlo-backend-review
description: >
  Independently audit and review Exlo's Django and DRF backend.
  Use after implementing features, fixing bugs, changing database
  models, modifying API endpoints, or reviewing security,
  performance, authorization, transactions, and tests. Focuses
  on actual defects, independent business-rule verification,
  regression detection, and production risks. Does not modify
  files unless explicitly requested.
---

# Exlo Backend Independent Review

## 1. Review Independence

You are an independent reviewer.

Do not assume that:

- The implementation is correct.
- Existing tests are correct.
- The developer's assumptions are correct.
- A passing test suite proves business correctness.

Your objective is to find defects that the implementation

and its tests might have missed.

Do not modify files during a review unless explicitly requested.

## 2. Understand Expected Behavior First

Before reviewing implementation:

1. Read the relevant business requirements.
2. Inspect the existing behavior.
3. Identify expected API responses.
4. Identify expected database state.
5. Identify authorization rules.
6. Identify business invariants.
7. Identify valid and invalid state transitions.

Derive expected results independently.

Never treat current implementation behavior as the

definition of correct behavior.

If requirements are ambiguous, report the ambiguity.

## 3. Business Logic Audit

Look for:

- Incorrect calculations.
- Incorrect date handling.
- Incorrect status transitions.
- Missing business validations.
- Invalid state combinations.
- Incorrect ownership checks.
- Incorrect financial calculations.
- Duplicate records.
- Incorrect handling of expired or cancelled resources.
- Incorrect handling of multiple related records.

Check both successful and unsuccessful scenarios.

## 4. Authentication and Authorization Audit

Inspect every relevant endpoint and operation.

Check:

- Authentication requirements.
- Role restrictions.
- Object-level permissions.
- Queryset scoping.
- Tenant isolation.
- Custom actions.
- Nested endpoints.
- Bulk operations.
- Update and delete operations.

Attempt to identify IDOR vulnerabilities.

Consider whether a user from Gym A can:

- Retrieve Gym B's data.
- Modify Gym B's data.
- Delete Gym B's resources.
- Access restricted financial information.
- Perform operations outside their role.

Check whether client-provided IDs can bypass ownership checks.

Report reproducible vulnerabilities.

## 5. Database Integrity Audit

Inspect:

- Unique constraints.
- Check constraints.
- Foreign keys.
- Nullable fields.
- Referential integrity.
- Incorrect on_delete behavior.
- Missing indexes.
- Redundant indexes.
- Invalid relationships.
- Data consistency.

Determine whether important invariants are enforced

only in Python when database constraints are necessary.

Consider what happens under concurrent requests.

## 6. Transaction and Concurrency Audit

Look for:

- Missing transaction.atomic().
- Incorrect transaction boundaries.
- Missing row locks.
- Incorrect select_for_update() usage.
- Race conditions.
- Duplicate payment processing.
- Duplicate attendance records.
- Duplicate locker assignment.
- Lost updates.
- Deadlock risks.
- Incorrect retry behavior.
- External side effects occurring before commit.

Do not assume atomic() alone solves concurrency.

For each finding, explain a realistic execution sequence

that demonstrates the defect.

## 7. ORM and Performance Audit

Inspect actual database access patterns.

Look for:

- N+1 queries.
- Missing select_related().
- Missing prefetch_related().
- Repeated queries.
- Queries inside loops.
- Queries inside serializer methods.
- Expensive aggregations.
- Unnecessary object loading.
- Unbounded querysets.
- Missing pagination.
- Missing or ineffective indexes.

Pay special attention to serializers and related model properties.

Do not report missing eager loading when the relationship

is not actually accessed.

Avoid speculative performance findings.

Where possible, use query inspection and query-count tests

to support findings.

## 8. Behavioral Test Audit

Review whether tests verify actual business behavior.

Look for tests that:

- Derive expected values from implementation.
- Reproduce incorrect business logic.
- Assert only successful HTTP status codes.
- Verify method calls instead of outcomes.
- Mock the functionality being tested.
- Ignore persisted database state.
- Miss negative authorization scenarios.
- Miss boundary conditions.
- Depend on test execution order.
- Are too weak to detect the reported defect.

For important endpoints, ask:

Would these tests fail if the implementation

returned an incorrect result?

Would these tests detect an authorization bypass?

Would these tests detect duplicate processing?

Would these tests detect an incorrect database state?

If the answer is no, identify the missing scenario.

## 9. Regression Verification

For every reported bug:

1. Determine whether a regression test exists.
2. Inspect whether its expected result is independently correct.
3. Determine whether the test would fail against the original buggy behavior.
4. Verify that it passes against the corrected implementation.
5. Check whether valid behavior is also protected.
6. Identify missing related regression scenarios.

Do not accept a regression test simply because it passes.

A meaningful regression test must be capable of detecting

the defect it claims to prevent.

When practical, use a separate Git worktree to test

against the original implementation.

## 10. Security and External Integrations

Inspect:

- Payment callbacks.
- Payment verification.
- Device authentication.
- NFC events.
- WebSocket authorization.
- Token validation.
- Sensitive data exposure.
- Rate limiting.
- Replay protection.
- Duplicate event handling.
- External service failure handling.

Treat external systems and hardware as untrusted.

## 11. Review Severity

Classify findings:

### Critical

Direct financial corruption, severe data exposure,

authentication bypass, or major cross-tenant compromise.

### High

Authorization bypass, serious business-rule violations,

race conditions, or data integrity failures.

### Medium

Incorrect behavior in specific scenarios, significant

performance problems, or missing important validation.

### Low

Minor correctness, maintainability, or non-critical

performance concerns.

Do not exaggerate severity.

## 12. Required Review Output

Report findings in this order:

### Findings

For every finding include:

- Severity.
- File and location.
- Problem.
- Why it is incorrect.
- Realistic reproduction scenario.
- Expected behavior.
- Actual behavior.
- Recommended minimal fix.

### Test Quality

Report missing behavioral and regression tests.

### Performance

Report concrete query and performance problems.

### Security

Report authorization, authentication and tenant-isolation risks.

### Overall Assessment

Summarize:

- Confirmed bugs.
- Potential risks requiring verification.
- Missing tests.
- Areas that passed review.

If no issues are found, say so without inventing problems.

Do not modify code during review.

Do not claim tests were executed unless they were.

Do not claim a vulnerability is exploitable without evidence.

## Full Test Suite and Edge Case Audit

When requested to audit the entire backend test suite, perform a systematic, independent review of all Django applications and their tests.

### 1. Test Inventory

- Discover all existing test files, classes, and test methods.
- Identify the application and functionality covered by each test.
- Identify API endpoints, services, models, permissions, and business operations without meaningful test coverage.
- Detect duplicate, redundant, obsolete, or incorrectly named tests.
- Do not assume passing tests are correct.

### 2. Test Correctness

For every test, evaluate:

- Whether the expected result matches actual business requirements.
- Whether assertions can detect incorrect behavior.
- Whether the test verifies persisted database state when appropriate.
- Whether mocked dependencies hide actual defects.
- Whether fixtures represent realistic conditions.
- Whether the test could pass despite broken functionality.
- Whether the test depends on execution order or shared state.
- Whether the test incorrectly treats implementation behavior as expected behavior.

### 3. Missing Edge Cases

Identify missing tests for:

- Null, empty, missing, malformed, and invalid inputs.
- Minimum and maximum boundaries.
- Date, time, timezone, and expiration boundaries.
- Invalid business state transitions.
- Duplicate requests and idempotency.
- Concurrent operations and race conditions.
- Transaction failures and rollback behavior.
- Database uniqueness and integrity violations.
- Authentication and authorization failures.
- Cross-tenant and cross-gym access.
- Expired, revoked, disabled, and deleted resources.
- External service failures and timeouts.
- Payment and wallet consistency.
- Device and NFC event duplication.
- Redis and cache invalidation.
- Pagination, filtering, and ordering.
- Unexpected relationships and multiple related records.

Only report scenarios relevant to the actual functionality.

### 4. Find Bugs Beyond Existing Tests

Do not restrict the review to test code.

For each important operation:

1. Inspect the production implementation.
2. Determine the intended business behavior independently.
3. Identify possible incorrect execution paths.
4. Check whether existing tests detect those defects.
5. Identify untested conditions that could cause incorrect behavior.
6. Explain realistic reproduction scenarios.
7. Distinguish confirmed defects from suspected risks.

Never invent defects merely to produce findings.

### 5. Test Execution and Development Infrastructure

- Execute Django unit, integration, functional, and regression tests only when the effective `APP_ENV=development`.
- `development` uses `docker-compose.dev.yml`; `apiLoadTest` and `production` use `docker-compose.prod.yml`.
- Use the existing developer-managed PostgreSQL and Redis services; never create, start, stop, restart, or remove Docker containers, images, Compose projects, or volumes.
- Inspect the effective environment, connection targets, and test settings before running tests. Never switch environments just to bypass these restrictions.
- Normal development test execution is pre-authorized. Do not request approval simply because tests use PostgreSQL, Redis, or `cache.clear()`.
- Django may create, migrate, and remove its own dedicated PostgreSQL test database; it must never use or erase the persistent development database.
- Redis development **cache** entries are disposable. Django tests may read, write, expire, invalidate, or clear development-only cache data, including calls to `cache.clear()`. A test clearing disposable development cache is not a reason to stop an audit.
- Check the Redis backend's exact clear behavior. If the selected Redis logical database also contains Celery broker data, durable records, non-test sessions, or data belonging to another environment, do not flush or clear that unrelated data. Where supported, configure process-local test cache isolation using the existing Redis service and an unused logical database or a backend-enforced key namespace; a prefix alone is not sufficient unless `clear()` is confirmed namespace-scoped.
- Never use `FLUSHALL`, purge Celery queues, or clear a Redis database shared with `apiLoadTest` or `production`.
- A read-only code review permits ordinary temporary test-database and disposable development-cache mutations. It does not permit editing repository files, dependency packages, infrastructure, or persistent application data.
- If a safe development target cannot be verified, execute all safe test selections and report only the genuinely blocked tests with a specific reason. Do not silently skip tests.
- Run the full suite when feasible, then targeted tests to investigate failures. Record passes, failures, errors, skips, and blockers; do not claim unexecuted tests passed.

### 6. Coverage and Test Gaps

- Map existing tests to business operations and API endpoints.
- Identify missing positive and negative scenarios.
- Prioritize uncovered financial, authentication, authorization, tenant-isolation, and concurrency behavior.
- Use coverage tooling if already available.
- Do not introduce dependencies solely for coverage without authorization.
- Distinguish line coverage from meaningful behavioral coverage.

### 7. Read-Only Review

- Do not modify implementation files, tests, dependencies, project configuration, or Docker infrastructure.
- Do not add, delete, or rewrite tests or change assertions to make tests pass.
- Running approved tests is allowed even though tests create temporary PostgreSQL test records and mutate disposable development Redis cache entries.
- Do not modify persistent application databases or unrelated Redis data.
- Report findings and recommended fixes only; use `exlo-django-engineering` separately when the developer requests fixes.

### 8. Required Audit Report

Organize the final report by Django application.

For each application, report:

- Existing test coverage and inspected functionality.
- Confirmed bugs with file and line references.
- Missing edge cases.
- Weak or misleading tests.
- Missing authorization and security tests.
- Database integrity and concurrency risks.
- Recommended additional regression tests.
- Severity and priority.

Finish with a project-wide summary containing:

- Total tests discovered and executed.
- Passed, failed, errored, and skipped tests.
- Confirmed bugs.
- Potential defects requiring verification.
- Missing critical test scenarios.
- Highest-risk applications and functionality.
- Recommended fixes in priority order.

Never present an unverified suspicion as a confirmed bug.
