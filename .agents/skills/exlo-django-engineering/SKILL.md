---
name: exlo-django-engineering
description: >
  Implement, debug, extend, and optimize Exlo's Django and
  Django REST Framework backend. Use when creating or modifying
  models, serializers, views, API endpoints, permissions,
  authentication, database queries, transactions, business logic,
  or backend tests. Enforces independent behavioral testing,
  tenant isolation, database integrity, concurrency safety,
  and production-quality implementation.
---

# Exlo Django Engineering

## 1. Mandatory Workflow

For every backend task, follow this workflow:

### Phase 1: Understand

Before changing code:

1. Understand the requested behavior.
2. Inspect the relevant implementation.
3. Identify related models and relationships.
4. Inspect serializers, views, permissions and querysets.
5. Inspect existing tests.
6. Identify dependencies and side effects.
7. Identify security and performance implications.

Do not start coding before understanding the existing implementation.

### Phase 2: Define Expected Behavior

Establish what the system must actually do.

Identify:

- Valid inputs.
- Invalid inputs.
- Expected responses.
- Expected database state.
- Allowed state transitions.
- Forbidden operations.
- User roles and permissions.
- Tenant boundaries.
- Edge cases.

Expected behavior must come from the business requirements.

Existing code is evidence of current behavior, not proof of correct behavior.

If requirements are ambiguous and materially affect implementation, ask for clarification.

### Phase 3: Design the Smallest Correct Solution

Choose one straightforward implementation.

Evaluate:

- Existing Django capabilities.
- Existing project conventions.
- Database integrity.
- Query efficiency.
- Transactions.
- Concurrency.
- Security.
- Maintainability.

Avoid unnecessary abstractions, dependencies and refactoring.

### Phase 4: Implement

Make focused changes.

Preserve existing behavior unless the requirements explicitly change it.

Do not modify unrelated applications or files.

### Phase 5: Test

Write tests based on independently established expected behavior.

Execute the relevant tests and inspect the results. Follow the development infrastructure rules below: do not skip tests because they use the existing Redis cache or Django's managed PostgreSQL test database.

### Phase 6: Review

Inspect the final implementation and Git diff.

Check for:

- Incorrect business logic.
- Missing authorization.
- N+1 queries.
- Unnecessary database operations.
- Missing constraints.
- Race conditions.
- Unhandled errors.
- Missing regression tests.

---

## 2. Django ORM and Query Optimization

Query optimization is part of implementation, not an optional final step.

For every endpoint that retrieves related objects:

1. Identify which relationships are accessed.
2. Inspect serializer fields and nested serializers.
3. Inspect model properties and methods.
4. Identify queries executed inside loops.
5. Determine which relationships need eager loading.
6. Inspect the actual query behavior.

Use:

### select_related()

For appropriate single-valued relationships:

- ForeignKey.
- OneToOneField.

### prefetch_related()

For appropriate multi-valued relationships:

- ManyToManyField.
- Reverse ForeignKey.
- Other relationships requiring separate queries.

### annotate() and aggregate()

When database-level calculations are more efficient and appropriate than loading objects and calculating everything in Python.

### exists()

When only the existence of a record is required.

### Other considerations

- Avoid unnecessary count queries.
- Avoid evaluating querysets repeatedly.
- Avoid loading large unnecessary datasets.
- Avoid unbounded related-object retrieval.
- Use pagination appropriately.
- Inspect indexes for frequently filtered and ordered fields.
- Consider query plans for expensive queries.

Do not add eager loading blindly.

Do not add indexes without understanding the query pattern and write overhead.

### Serializer-specific checks

Pay particular attention to:

- SerializerMethodField.
- Nested serializers.
- Model properties.
- Related managers.
- Custom representation methods.

These can introduce hidden database queries.

A queryset that looks optimized at the view level can still produce N+1 queries during serialization.

For important endpoints, use query-count tests or query inspection to verify behavior.

---

## 3. Business Logic and Domain Correctness

Implement the actual business rules.

Do not assume that existing code correctly represents those rules.

Before implementation, identify invariants.

Examples:

### Memberships

- Which memberships can be active?
- How is expiration calculated?
- Can a user have multiple active memberships?
- What happens when a membership is renewed?
- Can an expired membership be activated?
- What happens when two renewals happen simultaneously?

### Attendance

- What qualifies as a valid check-in?
- Can duplicate check-ins happen?
- What happens when a subscription expires?
- Can an unauthorized device register attendance?

