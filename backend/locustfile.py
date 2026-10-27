import base64
import json
import logging
import os
import random
import re
import uuid
from collections import defaultdict
from io import BytesIO
from typing import Any, Iterable, Optional

from gevent import sleep
from gevent.event import Event
from gevent.lock import Semaphore
from locust import HttpUser, between, events, task
from locust.exception import StopUser
from PIL import Image

logger = logging.getLogger(__name__)


# ======================================================================
# CONFIGURATION
# ======================================================================
TASK_WAIT_MIN = float(os.getenv("LOCUST_TASK_WAIT_MIN", "2"))
TASK_WAIT_MAX = float(os.getenv("LOCUST_TASK_WAIT_MAX", "5"))

# User sees the gym list and decides which gym to open
GYM_LIST_READ_MIN = float(os.getenv("LOCUST_GYM_LIST_READ_MIN", "2"))
GYM_LIST_READ_MAX = float(os.getenv("LOCUST_GYM_LIST_READ_MAX", "6"))

# User reads gym information before choosing another section
GYM_DETAIL_READ_MIN = float(os.getenv("LOCUST_GYM_DETAIL_READ_MIN", "3"))
GYM_DETAIL_READ_MAX = float(os.getenv("LOCUST_GYM_DETAIL_READ_MAX", "8"))

# User looks through plans/photos
GYM_CONTENT_READ_MIN = float(os.getenv("LOCUST_GYM_CONTENT_READ_MIN", "3"))
GYM_CONTENT_READ_MAX = float(os.getenv("LOCUST_GYM_CONTENT_READ_MAX", "10"))

# Profile is usually checked fairly quickly
PROFILE_READ_MIN = float(os.getenv("LOCUST_PROFILE_READ_MIN", "2"))
PROFILE_READ_MAX = float(os.getenv("LOCUST_PROFILE_READ_MAX", "5"))

# User looks at active/logged-in sessions
SESSIONS_READ_MIN = float(os.getenv("LOCUST_SESSIONS_READ_MIN", "2"))
SESSIONS_READ_MAX = float(os.getenv("LOCUST_SESSIONS_READ_MAX", "6"))

# User checks referral information
REFERRALS_READ_MIN = float(os.getenv("LOCUST_REFERRALS_READ_MIN", "3"))
REFERRALS_READ_MAX = float(os.getenv("LOCUST_REFERRALS_READ_MAX", "8"))

# Announcements are actual content, so reading takes longer
ANNOUNCEMENTS_READ_MIN = float(os.getenv("LOCUST_ANNOUNCEMENTS_READ_MIN", "4"))
ANNOUNCEMENTS_READ_MAX = float(os.getenv("LOCUST_ANNOUNCEMENTS_READ_MAX", "12"))

# User examines subscription information
SUBSCRIPTIONS_READ_MIN = float(os.getenv("LOCUST_SUBSCRIPTIONS_READ_MIN", "3"))
SUBSCRIPTIONS_READ_MAX = float(os.getenv("LOCUST_SUBSCRIPTIONS_READ_MAX", "8"))


# ======================================================================
# SHARED BOOTSTRAP STATE
# ======================================================================

_BOOTSTRAP_EVENT = Event()
_BOOTSTRAP_LOCK = Semaphore()

_BOOTSTRAP_DATA: dict[str, Any] = {}
_BOOTSTRAP_ERROR = ""


# ======================================================================
# DJANGO TIMING STATISTICS
#
# IMPORTANT:
# These statistics are NOT fired into Locust's request event system.
#
# Therefore:
#
#   Locust RPS      = real HTTP RPS
#   Locust requests = real HTTP requests
#   Locust latency  = real HTTP latency
#
# Django timing is collected independently.
# ======================================================================

_DJANGO_TIMING_LOCK = Semaphore()

_DJANGO_TIMINGS: dict[str, dict[str, Any]] = defaultdict(
    lambda: {
        "count": 0,
        "total": 0.0,
        "min": None,
        "max": None,
        "values": [],
    }
)


# ======================================================================
# HELPERS
# ======================================================================


