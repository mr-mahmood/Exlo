import secrets
from dataclasses import dataclass, replace
from enum import StrEnum
from math import ceil
from uuid import UUID, uuid4

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from kombu.exceptions import EncodeError, OperationalError
from redis.exceptions import RedisError, WatchError

from core.errors import APIError, OTPError
from core.hashing import hash_secret, verify_secret

MAX_WATCH_RETRIES = 3


class OTPPurpose(StrEnum):
    LOGIN = "login"
    OLD_PHONE = "old_phone"
    NEW_PHONE = "new_phone"


@dataclass(frozen=True)
class OTPWorkflow:
    """The state an OTP operation must still see, and its optional next step."""

    key: str
    expected: dict | None
    next_state: dict | None = None
    conflict_error: tuple = OTPError.INVALID_STEP

    def read_watched(self, pipe):
        key = cache.make_key(self.key)
        pipe.watch(key)
        raw = pipe.get(key)
        return cache.client.decode(raw) if raw is not None else None

    def watch(self, pipe):
        current = self.read_watched(pipe)
        if current != self.expected:
            raise APIError(self.conflict_error if current is not None else OTPError.OTP_NOT_FOUND)

    def advance(self, pipe):
        if self.next_state is not None:
            pipe.set(cache.make_key(self.key), cache.client.encode(self.next_state), ex=300)

    def queue_rollback(self, pipe, expires_at):
        key = cache.make_key(self.key)
        if self.expected is None:
            pipe.delete(key)
        else:
            # Use the original absolute expiry, including time spent publishing.
            pipe.set(key, cache.client.encode(self.expected), pxat=expires_at if expires_at > 0 else None)


def _otp_key(phone_number, purpose, user_id):
    purpose = OTPPurpose(purpose)
    return f"otp:{purpose}:{user_id or '-'}:{phone_number}"


def _phone_change_flow_id(purpose, user_id, state):
    if purpose == OTPPurpose.LOGIN:
        return None
    if user_id is None or not state or state.get("user_id") != user_id:
        raise APIError(OTPError.OTP_NOT_FOUND)
    flow_id = state.get("flow_id")
    if not isinstance(flow_id, UUID):
        raise APIError(OTPError.OTP_NOT_FOUND)
    return flow_id


def _retry_after(ttl_ms):
    return max(1, ceil((ttl_ms or 0) / 1000))


def _is_watch_conflict(exc):
    # redis-py also raises WatchError when the connection drops during EXEC.
    return (
        isinstance(exc, WatchError)
        and exc.args == ("Watched variable changed.",)
        and not isinstance(exc.__cause__, RedisError)
        and not isinstance(exc.__context__, RedisError)
    )


def delete_if_unchanged(cache_key, expected):
    """Delete only the record that the caller read."""

    try:
        client = cache.client.get_client(write=True)
        key = cache.make_key(cache_key)
        with client.pipeline() as pipe:
            pipe.watch(key)

            current = pipe.get(key)

            if current is None:
                return False

            if cache.client.decode(current) != expected:
                return False

            pipe.multi()
            pipe.delete(key)

            return bool(pipe.execute()[0])

    except RedisError:
        return False


def _reserve_workflow_otp(cache_key, challenge, workflow, *, restart):
    key = cache.make_key(cache_key)
    client = cache.client.get_client(write=True)
    for _ in range(MAX_WATCH_RETRIES + 1):
        with client.pipeline() as pipe:
            pipe.watch(key)
            ttl_ms = pipe.pttl(key)
            if ttl_ms != -2:
                raise APIError(OTPError.OTP_ALREADY_ACTIVE, retry_after=_retry_after(ttl_ms))
            if restart:
                # A completed flow's on_commit cleanup can run after its row unlocks.
                workflow = replace(workflow, expected=workflow.read_watched(pipe))
            else:
                workflow.watch(pipe)
            expires_at = None
            if workflow.expected is not None and workflow.next_state is not None:
                expires_at = pipe.pexpiretime(cache.make_key(workflow.key))
            pipe.multi()
            pipe.set(key, cache.client.encode(challenge), ex=settings.OTP_EXPIRY_SECONDS)
            workflow.advance(pipe)
            try:
                pipe.execute()
                return workflow, expires_at
            except WatchError as exc:
                if not _is_watch_conflict(exc):
                    raise
    raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)


def _cancel_unsent_workflow_otp(cache_key, challenge_id, workflow, expires_at):
    key = cache.make_key(cache_key)
    state_key = cache.make_key(workflow.key)
    reserved_state = workflow.next_state or workflow.expected
    try:
        client = cache.client.get_client(write=True)
        # Each failed verification can invalidate one cleanup attempt.
        for _ in range(settings.OTP_MAX_ATTEMPTS + 1):
            with client.pipeline() as pipe:
                pipe.watch(key, state_key)
                raw_challenge, raw_state = pipe.mget(key, state_key)
                if raw_challenge is None or raw_state is None:
                    return
                challenge = cache.client.decode(raw_challenge)
                if not isinstance(challenge, tuple) or len(challenge) != 3:
                    return
                current_id, stored_hash, failures = challenge
                if current_id != challenge_id or cache.client.decode(raw_state) != reserved_state:
                    return
                if stored_hash is None and failures < settings.OTP_MAX_ATTEMPTS:
                    return  # Successfully consumed before publication failed.

                pipe.multi()
                pipe.delete(key)
                if workflow.next_state is not None:
                    workflow.queue_rollback(pipe, expires_at)
                try:
                    pipe.execute()
                    return
                except WatchError as exc:
                    if not _is_watch_conflict(exc):
                        raise
    except RedisError:
        return  # Publication already returns OTP_SERVICE_UNAVAILABLE.


