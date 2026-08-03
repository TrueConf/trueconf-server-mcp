"""TLS helpers: self-signed certificate generation, SAN extraction, and
TLS file resolution for the MCP server bootstrap."""

import datetime
import logging
import os
import platform
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.config import Config

logger = logging.getLogger(__name__)


def extract_san_names(base_url: str) -> list[str]:
    """Extract SAN entries from the host part of a base URL.

    For "localhost" host, both "localhost" and "127.0.0.1" are returned so the
    cert works regardless of which form the client uses. For any other host
    (IP or domain) only that host is returned.
    """
    host = urlparse(base_url).hostname or ""
    if not host:
        raise ValueError(f"Could not parse host from base_url: {base_url!r}")
    if host == "localhost":
        return ["localhost", "127.0.0.1"]
    return [host]


def generate_self_signed_cert(san_names: list[str]) -> tuple[bytes, bytes]:
    """Generate a self-signed RSA certificate valid for the given SAN names.

    Returns (cert_pem, key_pem) as PEM-encoded bytes. DNS names and IP addresses
    in `san_names` are placed into the SubjectAlternativeName extension.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    dns_names: list[str] = []
    ip_addresses: list[ip_address] = []  # type: ignore[type-arg]
    for name in san_names:
        try:
            ip_addresses.append(ip_address(name))
        except ValueError:
            dns_names.append(name)

    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, san_names[0] if san_names else "mcp")]
    )
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    if dns_names or ip_addresses:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(n) for n in dns_names]
                + [x509.IPAddress(ip) for ip in ip_addresses]
            ),
            critical=False,
        )

    cert = builder.sign(private_key=key, algorithm=hashes.SHA256())

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def ensure_self_signed_cert(
    storage_dir: Path, san_names: list[str]
) -> tuple[Path, Path]:
    """Return (cert_path, key_path) for a self-signed cert, generating on first use.

    Idempotent: if both `cert.pem` and `key.pem` already exist in `storage_dir`
    AND the cert is valid for more than 30 days AND the key is loadable, they
    are reused. Otherwise (missing files, expired, expiring within 30 days, SAN
    mismatch, or corrupt/unreadable key) a new cert is generated and written.
    The key file is written atomically (temp → chmod 0600 → replace) and with
    restrictive permissions.
    """
    storage_dir.mkdir(parents=True, exist_ok=True)
    cert_path = storage_dir / "cert.pem"
    key_path = storage_dir / "key.pem"

    if cert_path.exists() and key_path.exists():
        not_valid_after = _cert_not_valid_after(cert_path)
        if (
            not_valid_after is not None
            and _is_cert_valid_for(cert_path, days=30)
            and _cert_san_matches(cert_path, san_names)
            and _is_key_loadable(key_path)
        ):
            logger.info("Reusing self-signed cert (expires %s)", not_valid_after)
            return cert_path, key_path
        logger.info(
            "Regenerating expired/expiring/SAN-mismatch/corrupt-key self-signed cert (was %s)",
            not_valid_after,
        )

    logger.info("Generated self-signed cert for %s at %s", san_names, cert_path)
    cert_pem, key_pem = generate_self_signed_cert(san_names)
    cert_path.write_bytes(cert_pem)
    # Write key atomically: temp file → chmod 0600 → os.replace. A crash
    # mid-write leaves either the old key or no key, never a partial key that
    # the reuse check above would silently accept. The temp file is created
    # with 0o600 directly (not chmod'd after) so the private key is never
    # world-readable, even briefly.
    tmp_key = key_path.with_suffix(".pem.tmp")
    try:
        fd = os.open(
            str(tmp_key),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(fd, "wb") as f:
            f.write(key_pem)
        os.replace(tmp_key, key_path)
    finally:
        tmp_key.unlink(missing_ok=True)
    return cert_path, key_path


def _cert_not_valid_after(cert_path: Path):
    """Return the cert's not_valid_after (timezone-aware), or None on error."""
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except Exception:
        return None
    not_valid_after = getattr(cert, "not_valid_after_utc", None)
    if not_valid_after is None:
        not_valid_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
    return not_valid_after


def _is_cert_valid_for(cert_path: Path, *, days: int) -> bool:
    """True if the cert at cert_path is still valid for at least `days` more days."""
    not_valid_after = _cert_not_valid_after(cert_path)
    if not_valid_after is None:
        return False
    return not_valid_after > datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(days=days)


def _cert_san_matches(cert_path: Path, expected_san_names: list[str]) -> bool:
    """True if the cert's SubjectAlternativeName matches expected_san_names."""
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except Exception:
        return False
    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return False
    actual_names: list[str] = []
    actual_names.extend(san_ext.value.get_values_for_type(x509.DNSName))
    actual_names.extend(
        str(ip) for ip in san_ext.value.get_values_for_type(x509.IPAddress)
    )
    return sorted(actual_names) == sorted(expected_san_names)


def _is_key_loadable(key_path: Path) -> bool:
    """True if the key file at key_path is a loadable PEM private key.

    Guards against a corrupt or partial key left by a crash mid-write — the
    reuse check in ``ensure_self_signed_cert`` calls this so a broken key
    triggers regeneration instead of a cryptic SSL startup error.
    """
    try:
        serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    except Exception:
        return False
    return True


def resolve_tls_files(config: Config) -> tuple[str, str] | None:
    """Resolve TLS cert/key paths for the server.

    Returns None when TLS is disabled (--no-tls). When custom cert/key paths
    are provided, they are used as-is. Otherwise a self-signed cert is
    generated (and persisted) from the host of `mcp_base_url`.
    """
    if config.no_tls:
        return None

    if config.tls_cert and config.tls_key:
        return config.tls_cert, config.tls_key

    from fastmcp import settings

    san_names = extract_san_names(config.mcp_base_url)
    storage_dir = settings.home / "tls"
    cert_path, key_path = ensure_self_signed_cert(storage_dir, san_names)
    return str(cert_path), str(key_path)


def bind_error_help(port: int) -> str:
    """Return a human-readable hint for privileged-port bind failures."""
    hint = (
        f"Failed to bind port {port}. "
        "Privileged ports (<1024) require elevated permissions."
    )

    if platform.system() == "Linux":
        hint += (
            " Grant the capability once with "
            "`sudo setcap cap_net_bind_service+ep $(which python)` "
            "(or run under `sudo`), or use a non-privileged port like "
            "`--port 8443`."
        )
    elif platform.system() == "Darwin":
        hint += (
            " Binding to 0.0.0.0 should work without root on macOS; if you are "
            "binding to a specific interface, run under `sudo` or use "
            "`--port 8443`."
        )
    else:
        hint += (
            " Run as Administrator, or use a non-privileged port like `--port 8443`."
        )
    return hint
