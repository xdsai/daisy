"""Daisy - automated torrent download and media management."""

# This box's IPv6 routing is broken. Some hosts (e.g. letterboxd.com) now
# return AAAA records that the system resolver prefers, so outbound requests
# try the dead IPv6 path first and fail with "Network is unreachable". Force
# urllib3/requests to use IPv4 until IPv6 is fixed at the system level.
import socket as _socket
try:
    import urllib3.util.connection as _urllib3_conn
    _urllib3_conn.allowed_gai_family = lambda: _socket.AF_INET
except Exception:
    pass
