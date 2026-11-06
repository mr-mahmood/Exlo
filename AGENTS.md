# Exlo Backend Engineering Rules

## 1. Project Context

Exlo is a multi-tenant gym management SaaS.

It is not a fitness or workout application.

Main technologies:

- Python
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Django Channels
- Celery
- Next.js frontend
- Docker

Main application domains include:

- Authentication and users
- Gyms and gym management
- Memberships and subscriptions
- Attendance and visits
- Payments and financial transactions
- Coaches and gym staff
- Devices and NFC cards
- Electronic lockers

Understand the existing implementation before making assumptions.

## 2. Core Engineering Principles

Follow:

- KISS
- YAGNI
- DRY
- Separation of concerns
- Explicit business rules
- Database-level integrity

Rules:

- Prefer Django's built-in functionality.
- Avoid unnecessary abstractions.
- Avoid unnecessary dependencies.
- Do not introduce design patterns without a real requirement.
- Do not duplicate existing functionality.
- Do not refactor unrelated code.
- Prefer small, targeted changes.
- Preserve existing project conventions.

Do not optimize code at the expense of correctness.

## 3. Project Inspection

Before modifying code:

1. Inspect the relevant application.
2. Read related models and relationships.
3. Inspect serializers, views, permissions and querysets.
4. Inspect existing services and utility functions.
5. Inspect related tests.
6. Understand the business requirements.
7. Identify possible side effects.

Never invent project models, fields, functions, or architectural conventions.

If something is unclear, investigate the repository before asking questions.

## 4. Business Logic

Business requirements are the source of truth.

- Implement actual business behavior.
- Identify business invariants.
- Validate state transitions.
- Handle boundary conditions.
- Handle invalid and unexpected states.
- Preserve existing business rules unless explicitly instructed otherwise.

Never assume that existing implementation behavior is necessarily correct.

Never derive expected test results from potentially incorrect implementation.

## 5. Django ORM and Database Performance

Prevent unnecessary database queries.

Always consider:

- N+1 queries.
- select_related().
- prefetch_related().
- annotate().
- aggregate().
- exists().
- only() and defer() where appropriate.
- Queryset evaluation.
- Pagination.
- Database indexes.
- Unnecessary object creation.
- Unnecessary database writes.

Rules:

- Inspect relationship access in serializers and nested serializers.
- Inspect properties and model methods that execute queries.
- Inspect loops that access related objects.
- Avoid repeated queries for the same data.
- Avoid retrieving objects that are not needed.
- Use database aggregations when appropriate.
- Avoid premature optimization.

Do not blindly add select_related(), prefetch_related(), or indexes.

Choose optimizations based on actual query patterns.

For important endpoints, consider realistic query-count tests.

## 6. Database Integrity

Use PostgreSQL constraints when database-level guarantees are necessary.

Consider:

- UniqueConstraint.
- CheckConstraint.
- ForeignKey behavior.
- Nullability.
- Referential integrity.
- Indexes.
- Conditional uniqueness.
- Concurrent writes.

Application validation alone is not sufficient for critical database invariants.

New UUID identifiers must follow the project's existing UUID7 conventions.

Do not change existing identifier strategies without an explicit requirement.

## 7. Transactions and Concurrency

Use transaction.atomic() when multiple database operations must succeed or fail together.

Evaluate:

- Transaction boundaries.
- Concurrent requests.
- Race conditions.
- select_for_update().
- Database constraints.
- Duplicate requests.
- Idempotency.
- Deadlocks.
- Lock ordering.
- Transaction isolation.

Important:

- atomic() does not automatically prevent race conditions.
- Use database-level guarantees where appropriate.
- Lock the correct rows when necessary.
- Keep transactions as short as possible.
- Never hold a database transaction open while waiting for an external network request.
- Handle external side effects carefully.
- Consider transaction.on_commit() when an operation must happen after a successful commit.

For payment and financial operations, protect against duplicate processing and inconsistent ledger state.

For hardware and device events, consider retries, duplicate messages, reconnections and untrusted input.

## 8. Authentication and Authorization

Always distinguish authentication from authorization.

For every endpoint, establish:

1. Who can authenticate?
2. Which roles can access the endpoint?
3. Which gym owns the resource?
4. Does the user have access to this specific object?
5. Can the operation modify another tenant's data?

