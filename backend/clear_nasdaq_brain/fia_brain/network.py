from __future__ import annotations
import ipaddress
import socket
import urllib.parse
import urllib.request

class NetworkPolicyError(RuntimeError):
    pass


def assert_loopback_url(url: str) -> None:
    p=urllib.parse.urlparse(str(url))
    if p.scheme != "http":
        raise NetworkPolicyError("local-only policy requires http")
    if p.username or p.password or p.query or p.fragment:
        raise NetworkPolicyError("credentials/query/fragment forbidden in base URL")
    host=p.hostname
    if not host:
        raise NetworkPolicyError("URL host missing")
    if host.lower()=="localhost":
        return
    try:
        ip=ipaddress.ip_address(host)
        if ip.is_loopback:
            return
    except ValueError:
        pass
    try:
        infos=socket.getaddrinfo(host,p.port or 80,type=socket.SOCK_STREAM)
        addrs={x[4][0] for x in infos}
        if addrs and all(ipaddress.ip_address(a).is_loopback for a in addrs):
            return
    except Exception:
        pass
    raise NetworkPolicyError("remote host blocked by local-only policy")


def no_proxy_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))