def _otp_code() -> str:
    return os.getenv(
        "LOCUST_OTP_CODE",
        "123456",
    ).strip()


def _new_test_phone() -> str:
    """
    Generate a random Iranian-style 11-digit test phone number.
    """

    prefix = os.getenv(
        "LOCUST_TEST_PHONE_PREFIX",
        "09",
    ).strip()

    if not re.fullmatch(r"09\d{0,8}", prefix):
        raise RuntimeError(
            "LOCUST_TEST_PHONE_PREFIX must start with 09 "
            "and contain at most 10 digits"
        )

    suffix_length = 11 - len(prefix)

    suffix = uuid.uuid4().int % (10**suffix_length)

    return f"{prefix}{suffix:0{suffix_length}d}"


def _jpeg_bytes() -> bytes:
    image = Image.new(
        "RGB",
        (32, 32),
        color="blue",
    )

    output = BytesIO()

    image.save(
        output,
        format="JPEG",
    )

    return output.getvalue()


def _human_pause(
    minimum: float,
    maximum: float,
) -> None:
    """
    Simulate a person reading/thinking/interacting with the UI.
    """

    sleep(
        random.uniform(
            minimum,
            maximum,
        )
    )


# ======================================================================
# DJANGO SERVER-TIMING PARSER
# ======================================================================


def _get_django_timing_ms(response) -> Optional[float]:
    """
    Extract Django processing time from:

        Server-Timing: django;dur=12.34

    Also supports multiple metrics:

        Server-Timing: django;dur=12.34, sql;dur=2.10
    """

    header = response.headers.get("Server-Timing")

    if not header:
        return None

    for metric in header.split(","):
        metric = metric.strip()

        if not metric.startswith("django;"):
            continue

        for part in metric.split(";")[1:]:
            part = part.strip()

            if not part.startswith("dur="):
                continue

            try:
                return float(part[4:])

            except ValueError:
                return None

    return None


# ======================================================================
# DJANGO TIMING COLLECTION
# ======================================================================


def _record_django_timing(
    name: str,
    duration_ms: float,
) -> None:
    """
    Store Django timing independently from Locust's HTTP statistics.

    This is intentionally NOT:

        events.request.fire(...)

    because doing that would make Locust count Django timing as another
    request and would double the reported request count/RPS.
    """

    with _DJANGO_TIMING_LOCK:
        stats = _DJANGO_TIMINGS[name]

        stats["count"] += 1
        stats["total"] += duration_ms

        if stats["min"] is None or duration_ms < stats["min"]:
            stats["min"] = duration_ms

        if stats["max"] is None or duration_ms > stats["max"]:
            stats["max"] = duration_ms

        stats["values"].append(duration_ms)


def _percentile(
    values: list[float],
    percentile: float,
) -> float:
    """
    Simple percentile calculation for diagnostic Django timing output.
    """

    if not values:
        return 0.0

    sorted_values = sorted(values)

    index = int(round(percentile * (len(sorted_values) - 1)))

    index = max(
        0,
        min(
            index,
            len(sorted_values) - 1,
        ),
    )

    return sorted_values[index]


# ======================================================================
# PRINT DJANGO TIMINGS WHEN LOCUST STOPS
# ======================================================================


@events.test_stop.add_listener
def _print_django_timing_statistics(
    environment,
    **kwargs,
) -> None:
    """
    Print Django timing separately at the end of the Locust run.

    Locust's normal report remains 100% real HTTP statistics.
    """

    if not _DJANGO_TIMINGS:
        logger.info("No Django Server-Timing measurements were collected.")
        return

    print()
    print()
    print("=" * 118)
    print("DJANGO SERVER-TIMING STATISTICS")
    print("=" * 118)

    header = (
        f"{'Name':45}"
        f"{'Count':>10}"
        f"{'Avg':>10}"
        f"{'Min':>10}"
        f"{'p50':>10}"
        f"{'p90':>10}"
        f"{'p95':>10}"
        f"{'p99':>10}"
        f"{'Max':>10}"
    )

    print(header)

    print("-" * 118)

    for name in sorted(_DJANGO_TIMINGS):
        stats = _DJANGO_TIMINGS[name]

        count = stats["count"]

        if count == 0:
            continue

        values = stats["values"]

        average = stats["total"] / count

        minimum = stats["min"] or 0.0
        maximum = stats["max"] or 0.0

        p50 = _percentile(values, 0.50)
        p90 = _percentile(values, 0.90)
        p95 = _percentile(values, 0.95)
        p99 = _percentile(values, 0.99)

        print(
            f"{name:45}"
            f"{count:>10}"
            f"{average:>10.2f}"
            f"{minimum:>10.2f}"
            f"{p50:>10.2f}"
            f"{p90:>10.2f}"
            f"{p95:>10.2f}"
            f"{p99:>10.2f}"
            f"{maximum:>10.2f}"
        )

    print("=" * 118)
    print(
        "NOTE: Django timings above are separate from Locust request "
        "statistics. Locust RPS/request counts are real HTTP values."
    )
    print("=" * 118)
    print()