Rules:

- Never trust client-provided ownership.
- Never trust client-provided gym IDs without validating access.
- Scope querysets appropriately.
- Enforce object-level authorization where necessary.
- Protect custom actions and nested endpoints.
- Protect sensitive operations.
- Do not assume authentication alone provides authorization.
- Avoid exposing sensitive data through serializers.

Test both permitted and denied operations.

## 9. API and DRF Standards

Follow existing project conventions.

Consider:

- Serializer validation.
- View and ViewSet responsibilities.
- Permissions.
- Authentication classes.
- Throttling.
- Pagination.
- Filtering.
- Ordering.
- HTTP status codes.
- Consistent response structures.
- Error handling.
- Backward compatibility.

Validate all untrusted input.

Avoid putting complex business logic in serializers or views when the existing architecture provides a better location.

Do not introduce unnecessary service layers.

## 10. Security

Treat all client input as untrusted.

Consider:

- IDOR vulnerabilities.
- Cross-tenant access.
- Privilege escalation.
- Authentication bypass.
- Insecure object access.
- Sensitive information exposure.
- Replay attacks.
- Duplicate requests.
- Rate limiting.
- Device authentication.
- Payment verification.
- Secret handling.

Never expose secrets, tokens, or credentials.

Never trust device-provided identifiers without validating device authorization and ownership.

## 11. Testing Standards

Tests must verify actual expected behavior.

Prefer testing externally observable behavior through the API when appropriate.

Test:

- Successful operations.
- Invalid input.
- Missing resources.
- Permission failures.
- Authentication failures.
- Business-rule violations.
- Database state changes.
- Boundary conditions.
- Duplicate operations.
- Tenant isolation.
- Concurrency-sensitive behavior.

Never:

- Write tests that simply reproduce implementation logic.
- Copy potentially incorrect implementation results into expected values.
- Change correct expectations to make tests pass.
- Remove tests to hide regressions.
- Mock the exact behavior that the test is supposed to verify.

Expected results must be derived independently from business requirements.

## 12. Bug and Regression Protocol

Whenever a bug is discovered:

1. Understand the intended behavior.
2. Reproduce the bug.
3. Write a regression test before fixing the implementation.
4. Run the test against the original buggy implementation.
5. Confirm that it fails for the expected reason.
6. Fix the underlying implementation.
7. Run the same test again.
8. Confirm that it passes.
9. Add complementary tests for valid behavior that could be affected.
10. Keep the regression test permanently.

For important bugs, verify that the test actually detects the defect.

When practical, use a temporary Git worktree or isolated checkout to verify the test against the original implementation.

Never leave intentionally failing tests in the final test suite.

## 13. Code Quality

- Use clear names.
- Keep functions focused.
- Avoid unnecessary nesting.
- Avoid unnecessary database access.
- Avoid duplicated business rules.
- Handle exceptions intentionally.
- Follow existing formatting and conventions.
- Keep changes minimal.

Do not sacrifice readability for shorter code.

## 14. Final Verification

Before completing a task:

1. Inspect the Git diff.
2. Check for unrelated changes.
3. Run relevant tests.
4. Check migrations if models changed.
5. Verify database behavior.
6. Review authorization.
7. Review query patterns.
8. Identify remaining risks.

Never claim tests passed without executing them.

Never claim performance improvements without evidence.

Never claim security guarantees without verifying the implementation.

Be concise, technically precise and honest.

## Tenant Isolation

Exlo has both user-level and gym-level resources.

Do not assume every resource belongs directly to a gym.

User-level resources include:

- Users
- Wallets
- Sessions
- NFC cards
- others that might added in future

Gym-level access is determined by gym relationships

and UserGymRole records. and the exist of gym membership for athlete in the gym

Always inspect the actual resource ownership model.

Gym access must be validated using the authenticated

user's actual role and permissions.

Never assume URL gym_id establishes authorization.

## API Conventions

Follow existing API conventions.

- Use the shared response envelope:

  {success, data, error_code}

- Use existing APIError definitions.
- Follow existing exception handling.
- Respect existing pagination conventions.
- Ordinary DRF permission denials currently return HTTP 404.
- Follow existing PUT and partial-update behavior.

Do not introduce alternative response structures

