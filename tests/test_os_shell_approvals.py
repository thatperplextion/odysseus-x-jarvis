"""ApprovalStore: single-use, expiring, owner-bound tokens for AI-originated actions."""

import pytest

from services.os_shell.approvals import ApprovalStore

pytestmark = pytest.mark.area_security


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_roundtrip_returns_the_stored_payload():
    s = ApprovalStore()
    token = s.create({"kind": "run", "command": "echo hi"}, owner="alice")
    assert s.take(token, owner="alice") == {"kind": "run", "command": "echo hi"}


def test_tokens_are_single_use():
    s = ApprovalStore()
    token = s.create({"x": 1}, owner="alice")
    assert s.take(token, owner="alice") == {"x": 1}
    assert s.take(token, owner="alice") is None


def test_tokens_are_unguessable_and_unique():
    s = ApprovalStore(max_pending=1000)
    tokens = {s.create({}) for _ in range(500)}
    assert len(tokens) == 500
    assert all(len(t) >= 24 for t in tokens)


@pytest.mark.parametrize("bad", [None, "", "nope", 123, ["x"], "A" * 24])
def test_unknown_or_malformed_tokens_redeem_nothing(bad):
    s = ApprovalStore()
    s.create({"x": 1})
    assert s.take(bad) is None  # type: ignore[arg-type]


def test_tokens_expire():
    clock = Clock()
    s = ApprovalStore(ttl_seconds=300, clock=clock)
    token = s.create({"x": 1})
    clock.t += 301
    assert s.take(token) is None


def test_token_is_still_valid_just_before_expiry():
    clock = Clock()
    s = ApprovalStore(ttl_seconds=300, clock=clock)
    token = s.create({"x": 1})
    clock.t += 299
    assert s.take(token) == {"x": 1}


def test_another_user_cannot_redeem_and_burns_the_token():
    s = ApprovalStore()
    token = s.create({"x": 1}, owner="alice")
    assert s.take(token, owner="mallory") is None
    # the probe consumed it, so even the rightful owner can't use it any more: fail closed
    assert s.take(token, owner="alice") is None


def test_ownerless_and_owned_tokens_do_not_cross():
    s = ApprovalStore()
    owned = s.create({"x": 1}, owner="alice")
    anon = s.create({"x": 2})
    assert s.take(owned) is None
    assert s.take(anon, owner="alice") is None


def test_store_is_bounded_and_drops_the_oldest():
    s = ApprovalStore(max_pending=3)
    tokens = [s.create({"i": i}) for i in range(5)]
    assert len(s) == 3
    assert s.take(tokens[0]) is None and s.take(tokens[1]) is None
    assert s.take(tokens[4]) == {"i": 4}


def test_expired_entries_are_purged_on_create():
    clock = Clock()
    s = ApprovalStore(ttl_seconds=10, clock=clock)
    for _ in range(5):
        s.create({})
    clock.t += 11
    s.create({})
    assert len(s) == 1


def test_expire_and_cancel():
    s = ApprovalStore()
    a = s.create({"x": 1}, owner="alice")
    s.expire(a)
    assert s.take(a, owner="alice") is None
    b = s.create({"x": 2}, owner="alice")
    assert s.cancel(b, owner="mallory") is False
    assert s.cancel(b, owner="alice") is True
    assert s.take(b, owner="alice") is None
