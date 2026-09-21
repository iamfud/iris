"""Network IP detection, LAN pairing URL, and QR code rendering for Iris server."""

import io
import socket


def lan_ip():
    """Best-effort primary LAN IPv4 address (route to default gateway)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def lan_url(is_loopback=False, port=15502, scheme="http"):
    """Panel URL a LAN device can open."""
    host = "127.0.0.1" if is_loopback else lan_ip()
    return f"{scheme}://{host}:{port}"


def lan_pair_url(token, is_loopback=False, port=15502, scheme="http"):
    """Pairing URL encoded in the on-screen QR code."""
    host = "127.0.0.1" if is_loopback else lan_ip()
    return f"{scheme}://{host}:{port}/pair?token={token}"


def qr_bytes(pair_url):
    """Render the one-time pairing URL as a QR code PNG."""
    try:
        import qrcode
    except ImportError:
        return None
    try:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(pair_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f1014", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None
