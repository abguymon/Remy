"""OAuth state TTL logic (PRD §6/§7.2 — 10-minute expiry)."""

from datetime import UTC, datetime, timedelta

from remy_api.models import OAUTH_STATE_TTL, OAuthState


def _state(created_at):
    return OAuthState(state="s", user_id="u", pkce_verifier="v", created_at=created_at)


def test_fresh_state_not_expired():
    assert _state(datetime.now(UTC)).is_expired() is False


def test_state_just_inside_ttl():
    created = datetime.now(UTC) - (OAUTH_STATE_TTL - timedelta(seconds=30))
    assert _state(created).is_expired() is False


def test_state_past_ttl_expired():
    created = datetime.now(UTC) - (OAUTH_STATE_TTL + timedelta(seconds=1))
    assert _state(created).is_expired() is True


def test_naive_timestamp_treated_as_utc():
    # SQLite returns naive datetimes; is_expired must not crash on them.
    naive = (datetime.now(UTC) - timedelta(minutes=20)).replace(tzinfo=None)
    assert _state(naive).is_expired() is True
