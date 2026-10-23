# Repository guide

## Build and test

The Django project lives in `backend/`. Install its dependencies from that directory with `pip install -r requirements.txt`.

Run the test suite from `backend/`:

```sh
python manage.py test
```

`manage.py` automatically selects `config.settings_test` for test commands. Run a narrower test by passing a module, test class, or test method, for example:

```sh
python manage.py test authentication.tests.test_otp
python manage.py test authentication.tests.test_otp.OTPServiceTest.test_verify_otp_success
```

Build the backend image from the repository root:

```sh
docker build -t fitness-platform-backend ./backend
```

For local infrastructure, `docker compose -f docker-compose.dev.yml up -d` starts PostgreSQL and Redis. Start the Django development server from `backend/` with `python manage.py runserver`. There is no configured lint command in the repository.

## Architecture

- This is a Django REST Framework backend, not a full-stack checkout. `backend/config/settings.py` registers the domain apps and configures PostgreSQL, Redis, JWT authentication, and REST defaults. `backend/config/urls.py` mounts app URL modules beneath `/api/`.
- Features are split into Django apps: `users` and `users_sessions` provide the core identity/session data; `authentication` implements OTP sign-in and JWT handling; `gym*` apps cover gyms, memberships, visits, devices and access control; `commerce_*` apps cover products, orders, payments, refunds, commissions, and wallets. Related user features (referrals, measurements, NFC cards) also live in separate apps.
- HTTP requests generally flow from an app's `urls.py` to DRF `APIView` classes in `views.py`, then through serializers and Django models/managers. Shared API behavior is in `backend/core/` (errors, exception handling, pagination, rendering, hashing, and SMS tasks).
- The ASGI entry point (`backend/config/asgi.py`) routes HTTP to Django and WebSockets through Channels; WebSocket URL patterns are in `backend/config/routing.py`. Celery is initialized in `backend/config/celery.py`; app tasks handle deferred work such as SMS and periodic cleanup.
- Production Compose runs the ASGI app with Uvicorn and starts PostgreSQL, PgBouncer, and Redis. The development Compose file provides PostgreSQL and Redis only.

## Repository conventions

- Keep domain behavior in its owning app and mount its URL module in `backend/config/urls.py` when adding endpoints. Use DRF `APIView` and serializers for request validation/representation; pass `context={"request": request}` when serializing API data that depends on the request.
- Use `APIError` and the typed error constants from `core/errors.py` for expected API failures. `core/exception_handler.py` maps these to the repository's `error_code` response shape; avoid returning a different error format from an endpoint.
- The configured identity model is `users.User` (`AUTH_USER_MODEL`), keyed by UUID and identified by a unique phone number. Use its manager and validation methods rather than assuming Django's default username/email fields.
- User authentication is OTP plus SimpleJWT. Access tokens include both a user claim and a session claim; the custom authentication classes check the related `users_sessions.Session` row on requests. Keep token/session creation and validation aligned when changing auth flows. Gym devices have a separate `Device` authorization scheme in `gym_devices`.
- User signup creates related records (including the wallet) transactionally; preserve transaction boundaries when changing multi-model workflows. Put deferred or scheduled operations in Celery tasks rather than doing them inline in a request.
- Tests use Django `TestCase` and DRF's `APIClient`, organized under each app's `tests/` package (some small apps use a single `tests.py`). `manage.py test` applies `config.settings_test`, which uses in-memory storage.
