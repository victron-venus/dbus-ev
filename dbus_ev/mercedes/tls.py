"""Mercedes HTTPS sessions reject redirects before any plaintext request."""

from urllib.parse import urljoin, urlsplit

import aiohttp

from dbus_ev.tls_policy import client_context


async def _check_redirect(_session, _context, params):
    location = params.response.headers.get("location", "")
    if urlsplit(urljoin(str(params.url), location)).scheme not in {"https", "wss"}:
        raise aiohttp.ClientError("Mercedes HTTPS redirect to plaintext is not allowed")


def session_options():
    trace = aiohttp.TraceConfig()
    trace.on_request_redirect.append(_check_redirect)
    return {"connector": aiohttp.TCPConnector(ssl=client_context()), "trace_configs": [trace]}
