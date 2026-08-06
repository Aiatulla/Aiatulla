import pytest
from fastapi import HTTPException

from app.rate_limit import RateLimiter


def test_requests_within_the_limit_pass():
    limiter = RateLimiter(max_requests=3, window_seconds=60)

    for _ in range(3):
        limiter.check("caller", now=0.0)


def test_the_request_over_the_limit_is_rejected():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.check("caller", now=0.0)
    limiter.check("caller", now=1.0)

    with pytest.raises(HTTPException) as caught:
        limiter.check("caller", now=2.0)

    assert caught.value.status_code == 429


def test_a_rejection_says_when_to_retry():
    """Without this a client can only guess, and guessing means hammering."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.check("caller", now=0.0)

    with pytest.raises(HTTPException) as caught:
        limiter.check("caller", now=10.0)

    assert caught.value.headers is not None
    assert int(caught.value.headers["Retry-After"]) > 0


def test_the_window_slides_rather_than_resetting():
    """A fixed window lets a caller send twice the limit across its boundary."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.check("caller", now=0.0)
    limiter.check("caller", now=30.0)

    # 61s: the first hit has expired, the second has not.
    limiter.check("caller", now=61.0)

    with pytest.raises(HTTPException):
        limiter.check("caller", now=62.0)


def test_callers_are_limited_independently():
    """One noisy caller must not lock everyone else out."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.check("first", now=0.0)

    limiter.check("second", now=0.0)

    with pytest.raises(HTTPException):
        limiter.check("first", now=1.0)


def test_expired_hits_are_discarded_rather_than_accumulating():
    """Read-time pruning is what keeps memory bounded without a background task."""
    limiter = RateLimiter(max_requests=5, window_seconds=10)

    for second in range(0, 100, 5):
        limiter.check("caller", now=float(second))

    assert len(limiter._hits["caller"]) <= 5