def generate_otp(
    *,
    phone_number: str,
    purpose: OTPPurpose,
    user_id=None,
    workflow: OTPWorkflow | None = None,
    publish_after_commit: bool = False,
) -> None:
    """Use the canonical phone number supplied by the caller."""

    cache_key = _otp_key(phone_number, purpose, user_id)
    state = None
    if workflow is not None:
        state = workflow.next_state if purpose == OTPPurpose.OLD_PHONE else workflow.expected
    flow_id = _phone_change_flow_id(purpose, user_id, state)

    if settings.IS_PRODUCTION:
        otp_code = str(secrets.randbelow(900000) + 100000)
    else:
        otp_code = "123456"

    issuance_id = uuid4().hex
    challenge_id = (flow_id, issuance_id) if flow_id is not None else issuance_id
    challenge = (challenge_id, hash_secret(otp_code), 0)

    # TODO: Reserve paid SMS quotas together with challenge creation using Redis
    # WATCH/MULTI/EXEC without Lua. Across login and phone changes, allow 10 sends
    # per validated destination in any 24 hours and 30 per trusted Nginx client IP
    # in any hour. Add a configurable global cap per Tehran calendar day to protect
    # provider credit. Rejected sends and verification consume no SMS quota.
    # Preserve the resend cooldown and verification attempt limit.
    # Atomic SET NX with expiration through django-redis.

    expires_at = None
    try:
        if workflow is not None:
            workflow, expires_at = _reserve_workflow_otp(
                cache_key, challenge, workflow, restart=purpose == OTPPurpose.OLD_PHONE
            )
        elif not cache.add(cache_key, challenge, timeout=settings.OTP_EXPIRY_SECONDS):
            raise APIError(OTPError.OTP_ALREADY_ACTIVE, retry_after=_retry_after(cache.pttl(cache_key)))
    except RedisError:
        raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)

    if not settings.IS_PRODUCTION:
        return

    def publish_sms():
        from core.sms_task import send_sms_verification_task

        try:
            send_sms_verification_task.delay(phone_number, otp_code)
        except EncodeError:
            if workflow is None:
                delete_if_unchanged(cache_key, challenge)
            else:
                _cancel_unsent_workflow_otp(cache_key, challenge[0], workflow, expires_at)
            raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)
        except (OperationalError, RedisError):
            raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)

    if publish_after_commit:
        transaction.on_commit(publish_sms)
    else:
        publish_sms()


def verify_otp(
    *,
    phone_number: str,
    otp_code: str,
    purpose: OTPPurpose,
    user_id=None,
    workflow: OTPWorkflow | None = None,
) -> None:
    """Use the canonical phone number supplied by the caller."""

    cache_key = _otp_key(phone_number, purpose, user_id)

    flow_id = _phone_change_flow_id(purpose, user_id, workflow.expected if workflow else None)
    max_attempts = settings.OTP_MAX_ATTEMPTS
    original_challenge_id = None

    for _ in range(MAX_WATCH_RETRIES + 1):
        executing = False
        try:
            client = cache.client.get_client(write=True)
            key = cache.make_key(cache_key)
            with client.pipeline() as pipe:

                # Monitor the key before reading it.
                pipe.watch(key)
                if workflow is not None:
                    workflow.watch(pipe)

                raw_challenge = pipe.get(key)

                if raw_challenge is None:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                challenge = cache.client.decode(raw_challenge)

                # Reject records using the previous storage format.
                if not isinstance(challenge, tuple) or len(challenge) != 3:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                challenge_id, stored_hash, failures = challenge
                if flow_id is not None:
                    if not isinstance(challenge_id, tuple) or len(challenge_id) != 2 or challenge_id[0] != flow_id:
                        raise APIError(OTPError.OTP_NOT_FOUND)
                if original_challenge_id is None:
                    original_challenge_id = challenge_id
                elif challenge_id != original_challenge_id:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                if failures >= max_attempts:
                    ttl_ms = pipe.pttl(key)
                    if ttl_ms == -2:
                        raise APIError(OTPError.OTP_NOT_FOUND)
                    raise APIError(OTPError.OTP_ATTEMPTS_EXHAUSTED, retry_after=_retry_after(ttl_ms))

                # Already consumed.
                if stored_hash is None:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                valid = (
                    isinstance(otp_code, str)
                    and len(otp_code) == 6
                    and otp_code.isascii()
                    and otp_code.isdigit()
                    and verify_secret(otp_code, stored_hash)
                )

                if valid:
                    # Consume the OTP but preserve its resend cooldown.
                    updated_challenge = (challenge_id, None, failures)
                else:
                    failures += 1
                    updated_challenge = (challenge_id, None if failures >= max_attempts else stored_hash, failures)

                # Queue the conditional update.
                pipe.multi()
                pipe.set(key, cache.client.encode(updated_challenge), xx=True, keepttl=True)
                pipe.pttl(key)
                if valid and workflow is not None:
                    workflow.advance(pipe)

                # Redis commits only if the watched key is unchanged.
                executing = True
                updated, ttl_ms = pipe.execute()[:2]
                executing = False

                if not updated:
                    raise APIError(OTPError.OTP_NOT_FOUND)

                if valid:
                    return

                if failures >= max_attempts:
                    raise APIError(OTPError.OTP_ATTEMPTS_EXHAUSTED, retry_after=_retry_after(ttl_ms))

                raise APIError(OTPError.OTP_INVALID)

        except RedisError as exc:
            if executing:
                if _is_watch_conflict(exc):
                    continue
            raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)

    raise APIError(OTPError.OTP_SERVICE_UNAVAILABLE)