# ======================================================================
# BASE AUTHENTICATED USER
# ======================================================================


class AuthenticatedApiUser(HttpUser):
    abstract = True

    host = os.getenv(
        "LOCUST_HOST",
        "http://localhost:8000",
    )

    wait_time = between(
        TASK_WAIT_MIN,
        TASK_WAIT_MAX,
    )

    role_key = ""

    logout_on_stop = False

    # ------------------------------------------------------------------
    # LOCUST START
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.authenticated = False

        self.otp_code = _otp_code()

        self._ensure_shared_bootstrap()

        if not self.role_key:
            self._abort(f"{self.__class__.__name__} does not define role_key")

        session = self.bootstrap_data["sessions"].get(self.role_key)

        if not session:
            self._abort(f"No bootstrap session exists for role={self.role_key}")

        self._restore_session(session)

        self.gym_id = self.bootstrap_data["gym_id"]

        self.after_login()

    # ------------------------------------------------------------------
    # SHARED BOOTSTRAP DATA
    # ------------------------------------------------------------------

    @property
    def bootstrap_data(self) -> dict[str, Any]:
        return _BOOTSTRAP_DATA

    # ------------------------------------------------------------------
    # SHARED BOOTSTRAP
    # ------------------------------------------------------------------

    def _ensure_shared_bootstrap(self) -> None:
        global _BOOTSTRAP_ERROR

        if not _BOOTSTRAP_EVENT.is_set():

            with _BOOTSTRAP_LOCK:

                if not _BOOTSTRAP_EVENT.is_set():

                    try:
                        self._bootstrap_shared_test_data()

                    except StopUser:

                        _BOOTSTRAP_ERROR = (
                            "Shared load-test bootstrap failed; "
                            "inspect the first failed bootstrap request "
                            "in the Locust/backend logs"
                        )

                        raise

                    except Exception as error:

                        _BOOTSTRAP_ERROR = (
                            "Shared load-test bootstrap failed: " f"{error}"
                        )

                        logger.exception("Unexpected shared bootstrap failure")

                        raise StopUser() from error

                    finally:
                        _BOOTSTRAP_EVENT.set()

        if _BOOTSTRAP_ERROR:
            self._abort(_BOOTSTRAP_ERROR)

    def _bootstrap_shared_test_data(self) -> None:
        admin_phone = os.getenv(
            "LOCUST_ADMIN_PHONE",
            "09024629079",
        ).strip()

        if not admin_phone:
            self._abort(
                "Set LOCUST_ADMIN_PHONE to an existing admin "
                "account; the API cannot create admin users"
            )

        self.otp_code = _otp_code()

        logger.info("Starting shared load-test bootstrap")

        # ==============================================================
        # ADMIN LOGIN
        # ==============================================================

        self._login_account(
            admin_phone,
            request_name="bootstrap/admin/request",
            fatal=True,
        )

        sessions: dict[str, Any] = {
            "admin": self._save_session(admin_phone),
        }

        phone_numbers: dict[str, str] = {}

        user_ids: dict[str, str] = {}

        # ==============================================================
        # OWNER + STAFF
        # ==============================================================

        used_phones = {
            admin_phone,
        }

        for role in (
            "owner",
            "staff",
        ):

            while True:
                phone = _new_test_phone()

                if phone not in used_phones:
                    used_phones.add(phone)
                    break

            phone_numbers[role] = phone

            logger.info(
                "Creating bootstrap %s account: %s",
                role,
                phone,
            )

            self._signup_account(
                phone,
                name=f"bootstrap/{role}/signup",
                fatal=True,
            )

            user_ids[role] = self.user_id

            sessions[role] = self._save_session(phone)

        # ==============================================================
        # RESTORE ADMIN
        # ==============================================================

        self._restore_session(sessions["admin"])

        # ==============================================================
        # CREATE GYM
        # ==============================================================

        gym_result = self._request(
            "POST",
            "/api/gym/create/",
            name="bootstrap/gym/create",
            json_body={
                "name": f"Locust {uuid.uuid4().hex[:10]}",
                "province": "Load Test Province",
                "city": "Load Test City",
                "address": "Load test address",
            },
            expected_status=(201,),
            expected_paths=(("gym", "id"),),
            fatal=True,
        )

        gym_id = str(gym_result["gym"]["id"])

        # ==============================================================
        # ASSIGN OWNER
        # ==============================================================

        self._request(
            "POST",
            f"/api/gym/{gym_id}/owner/create/",
            name="bootstrap/gym/assign-owner",
            json_body={
                "user": user_ids["owner"],
            },
            expected_status=(200,),
            fatal=True,
        )

        # ==============================================================
        # ASSIGN STAFF
        # ==============================================================

        self._request(
            "POST",
            f"/api/gym/{gym_id}/staff/create/",
            name="bootstrap/gym/assign-staff",
            json_body={
                "user": user_ids["staff"],
            },
            expected_status=(200,),
            fatal=True,
        )

        # ==============================================================
        # DEVICES
        # ==============================================================

        devices: dict[
            str,
            tuple[str, str],
        ] = {}

        for device_type in (
            "entrance",
            "locker",
        ):

            result = self._request(
                "POST",
                f"/api/gym/{gym_id}/devices/create/",
                name=("bootstrap/devices/" f"create-{device_type}"),
                json_body={
                    "device_type": device_type,
                },
                expected_status=(201,),
                expected_paths=(
                    ("device", "id"),
                    ("token",),
                ),
                fatal=True,
            )

            devices[device_type] = (
                str(result["device"]["id"]),
                str(result["token"]),
            )

        # ==============================================================
        # LOCKERS
        # ==============================================================

        self._request(
            "POST",
            f"/api/gym/{gym_id}/create/",
            name="bootstrap/lockers/create",
            json_body={
                "count": 2,
            },
            expected_status=(201,),
            fatal=True,
        )

        # ==============================================================
        # SAVE SHARED DATA
        # ==============================================================

        _BOOTSTRAP_DATA.update(
            {
                "gym_id": gym_id,
                "phones": phone_numbers,
                "sessions": sessions,
                "devices": devices,
            }
        )

        logger.info(
            "Shared bootstrap completed. gym=%s",
            gym_id,
        )

    # ------------------------------------------------------------------
    # COOKIE HELPERS
    # ------------------------------------------------------------------

    def _get_cookie(
        self,
        name: str,
    ) -> Optional[str]:

        matches = [
            cookie.value for cookie in self.client.cookies if cookie.name == name
        ]

        if not matches:
            return None

        return matches[-1]

    def _clear_auth_cookies(self) -> None:

        for cookie in list(self.client.cookies):

            if cookie.name not in (
                "access_token",
                "refresh_token",
            ):
                continue

            try:
                self.client.cookies.clear(
                    domain=cookie.domain,
                    path=cookie.path,
                    name=cookie.name,
                )

            except KeyError:
                pass

    # ------------------------------------------------------------------
    # LOGIN
    # ------------------------------------------------------------------

    def _login_account(
        self,
        phone_number: str,
        *,
        request_name: str = "auth/login/request",
        fatal: bool = True,
    ) -> None:

        self._clear_auth_cookies()

        self._request(
            "POST",
            "/api/auth/login/request/",
            name=request_name,
            json_body={
                "phone_number": phone_number,
            },
            expected_status=(200,),
            fatal=fatal,
        )

        data = self._request(
            "POST",
            "/api/auth/login/verify/",
            name=request_name.replace(
                "request",
                "verify",
            ),
            json_body={
                "phone_number": phone_number,
                "otp": self.otp_code,
            },
            expected_status=(200,),
            expected_paths=(
                ("new_user",),
                ("user",),
            ),
            expected_values={
                ("new_user",): False,
            },
            fatal=fatal,
        )

        if data is None:

            if fatal:
                self._abort(f"{request_name}: login verify returned no data")

            return

        if not isinstance(
            data,
            dict,
        ) or not isinstance(
            data.get("user"),
            dict,
        ):

            message = "Existing-user login did not " "return a user profile"

            if fatal:
                self._abort(message)

            logger.error(message)

            return

        self.authenticated = True

        self.user_id = self._jwt_claim("key_1")

        self.session_id = self._jwt_claim("key_2")

    # ------------------------------------------------------------------
    # SIGNUP
    # ------------------------------------------------------------------

    def _signup_account(
        self,
        phone_number: str,
        *,
        name: str = "signup",
        fatal: bool = True,
    ) -> None:

        self._clear_auth_cookies()

        # ==============================================================
        # REQUEST OTP
        # ==============================================================

        self._request(
            "POST",
            "/api/auth/login/request/",
            name=f"{name}/auth/request",
            json_body={
                "phone_number": phone_number,
            },
            expected_status=(200,),
            fatal=fatal,
        )

        # ==============================================================
        # VERIFY OTP
        # ==============================================================

        verify_data = self._request(
            "POST",
            "/api/auth/login/verify/",
            name=f"{name}/auth/verify",
            json_body={
                "phone_number": phone_number,
                "otp": self.otp_code,
            },
            expected_status=(200,),
            expected_paths=(("new_user",),),
            expected_values={
                ("new_user",): True,
                ("user",): None,
            },
            fatal=fatal,
        )

        if verify_data is None:

            if fatal:
                self._abort(f"{name}: signup OTP verification " "returned no data")

            return

        if verify_data["new_user"] is not True:

            message = "Generated test phone already exists: " f"{phone_number}"

            if fatal:
                self._abort(message)

            logger.error(message)

            return

        # ==============================================================
        # CREATE USER
        # ==============================================================

        create_data = self._request(
            "POST",
            "/api/users/signup/",
            name=f"{name}/create",
            json_body={
                "phone_number": phone_number,
                "first_name": os.getenv(
                    "LOCUST_SIGNUP_FIRST_NAME",
                    "LoadTest",
                ),
                "last_name": os.getenv(
                    "LOCUST_SIGNUP_LAST_NAME",
                    "User",
                ),
                "gender": os.getenv(
                    "LOCUST_SIGNUP_GENDER",
                    "MALE",
                ),
                "date_of_birth": os.getenv(
                    "LOCUST_SIGNUP_DATE_OF_BIRTH",
                    "1990-01-01",
                ),
            },
            expected_status=(201,),
            expected_paths=(("user",),),
            fatal=fatal,
        )

        if create_data is None:

            if fatal:
                self._abort(f"{name}: signup returned no data")

            return

        self.authenticated = True

        self.user_id = self._jwt_claim("key_1")

        self.session_id = self._jwt_claim("key_2")

    # ------------------------------------------------------------------
    # SESSION
    # ------------------------------------------------------------------

    def _save_session(
        self,
        phone_number: str,
    ) -> dict[str, str]:

        session = {
            "phone_number": phone_number,
        }

        for cookie_name in (
            "access_token",
            "refresh_token",
        ):

            value = self._get_cookie(cookie_name)

            if not value:
                self._abort("Signup/login did not set the " f"{cookie_name} cookie")

            session[cookie_name] = value

        return session

    def _restore_session(
        self,
        session: dict[str, str],
    ) -> None:

        self.phone_number = session["phone_number"]

        self.client.cookies.clear()

        for cookie_name in (
            "access_token",
            "refresh_token",
        ):

            self.client.cookies.set(
                cookie_name,
                session[cookie_name],
            )

        self.user_id = self._jwt_claim("key_1")

        self.session_id = self._jwt_claim("key_2")

        self.authenticated = True

    # ------------------------------------------------------------------
    # REQUEST HELPER
    # ------------------------------------------------------------------

    @staticmethod
    def _value_at_path(
        data: Any,
        path: tuple[str, ...],
    ) -> Any:

        value = data

        for component in path:

            if (
                not isinstance(
                    value,
                    dict,
                )
                or component not in value
            ):
                return None

            value = value[component]

        return value

    def _request(
        self,
        method: str,
        path: str,
        *,
        name: str,
        expected_status: Iterable[int] = (200,),
        expected_paths: tuple[tuple[str, ...], ...] = (),
        expected_lists: tuple[tuple[str, ...], ...] = (),
        expected_values: Optional[
            dict[
                tuple[str, ...],
                Any,
            ]
        ] = None,
        json_body: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        files: Optional[
            dict[
                str,
                tuple[
                    str,
                    bytes,
                    str,
                ],
            ]
        ] = None,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        fatal: bool = False,
    ) -> Any:

        options: dict[str, Any] = {
            "name": name,
            "catch_response": True,
        }

        if json_body is not None:
            options["json"] = json_body

        if data is not None:
            options["data"] = data

        if files is not None:
            options["files"] = files

        if params is not None:
            options["params"] = params

        if headers is not None:
            options["headers"] = headers

        with self.client.request(
            method,
            path,
            **options,
        ) as response:

            # ==========================================================
            # DJANGO SERVER TIMING
            #
            # IMPORTANT:
            # This does NOT create another Locust request event.
            #
            # Therefore Locust's RPS remains REAL HTTP RPS.
            # ==========================================================

            if response.status_code != 0:

                django_time_ms = _get_django_timing_ms(response)

                if django_time_ms is not None:
                    _record_django_timing(
                        name,
                        django_time_ms,
                    )

            # ==========================================================
            # TRANSPORT FAILURE
            # ==========================================================

            if response.status_code == 0:

                error = getattr(
                    response,
                    "error",
                    None,
                )

                message = (
                    f"{name}: HTTP transport failure "
                    f"for {method} {path}: "
                    f"{error!r}"
                )

                logger.error(message)

                response.failure(message)

                if fatal:
                    raise StopUser()

                return None

            # ==========================================================
            # HTTP STATUS
            # ==========================================================

            if response.status_code not in expected_status:

                body_preview = response.text[:500]

                message = (
                    f"{name}: expected HTTP "
                    f"{tuple(expected_status)}, "
                    f"received "
                    f"{response.status_code}: "
                    f"{body_preview}"
                )

                logger.error(message)

                response.failure(message)

                if fatal:
                    raise StopUser()

                return None

            # ==========================================================
            # JSON
            # ==========================================================

            try:
                envelope = response.json()

            except ValueError:

                message = (
                    f"{name}: expected API JSON "
                    f"envelope; received HTTP "
                    f"{response.status_code}: "
                    f"{response.text[:500]}"
                )

                logger.error(message)

                response.failure(message)

                if fatal:
                    raise StopUser()

                return None

            # ==========================================================
            # SUCCESS ENVELOPE
            # ==========================================================

            if (
                not isinstance(
                    envelope,
                    dict,
                )
                or envelope.get("success") is not True
            ):

                message = (
                    f"{name}: API returned " f"unsuccessful response: " f"{envelope}"
                )

                logger.error(message)

                response.failure(message)

                if fatal:
                    raise StopUser()

                return None

            result = envelope.get("data")

            # ==========================================================
            # REQUIRED PATHS
            # ==============================================================

            for value_path in expected_paths:

                if (
                    self._value_at_path(
                        result,
                        value_path,
                    )
                    is None
                ):

                    message = (
                        f"{name}: successful response "
                        f"is missing data at "
                        f"{'.'.join(value_path)}. "
                        f"Response data={result}"
                    )

                    logger.error(message)

                    response.failure(message)

                    if fatal:
                        raise StopUser()

                    return None

            # ==========================================================
            # REQUIRED LISTS
            # ==========================================================

            for list_path in expected_lists:

                value = self._value_at_path(
                    result,
                    list_path,
                )

                if not isinstance(
                    value,
                    list,
                ):

                    message = (
                        f"{name}: successful response "
                        f"did not return a list at "
                        f"{'.'.join(list_path)}. "
                        f"Response data={result}"
                    )

                    logger.error(message)

                    response.failure(message)

                    if fatal:
                        raise StopUser()

                    return None

            # ==========================================================
            # EXPECTED VALUES
            # ==========================================================

            for (
                value_path,
                expected,
            ) in (expected_values or {}).items():

                actual = self._value_at_path(
                    result,
                    value_path,
                )

                if actual != expected:

                    message = (
                        f"{name}: unexpected value at "
                        f"{'.'.join(value_path)}: "
                        f"expected={expected!r}, "
                        f"actual={actual!r}"
                    )

                    logger.error(message)

                    response.failure(message)

                    if fatal:
                        raise StopUser()

                    return None

            response.success()

            return result

    # ------------------------------------------------------------------
    # JWT
    # ------------------------------------------------------------------

    def _jwt_claim(
        self,
        claim: str,
    ) -> str:

        token = self._get_cookie("access_token")

        try:

            if not token:
                raise ValueError("access_token cookie missing")

            encoded_payload = token.split(".")[1]

            encoded_payload += "=" * (-len(encoded_payload) % 4)

            payload = json.loads(
                base64.urlsafe_b64decode(encoded_payload).decode("utf-8")
            )

            value = payload[claim]

        except (
            AttributeError,
            IndexError,
            KeyError,
            ValueError,
            TypeError,
        ):

            self._abort("Login cookie did not contain " f"JWT claim {claim}")

        return str(value)

    # ------------------------------------------------------------------
    # ABORT
    # ------------------------------------------------------------------

    def _abort(
        self,
        message: str,
    ) -> None:

        logger.error(message)

        raise StopUser()

    # ------------------------------------------------------------------
    # HOOK
    # ------------------------------------------------------------------

    def after_login(self) -> None:
        pass


