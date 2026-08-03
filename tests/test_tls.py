from ipaddress import ip_address

import datetime
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.tls import (
    extract_san_names,
    generate_self_signed_cert,
    ensure_self_signed_cert,
)


@pytest.mark.parametrize(
    "base_url, expected",
    [
        ("https://localhost", ["localhost", "127.0.0.1"]),
        ("https://localhost:443", ["localhost", "127.0.0.1"]),
        ("https://10.100.2.108", ["10.100.2.108"]),
        ("https://10.100.2.108:443", ["10.100.2.108"]),
        ("https://conf.local", ["conf.local"]),
        ("http://localhost", ["localhost", "127.0.0.1"]),
    ],
)
def test_extract_san_names_returns_host_with_loopback_for_localhost(base_url, expected):
    assert extract_san_names(base_url) == expected


def test_generate_self_signed_cert_returns_pem_with_correct_san():
    san_names = ["localhost", "127.0.0.1"]

    cert_pem, key_pem = generate_self_signed_cert(san_names)

    cert = x509.load_pem_x509_certificate(cert_pem)
    key = serialization.load_pem_private_key(key_pem, password=None)

    assert isinstance(key, rsa.RSAPrivateKey)
    san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    dns_names = san_ext.value.get_values_for_type(x509.DNSName)
    ip_names = san_ext.value.get_values_for_type(x509.IPAddress)
    assert "localhost" in dns_names
    assert ip_address("127.0.0.1") in ip_names


def test_ensure_self_signed_cert_persists_and_is_reused(tmp_path):
    storage_dir = tmp_path / "tls"
    san_names = ["localhost", "127.0.0.1"]

    cert_path, key_path = ensure_self_signed_cert(storage_dir, san_names)

    assert cert_path.exists()
    assert key_path.exists()
    # Second call reuses the same files (does not regenerate)
    cert_path_2, key_path_2 = ensure_self_signed_cert(storage_dir, san_names)
    assert cert_path_2 == cert_path
    assert key_path_2 == key_path
    # Key file has restrictive permissions (owner read/write only)
    mode = key_path.stat().st_mode & 0o777
    assert mode == 0o600


def _write_cert_with_expiry(storage_dir, san_names, *, days_valid_after: int) -> None:
    """Write a cert/key pair with a custom not_valid_after (days from now)."""
    storage_dir.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, san_names[0])])
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=365))
        .not_valid_after(now + datetime.timedelta(days=days_valid_after))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(n) for n in san_names]),
            critical=False,
        )
    )
    cert = builder.sign(private_key=key, algorithm=hashes.SHA256())
    (storage_dir / "cert.pem").write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
    )
    (storage_dir / "key.pem").write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    import os

    os.chmod(storage_dir / "key.pem", 0o600)


def test_ensure_self_signed_cert_regenerates_when_expired(tmp_path):
    """An expired cert (not_valid_after < now) is regenerated."""
    storage_dir = tmp_path / "tls"
    san_names = ["localhost"]
    _write_cert_with_expiry(storage_dir, san_names, days_valid_after=-1)

    cert_path, key_path = ensure_self_signed_cert(storage_dir, san_names)
    # The cert was regenerated — new cert has a future expiry (365 days).
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    expiry = cert.not_valid_after_utc
    assert expiry > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        days=300
    )


def test_ensure_self_signed_cert_regenerates_when_expiring_soon(tmp_path):
    """A cert expiring within 30 days is regenerated."""
    storage_dir = tmp_path / "tls"
    san_names = ["localhost"]
    _write_cert_with_expiry(storage_dir, san_names, days_valid_after=15)

    cert_path, _ = ensure_self_signed_cert(storage_dir, san_names)
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    expiry = cert.not_valid_after_utc
    # Regenerated — new expiry is far in the future.
    assert expiry > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        days=300
    )


def test_ensure_self_signed_cert_reuses_when_valid(tmp_path):
    """A cert valid for more than 30 days is reused (not regenerated)."""
    storage_dir = tmp_path / "tls"
    san_names = ["localhost"]
    _write_cert_with_expiry(storage_dir, san_names, days_valid_after=60)

    original_cert_bytes = (storage_dir / "cert.pem").read_bytes()
    cert_path, _ = ensure_self_signed_cert(storage_dir, san_names)
    # Same cert reused — bytes unchanged.
    assert cert_path.read_bytes() == original_cert_bytes


def test_ensure_self_signed_cert_regenerates_on_san_mismatch(tmp_path):
    """A cert with wrong SAN (but valid expiry) is regenerated."""
    storage_dir = tmp_path / "tls"
    _write_cert_with_expiry(
        storage_dir, ["localhost", "127.0.0.1"], days_valid_after=60
    )
    original_cert_bytes = (storage_dir / "cert.pem").read_bytes()

    cert_path, _ = ensure_self_signed_cert(storage_dir, ["10.0.0.1"])

    # Cert was regenerated — bytes changed.
    assert cert_path.read_bytes() != original_cert_bytes
    # New cert has the correct SAN.
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    ip_names = san_ext.value.get_values_for_type(x509.IPAddress)
    assert ip_address("10.0.0.1") in ip_names


def test_ensure_self_signed_cert_reuses_on_san_match(tmp_path):
    """A cert with matching SAN and valid expiry is reused."""
    storage_dir = tmp_path / "tls"
    san_names = ["localhost", "127.0.0.1"]
    _write_cert_with_expiry(storage_dir, san_names, days_valid_after=60)
    original_cert_bytes = (storage_dir / "cert.pem").read_bytes()

    cert_path, _ = ensure_self_signed_cert(storage_dir, san_names)
    assert cert_path.read_bytes() == original_cert_bytes


def test_ensure_self_signed_cert_regenerates_when_key_is_corrupt(tmp_path):
    """A valid cert with a corrupt key file is regenerated, not reused.

    A crash mid-write can leave a valid cert + partial/corrupt key. The reuse
    check must validate the key (not just the cert), otherwise the server
    starts with a broken SSL configuration and a cryptic uvicorn error.
    """
    storage_dir = tmp_path / "tls"
    san_names = ["localhost"]
    _write_cert_with_expiry(storage_dir, san_names, days_valid_after=60)
    # Corrupt the key file: valid cert, garbage key.
    (storage_dir / "key.pem").write_bytes(b"not a valid PEM key")
    original_cert_bytes = (storage_dir / "cert.pem").read_bytes()

    cert_path, key_path = ensure_self_signed_cert(storage_dir, san_names)

    # Both cert and key were regenerated — the corrupt key invalidated the pair.
    assert cert_path.read_bytes() != original_cert_bytes
    # Key was regenerated — it is now a loadable RSA private key.
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    # Key file keeps restrictive permissions.
    mode = key_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_ensure_self_signed_cert_regenerates_when_key_missing(tmp_path):
    """A valid cert with a missing key file is regenerated, not reused."""
    storage_dir = tmp_path / "tls"
    san_names = ["localhost"]
    _write_cert_with_expiry(storage_dir, san_names, days_valid_after=60)
    # Remove the key file: valid cert, no key.
    (storage_dir / "key.pem").unlink()

    cert_path, key_path = ensure_self_signed_cert(storage_dir, san_names)

    # Key was regenerated.
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
