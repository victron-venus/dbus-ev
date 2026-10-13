"""HTTPS transport for the optional Home Assistant requests backend."""

from urllib.parse import urljoin, urlsplit

from requests.adapters import HTTPAdapter
from requests.exceptions import SSLError

from .tls_policy import client_context


class VerifiedHTTPSAdapter(HTTPAdapter):
    """Use one owned TLS context for direct and proxied HTTPS connections."""

    def __init__(self):
        self._context = client_context()
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["ssl_context"] = self._context
        return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs["ssl_context"] = self._context
        proxy_kwargs["proxy_ssl_context"] = self._context
        return super().proxy_manager_for(proxy, **proxy_kwargs)

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        if verify is False:
            raise ValueError("HTTPS certificate verification cannot be disabled")
        host, pool_kwargs = super().build_connection_pool_key_attributes(request, verify, cert)
        pool_kwargs["ssl_context"] = self._context
        return host, pool_kwargs

    def send(self, request, **kwargs):
        response = super().send(request, **kwargs)
        if (
            response.is_redirect
            and urlsplit(urljoin(request.url, response.headers["location"])).scheme != "https"
        ):
            response.close()
            raise SSLError("HTTPS redirect to plaintext is not allowed")
        return response