# ======================================================================
# MEMBER USER
# ======================================================================


class MemberUser(AuthenticatedApiUser):
    """
    Exlo member load-test workload.
    """

    abstract = False

    role_key = "member"

    # ------------------------------------------------------------------
    # MEMBER START
    # ------------------------------------------------------------------

    def on_start(self) -> None:

        self.authenticated = False

        self.otp_code = _otp_code()

        self._ensure_shared_bootstrap()

        self.gym_id = self.bootstrap_data["gym_id"]

        member_phone = _new_test_phone()

        self.phone_number = member_phone

        logger.info(
            "Creating unique member account " "for VU: %s",
            member_phone,
        )

        self._signup_account(
            member_phone,
            name="member/signup",
            fatal=True,
        )

        if not self.authenticated:
            self._abort("Member signup completed without " "an authenticated session")

        logger.info(
            "Member VU ready: " "phone=%s user_id=%s session_id=%s",
            self.phone_number,
            self.user_id,
            self.session_id,
        )

        self.after_login()

    # ==================================================================
    # PROFILE
    # ==================================================================

    @task(2)
    def view_profile(self) -> None:

        data = self._request(
            "GET",
            "/api/users/profile/",
            name="member/profile",
            expected_status=(200,),
            expected_paths=(("user",),),
            fatal=False,
        )

        if data is None:
            return

        _human_pause(
            PROFILE_READ_MIN,
            PROFILE_READ_MAX,
        )

    # ==================================================================
    # SESSIONS
    # ==================================================================

    @task(2)
    def list_sessions(self) -> None:

        data = self._request(
            "GET",
            "/api/sessions/",
            name="member/sessions",
            expected_status=(200,),
            expected_lists=(("sessions",),),
            fatal=False,
        )

        if data is None:
            return

        _human_pause(
            SESSIONS_READ_MIN,
            SESSIONS_READ_MAX,
        )

    # ==================================================================
    # REFERRALS
    # ==================================================================

    @task(1)
    def list_referrals(self) -> None:

        data = self._request(
            "GET",
            "/api/referrals/",
            name="member/referrals",
            expected_status=(200,),
            expected_lists=(("referrals",),),
            fatal=False,
        )

        if data is None:
            return

        _human_pause(
            REFERRALS_READ_MIN,
            REFERRALS_READ_MAX,
        )

    # ==================================================================
    # GYM BROWSING
    # ==================================================================

    @task(8)
    def browse_gyms(self) -> None:

        data = self._request(
            "GET",
            "/api/gym/",
            name="member/gyms",
            expected_status=(200,),
            expected_lists=(("gyms",),),
            fatal=False,
        )

        if data is None:
            return

        gyms = data["gyms"]

        if not gyms:

            logger.warning("No active gyms returned; " "skipping gym browsing journey")

            return

        # --------------------------------------------------------------
        # USER READS GYM LIST
        # --------------------------------------------------------------

        _human_pause(
            GYM_LIST_READ_MIN,
            GYM_LIST_READ_MAX,
        )

        selected_gym = random.choice(gyms)

        gym_id = str(selected_gym["id"])

        # --------------------------------------------------------------
        # GYM DETAIL
        # --------------------------------------------------------------

        detail = self._request(
            "GET",
            f"/api/gym/{gym_id}/",
            name="member/gym/detail",
            expected_status=(200,),
            expected_paths=(("gym",),),
            fatal=False,
        )

        if detail is None:
            return

        _human_pause(
            GYM_DETAIL_READ_MIN,
            GYM_DETAIL_READ_MAX,
        )

        # --------------------------------------------------------------
        # PLANS / PHOTOS / LEAVE
        # --------------------------------------------------------------

        choice = random.random()

        if choice < 0.45:

            plans = self._request(
                "GET",
                f"/api/gym/{gym_id}/plans/",
                name="member/gym/plans",
                expected_status=(200,),
                expected_lists=(("plans",),),
                fatal=False,
            )

            if plans is not None:

                _human_pause(
                    GYM_CONTENT_READ_MIN,
                    GYM_CONTENT_READ_MAX,
                )

        elif choice < 0.80:

            photos = self._request(
                "GET",
                f"/api/gym/{gym_id}/photos/",
                name="member/gym/photos",
                expected_status=(200,),
                expected_lists=(("gym_photos",),),
                fatal=False,
            )

            if photos is not None:

                _human_pause(
                    GYM_CONTENT_READ_MIN,
                    GYM_CONTENT_READ_MAX,
                )

    # ==================================================================
    # ANNOUNCEMENTS
    # ==================================================================

    @task(2)
    def list_announcements(self) -> None:

        data = self._request(
            "GET",
            (f"/api/gym/" f"{self.gym_id}/" f"announcements/"),
            name="member/gym/announcements",
            expected_status=(200,),
            expected_lists=(("announcements",),),
            fatal=False,
        )

        if data is None:
            return

        _human_pause(
            ANNOUNCEMENTS_READ_MIN,
            ANNOUNCEMENTS_READ_MAX,
        )

    # ==================================================================
    # SUBSCRIPTIONS
    # ==================================================================

    @task(2)
    def browse_subscriptions(self) -> None:

        data = self._request(
            "GET",
            "/api/gym/subscriptions/",
            name="member/subscriptions",
            expected_status=(200,),
            expected_lists=(("subscriptions",),),
            fatal=False,
        )

        if data is None:
            return

        subscriptions = data["subscriptions"]

        _human_pause(
            SUBSCRIPTIONS_READ_MIN,
            SUBSCRIPTIONS_READ_MAX,
        )

        if not subscriptions:
            return

        if random.random() > 0.60:
            return

        selected_subscription = random.choice(subscriptions)

        subscription_id = selected_subscription.get("id")

        if subscription_id is None:
            return

        self._request(
            "GET",
            ("/api/gym/subscriptions/" f"{subscription_id}/"),
            name="member/subscription/detail",
            expected_status=(200,),
            expected_paths=(("subscription",),),
            fatal=False,
        )

        _human_pause(
            SUBSCRIPTIONS_READ_MIN,
            SUBSCRIPTIONS_READ_MAX,
        )