without an explicit requirement.

## Authentication Conventions

Preserve the existing custom authentication architecture.

- JWT claim key_1 identifies the user.
- JWT claim key_2 identifies the persisted session.
- Cookies are the default transport.
- Session validity and revocation must be respected.

When changing authentication, test:

- Cookie authentication.
- Bearer authentication.
- Invalid tokens.
- Expired tokens.
- Revoked sessions.
- Refresh rotation.
- Inactive users.
- CSRF behavior for cookie-authenticated requests.

Do not replace custom authentication with standard

SimpleJWT behavior without an explicit requirement.

## Caching

Inspect existing cache behavior before modifying endpoints.

Consider:

- Versioned cache namespaces.
- Cache invalidation.
- Cache key correctness.
- Query parameter variations.
- Time-dependent values.
- Concurrent cache rebuilds.
- Redis locks.

When database changes affect cached representations,

ensure invalidation occurs after successful transaction commit.

## Python Environment and Dependency Safety

- Never modify Python standard library files.
- Never modify files inside site-packages.
- Never modify third-party dependency source code.
- Never modify files inside .venv or other virtual environments.
- Do not upgrade or reinstall dependencies unless explicitly required.
- When a third-party dependency causes an error, diagnose the problem

  without directly patching the installed package.

- When dependency changes are necessary, update the project's dependency

  specification and use the existing package-management workflow.

## Docker Infrastructure and Environment Rules

Exlo uses externally managed Docker infrastructure for PostgreSQL, Redis, and other configured services.

The `APP_ENV` variable determines the runtime environment and Docker Compose configuration.

\| APP_ENV | Docker Compose file | Purpose |

\|---|---|---|

\| `development` | `docker-compose.dev.yml` | Development, unit tests, integration tests |

\| `apiLoadTest` | `docker-compose.prod.yml` | API load testing, stress testing, and performance benchmarking |

\| `production` | `docker-compose.prod.yml` | Live production operations |

### Infrastructure Rules

- Always inspect `APP_ENV` before performing environment-dependent operations.
- Use the corresponding Docker Compose file to identify existing infrastructure services.
- PostgreSQL, Redis, and other infrastructure services are managed by the developer, not by the coding agent.
- Before executing commands requiring infrastructure, verify that the required services are running and reachable.
- Reuse the existing services and configured connections.
- Never create additional PostgreSQL or Redis containers, images, volumes, or Docker Compose projects.
- Never automatically start, stop, restart, recreate, or remove infrastructure containers.
- Never execute `docker compose up`, `down`, `restart`, `rm`, or equivalent lifecycle commands without explicit permission.
- Never delete Docker volumes or persistent infrastructure data.
- Do not modify Docker Compose configurations merely to make commands succeed.
- If a required service is unavailable, tell the developer which service must be started and ask them to start it.
- Never provision replacement infrastructure automatically.
- Never substitute SQLite, mock databases, or temporary containers for configured infrastructure unless explicitly requested.
- If environment configuration is unclear, inspect existing settings rather than making assumptions.

### Development Environment (`APP_ENV=development`)

This is the only environment where automated Django tests may run.

Allowed operations:

- Django unit tests.
- Django integration tests.
- API functional tests using Django's test runner.
- Regression tests.
- Database migration checks.
- Django-managed test database creation and cleanup.
- Development debugging and verification.

Rules:

- Always verify `APP_ENV=development` before running Django tests.
- Use the existing development PostgreSQL and Redis infrastructure.
- Use Django's standard isolated test database.
- Never run tests against the actual development database.
- Never delete or reset the persistent development database.
- Do not create separate Docker infrastructure for testing.
- Use the existing Python virtual environment and project dependencies.

### Development Test Infrastructure Permissions

The developer authorizes normal testing against the **existing** development PostgreSQL and Redis services. This authorization applies to both engineering work and read-only backend audits.

