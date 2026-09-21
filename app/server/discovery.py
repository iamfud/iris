"""UDP discovery service for Iris server."""

import logging
import socket
import time

log = logging.getLogger("iris.server.discovery")


def start_udp_discovery(discovery_port=15503, http_port=15502, scheme="http"):
    """Listen for UDP broadcast queries ('IRIS_DISCOVER_REQ') and respond with server URL."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", discovery_port))
        log.info("UDP discovery listening on port %d", discovery_port)
    except Exception as e:
        log.warning("UDP discovery bind failed: %s", e)
        return

    from server.network import lan_ip as _lan_ip

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if data.strip() == b"IRIS_DISCOVER_REQ":
                ip = _lan_ip()
                resp = f"IRIS_DISCOVER_RESP|{scheme}://{ip}:{http_port}".encode("utf-8")
                sock.sendto(resp, addr)
        except Exception as e:
            log.warning("UDP discovery handle error: %s", e)
            time.sleep(0.5)
