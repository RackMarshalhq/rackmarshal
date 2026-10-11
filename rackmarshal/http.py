"""HTTP(S) transport with explicit origins for credential-bearing requests.

Configured private and loopback endpoints are supported. Redirects may stay on
one origin only; callers must configure a different endpoint explicitly.
"""
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request


def _origin(url):
    """Validate before urllib normalizes input, returning its network origin."""
    if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise urllib.error.URLError("HTTP URL contains whitespace or control characters")
    if "\\" in url:
        raise urllib.error.URLError("HTTP URL contains a backslash")
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme.lower() not in ("http", "https"):
            raise ValueError("HTTP(S) URL required")
        if not parts.netloc or parts.username is not None or parts.password is not None:
            raise ValueError("HTTP URL requires a host and must not contain user information")
        host = parts.hostname
        port = parts.port
        if not host or parts.netloc.endswith(":") or "%" in host:
            raise ValueError("Invalid HTTP host or port")
        if ":" in host:
            if not re.fullmatch(r"\[[^\]]+\](?::[0-9]+)?", parts.netloc):
                raise ValueError("Invalid IPv6 authority")
            host = str(ipaddress.IPv6Address(host))
        else:
            host = host.encode("idna").decode("ascii").lower()
            if len(host) > 253 or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.rstrip(".").split(".")
            ):
                raise ValueError("Invalid HTTP host")
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Invalid HTTP port")
        return parts.scheme.lower(), host, port or (443 if parts.scheme.lower() == "https" else 80)
    except (ValueError, UnicodeError) as exc:
        # Do not echo configuration URLs, which may contain secrets.
        raise urllib.error.URLError("Invalid HTTP(S) destination") from exc


def validate_url(url):
    """Validate an initial URL without making a network request."""
    _origin(url)
    return url


class Request(urllib.request.Request):
    """Validate raw input before urllib's Request can strip characters."""

    def __init__(self, url, *args, **kwargs):
        validate_url(url)
        super().__init__(url, *args, **kwargs)


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            if _origin(req.full_url) != _origin(newurl):
                raise urllib.error.URLError("Cross-origin HTTP redirect refused")
        except urllib.error.URLError:
            if fp is not None:
                fp.close()
            raise
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def urlopen(url, data=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, *, context=None):
    """Open HTTP(S), preserving urllib timeout, proxy and TLS-context behavior.

    Uses a private opener so no process-wide handler is installed or inherited.
    Pass Request above when constructing a request from unvalidated input.
    """
    validate_url(url.full_url if isinstance(url, urllib.request.Request) else url)
    handlers = [_SameOriginRedirectHandler()]
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers).open(url, data=data, timeout=timeout)
