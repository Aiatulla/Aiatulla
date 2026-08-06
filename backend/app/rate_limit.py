import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

# A run clones a repository and makes several model calls, so it costs real disk,
# CPU and time even though the caller pays for the tokens. These bound how much
# of the server one caller can occupy.
MAX_RUNS_PER_WINDOW = 10
WINDOW_SECONDS = 60.0


class RateLimiter:
    """Sliding window limiter, keyed by client address.

    In-process and unsynchronised on purpose. A single worker is the current
    deployment, so a shared store would be infrastructure with nothing to
    coordinate.

    ponytail: per-process counters mean N workers allow N times the limit. Move
    the counter to Redis when the queue arrives in Stage 1, since that is the
    point where a second worker exists at all.
    """

    def __init__(
        self,
        max_requests: int = MAX_RUNS_PER_WINDOW,
        window_seconds: float = WINDOW_SECONDS,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_id: str, now: float | None = None) -> None:
        """Record a request and reject it if the caller is over the limit.

        :raises HTTPException: 429 with a Retry-After header when over the limit.
        """
        current = time.monotonic() if now is None else now
        hits = self._hits[client_id]

        # Drop everything that has fallen out of the window. Doing this on read
        # rather than on a timer means no background task and no unbounded growth
        # for callers who stop calling.
        cutoff = current - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self._max:
            retry_after = int(hits[0] + self._window - current) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many runs. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(current)

    def reset(self) -> None:
        """Forget every caller.

        The limiter is module-level state shared by the whole process, which
        leaks between tests unless each one starts clean.
        """
        self._hits.clear()


_limiter = RateLimiter()


def reset_rate_limits() -> None:
    """Clear the process-wide limiter. For tests and for a manual reset."""
    _limiter.reset()


def client_identifier(request: Request) -> str:
    """Identify the caller for rate limiting.

    The client address, never the API key. Keying on the key would mean holding
    someone's credential in an in-memory structure for the length of the window,
    which is exactly what this service otherwise refuses to do.

    Behind a proxy the direct address is the proxy's, so X-Forwarded-For is used
    when present. That header is caller-controlled and only trustworthy if a
    proxy you run overwrites it: do not deploy this without one.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency that rate limits by caller."""
    _limiter.check(client_identifier(request))