- Do not request separate permission to run Django tests or to use the existing development PostgreSQL and Redis connections.
- PostgreSQL: Django may create, migrate, reuse, and destroy its own dedicated test databases (for example `test_exlo`) using its normal test runner. Never run tests against or truncate the persistent development database.
- Redis: development-only **cache entries are disposable**. Tests may read, write, expire, invalidate, and clear that cache, including `cache.clear()`. Do not stop or skip tests solely because the cache may be cleared.
- Before executing a cache-wide clear, confirm what the configured Redis backend actually deletes. Clearing development cache entries is authorized; deleting Celery broker queues, durable data, other environments' keys, or unrelated data is not.
- If the configured Redis logical database mixes disposable cache with protected data, use safe test cache isolation on the **existing Redis service** when the project already supports a process-scoped override. Use an unused logical database or a verified namespace-scoped backend; a key prefix alone does not guarantee `cache.clear()` is safe.
- Never run Redis `FLUSHALL`, purge Celery queues, or destroy Redis volumes as part of testing.
- A read-only code review still permits normal temporary test-database writes and development-only cache operations. It must not modify source files or persistent application data.
- If services are available and test targets are verified, proceed with the requested tests without waiting for additional approval. If a specific operation can delete protected data, do not perform that operation; run other safe tests and report precisely what remains blocked.

### API Load Testing Environment (`APP_ENV=apiLoadTest`)

This environment is exclusively for API performance benchmarking under production-like conditions.

Performance metrics include:

- Requests per second (RPS).
- Throughput.
- Response time and average latency.
- P50, P95, and P99 latency.
- API error rate.
- Concurrent users and requests.
- Failure rates under load.
- Database and Redis performance.
- Resource utilization.
- Stress and capacity testing.

Rules:

- Never run Django unit, integration, functional, or regression test suites in this environment.
- Never execute `python manage.py test` or equivalent automated test commands.
- Run API load tests only when explicitly requested by the developer.
- Verify `APP_ENV=apiLoadTest` before executing benchmarks.
- Use the existing production-like infrastructure defined in `docker-compose.prod.yml`.
- Never create, start, stop, or recreate infrastructure containers automatically.
- Never run benchmarks against production endpoints or databases.
- Use only approved benchmark targets and test data.
- Do not reset, truncate, or delete databases to prepare or clean up benchmarks without explicit permission.
- Report performance results using measured metrics, not estimates.

### Production Environment (`APP_ENV=production`)

Production is reserved for live application operations.

Rules:

- Never run Django unit, integration, functional, or regression tests.
- Never run API load tests, stress tests, or performance benchmarks.
- Never execute `python manage.py test`.
- Never create or destroy test databases.
- Never modify, reset, or delete persistent data for testing.
- Never automatically execute database migrations, destructive operations, or infrastructure lifecycle commands.
- Do not perform experiments or test implementations against production services.
- Require explicit developer authorization before any production-changing operation.

### Environment Verification

Before running any test, benchmark, or environment-dependent command:

1. Determine the effective `APP_ENV` from the actual runtime configuration.
2. Verify that it matches the intended operation.
3. Identify the appropriate Docker Compose configuration.
4. Check that the required existing infrastructure is available.
5. Verify the actual database, Redis, and API targets to avoid cross-environment access.
6. Proceed only if the operation is permitted for that environment.

If the environment cannot be identified reliably, do not execute tests or benchmarks.

Never switch `APP_ENV` automatically to bypass restrictions.

### Test and Benchmark Restrictions

- Django automated tests are permitted only in `development`.
- API load and performance benchmarks are permitted only in `apiLoadTest`.
- No tests or benchmarks are permitted in `production`.
- Never create temporary infrastructure to bypass environment restrictions.
- Never change the environment configuration merely to make a prohibited operation possible.
- If the current environment does not permit the requested operation, explain the restriction and ask the developer to switch to the appropriate environment.
- Always distinguish successfully executed tests and benchmarks from skipped or blocked verification.
- Never claim tests passed or performance targets were achieved without executing the relevant verification.


## Mandatory Agent Skills and Tools

Every task must follow the mandatory skills and tools workflow.

Required skills:
- caveman
- i-have-adhd
- ponytail
- qmd

Required CLI tool:
- RTK

Rules:
1. Apply all five skill instruction sets on every request.
2. Use RTK for supported shell commands.
3. Do not skip mandatory skills because a task is simple.
4. Preserve correctness over token optimization.
5. Follow explicit user instructions and security constraints.
6. Never claim a skill or tool was used if it was not.
7. Report any mandatory tool that could not be used.
8. If any required skill is unavailable, stop and report it.