### Payments

- What constitutes a successful payment?
- Can a callback be processed more than once?
- When should wallet balances change?
- How are failed transactions handled?
- What prevents inconsistent financial records?

### Lockers

- Can one user have multiple lockers?
- Can two users receive the same locker?
- What happens during simultaneous assignment?
- Can an assigned locker be deactivated?

These are examples of questions to investigate, not assumptions about current Exlo behavior.

Preserve the actual established business requirements.

---

## 4. Transactions and Concurrency

Evaluate whether an operation requires atomic execution.

Use transaction.atomic() when multiple database modifications form one logical operation.

Consider:

- Atomicity.
- Row-level locking.
- select_for_update().
- Unique constraints.
- Check constraints.
- Race conditions.
- Idempotency.
- Deadlocks.
- Lock ordering.
- Transaction boundaries.

Important rules:

1. atomic() alone does not prevent all concurrency problems.
2. Validate and enforce critical invariants at the database level where appropriate.
3. Lock rows when concurrent operations could violate invariants.
4. Keep transactions short.
5. Do not make external network requests inside long-running transactions.
6. Use transaction.on_commit() when external side effects must wait for a successful commit.
7. Ensure retryable operations do not create duplicate records or financial effects.

Do not introduce locking without a concrete concurrency problem.

---

## 5. Authentication and Authorization

For every endpoint, inspect authentication and authorization separately.

Determine:

- Which authentication classes apply?
- Which roles can perform the operation?
- Which gym owns the requested resource?
- Can the user access this object?
- Can the user modify it?
- Can another tenant's information be exposed?

Never trust client-provided gym IDs, owner IDs or object ownership.

Use appropriately scoped querysets.

Check:

- List endpoints.
- Detail endpoints.
- Create endpoints.
- Update endpoints.
- Delete endpoints.
- Custom ViewSet actions.
- Nested resources.
- Bulk operations.

Do not assume that protecting a detail endpoint automatically protects list or custom endpoints.

Test positive and negative authorization scenarios.

---

## 6. Independent Behavioral Testing

This is one of the most important requirements.

Tests must establish whether the application behaves correctly according to its requirements.

They must not merely establish whether the code behaves consistently with itself.

### 6.1 Establish expected results independently

Before writing assertions:

1. Understand the business requirement.
2. Identify the expected outcome.
3. Calculate expected values independently.
4. Identify expected database changes.
5. Identify failure conditions.
6. Identify permission boundaries.

Never use the current implementation's output as the source of truth for expected values.

### 6.2 Prefer externally observable behavior

For API functionality, test:

- HTTP response status.
- Response data.
- Response structure.
- Database state.
- Side effects.
- Permission enforcement.

Unit tests are useful for isolated logic, but they do not replace endpoint-level verification.

### 6.3 Test realistic scenarios

For each important operation, consider:

- Normal successful behavior.
- Invalid input.
- Missing resources.
- Unauthorized users.
- Cross-gym access.
- Boundary conditions.
- Invalid state transitions.
- Duplicate operations.
- Database failures.
- Concurrent requests.

### 6.4 Avoid implementation-coupled tests

Do not:

- Copy serializer logic into expected assertions.
- Calculate expected results using the same implementation being tested.
- Mock the functionality whose real behavior needs verification.
- Assert only that an internal method was called.
- Assert that a response is correct merely because it matches the current implementation.

Use independent fixtures and explicitly defined expected results.

### 6.5 Test the database state

When an endpoint changes data, verify the persisted result.

Examples:

- Was the correct membership created?
- Was the correct subscription activated?
- Was the wallet balance changed exactly once?
- Was attendance recorded?
- Was the locker assigned to the correct user?
- Were related records updated consistently?

An HTTP 200 response alone does not establish correctness.

---

## 7. Mandatory Bug Regression Workflow

Whenever a bug is discovered, use this exact workflow.

### Step 1: Understand the defect

Identify:

- Expected behavior.
- Actual behavior.
- Root cause.
- Conditions required to reproduce it.

### Step 2: Write a regression test first

Write a test that verifies the correct business behavior.

The test must be capable of failing against the buggy implementation.

Do not modify the implementation yet.

### Step 3: Verify the original bug

Run the test against the original buggy code.

Confirm:

- The test actually executes.
- It fails.
- The failure demonstrates the reported bug.
- It does not fail because of incorrect fixtures or setup.

