"""Transport evidence for calls that could not reach the provider."""

from httpx import ConnectError, ConnectTimeout, PoolTimeout, UnsupportedProtocol


def definitely_not_sent(error):
    """Read typed causes, never provider text, to prove no request was sent.

    Read/write timeouts, generic connection errors and HTTP responses do not
    provide this proof. Their reservations must remain held for accounting.
    """
    seen = set()
    while isinstance(error, Exception) and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, (ConnectError, ConnectTimeout, PoolTimeout, UnsupportedProtocol)):
            return True
        error = error.__cause__
    return False
