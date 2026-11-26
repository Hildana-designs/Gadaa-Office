"""Start the web app over HTTPS on the office network."""
import datetime
import ipaddress
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.conf import settings
from django.core.management import BaseCommand


def local_ips():
    ips = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def ensure_certificate(cert_dir):
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert, key = cert_dir / "gadaa.crt", cert_dir / "gadaa.key"
    if cert.exists() and key.exists():
        return cert, key
    host = socket.gethostname()
    pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"GADAA Office ({host})")])
    alt = [x509.DNSName("localhost"), x509.DNSName(host), x509.DNSName(host.lower())]
    alt += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in local_ips()]
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(pk.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .sign(pk, hashes.SHA256())
    )
    key.write_bytes(pk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert, key


class Command(BaseCommand):
    help = "Run the app (HTTPS) for the office network."

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=None)

    def handle(self, *args, port=None, **options):
        import os
        import uvicorn

        port = port or int(os.environ.get("GADAA_PORT", "8443"))
        kwargs = {}
        if settings.GADAA_HTTPS:
            cert, key = ensure_certificate(settings.DATA_DIR / "certs")
            kwargs = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
        scheme = "https" if settings.GADAA_HTTPS else "http"
        for ip in local_ips():
            self.stdout.write(f"Open {scheme}://{ip}:{port} in the browser")
        uvicorn.run("gadaa.asgi:application", host="0.0.0.0", port=port, workers=1, log_level="info", **kwargs)