If practical, preserve the original code in a Git worktree for this verification.

### Step 4: Fix the implementation

Fix the underlying defect.

Do not weaken the test.

Do not change the expected result to accommodate the implementation.

### Step 5: Verify the fix

Run the exact same regression test.

It must now pass.

### Step 6: Verify related behavior

Add complementary tests when necessary.

Check that the fix does not break valid behavior.

### Step 7: Preserve the regression test

The test must remain in the permanent test suite.

Never leave an intentionally failing test in the final implementation.

### Important

A single regression test can provide both reproduction and permanent protection.

Do not create duplicate tests merely to satisfy a requirement for two tests.

What matters is proving:

1. The test detects the original bug.
2. The test passes after the fix.
3. The test continues protecting the application against recurrence.

For critical security and financial defects, consider mutation testing or an explicit test against the original vulnerable behavior.

---

## 8. Test Quality

Tests should be meaningful and capable of detecting real defects.

Prefer:

- Explicit expected values.
- Realistic database records.
- Independent test data.
- API-level behavior verification.
- Database state verification.
- Positive and negative cases.
- Boundary tests.

Avoid:

- Excessive mocking.
- Assertions that verify only implementation details.
- Tests that duplicate the same scenario.
- Assertions derived from the code under test.
- Arbitrary expected values.
- Weak assertions such as checking only that a response is successful.

Use the existing project's test framework and conventions.

Do not introduce a new testing dependency without a concrete need.

---

## 9. External Services and Hardware

When implementing functionality involving external systems, consider their trust and failure boundaries.

For payments:

- Duplicate callbacks.
- Verification.
- Idempotency.
- Atomic financial updates.
- Failed external requests.

For devices:

- Invalid tokens.
- Inactive devices.
- Unauthorized gym access.
- Duplicate events.
- Network retries.
- Reconnection behavior.
- Untrusted device input.

For WebSockets:

- Connection authentication.
- Authorization.
- Tenant isolation.
- Message validation.
- Disconnect behavior.

Never trust an external event merely because it reached the backend.

---

## Development Testing and Docker Infrastructure

- Inspect the effective `APP_ENV` before running environment-dependent commands. Run Django tests only with `APP_ENV=development` and the existing `docker-compose.dev.yml` infrastructure.
- `apiLoadTest` uses `docker-compose.prod.yml` for explicitly requested API performance benchmarks, not Django test suites. Never run automated tests or benchmarks under `production`.
- Reuse developer-managed PostgreSQL and Redis. Never provision, start, stop, recreate, or remove infrastructure containers, images, or volumes. If required services are down, ask the developer to start them.
- Django's normal dedicated PostgreSQL test database may be created, migrated, and destroyed. Never perform test operations against the persistent development database.
- Normal development cache reads, writes, invalidations, and `cache.clear()` are allowed without additional permission when the target is verified as development-only **cache** data. Treat these cache entries as disposable; do not skip tests just because they clear cache entries.
- Inspect how the Redis cache backend implements `clear()`. Do not flush a logical Redis database containing Celery broker data, persistent state, data from `apiLoadTest` or `production`, or other unrelated data. Prefer process-scoped test cache isolation using the existing Redis server if required, and verify isolation before clearing.
- Never execute `FLUSHALL`, purge queues, or delete persistent Redis data as a test workaround.
- If a dependency is unavailable or safe isolation cannot be established, execute unaffected tests and report a concrete blocker rather than silently skipping the suite.
- Do not switch `APP_ENV`, change Compose configurations, or install replacement infrastructure to make prohibited tests run.

## 10. Final Verification Checklist

Before declaring implementation complete:

- [ ] Business requirements satisfied.
- [ ] Existing conventions preserved.
- [ ] No unrelated refactoring.
- [ ] Input validation implemented.
- [ ] Authentication checked.
- [ ] Authorization checked.
- [ ] Tenant isolation checked.
- [ ] Database integrity considered.
- [ ] Transactions considered.
- [ ] Concurrency considered.
- [ ] N+1 risks inspected.
- [ ] Unnecessary queries avoided.
- [ ] Behavioral tests written.
- [ ] Regression tests verified where applicable.
- [ ] Relevant tests executed.
- [ ] Git diff inspected.
- [ ] Remaining limitations documented.

Never report unexecuted tests as passing.

Never claim an optimization without evidence.

Never claim a bug is fixed without verification.
