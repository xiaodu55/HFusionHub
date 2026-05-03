#!/usr/bin/env python3
"""generate-runner-tls.py — 生成 Plugin Runner TLS 证书（免 openssl）

等价于 scripts/generate-runner-tls.sh 的输出布局（Windows 无 openssl 时使用）：
  deploy/runner-tls/
    ca.pem / cert.pem / key.pem / server-cert.pem / server-key.pem
    dind-certs/server/{ca,cert,key}.pem
    dind-certs/client/{ca,cert,key}.pem

用法: python scripts/generate-runner-tls.py [output-dir]
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "deploy" / "runner-tls"
DAYS = 825
CA_DAYS = 3650


def _write_pem(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  {path.relative_to(OUT_DIR.parents[1])}")


def main() -> None:
    print(f"生成 Runner TLS 证书 -> {OUT_DIR}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hfusionhub-ca")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    client_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    client_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hfusionhub-plugin-runner")])
    client = (
        x509.CertificateBuilder()
        .subject_name(client_name)
        .issuer_name(ca_name)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hfusionhub-engine")])
    server = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("host.docker.internal"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    def enc(key: rsa.RSAPrivateKey) -> bytes:
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )

    ca_pem = ca.public_bytes(serialization.Encoding.PEM)
    client_pem = client.public_bytes(serialization.Encoding.PEM)
    server_pem = server.public_bytes(serialization.Encoding.PEM)

    _write_pem(OUT_DIR / "ca.pem", ca_pem)
    _write_pem(OUT_DIR / "cert.pem", client_pem)
    _write_pem(OUT_DIR / "key.pem", enc(client_key))
    _write_pem(OUT_DIR / "server-cert.pem", server_pem)
    _write_pem(OUT_DIR / "server-key.pem", enc(server_key))

    for sub in ("server", "client"):
        d = OUT_DIR / "dind-certs" / sub
        _write_pem(d / "ca.pem", ca_pem)
        _write_pem(d / "cert.pem", server_pem if sub == "server" else client_pem)
        _write_pem(d / "key.pem", enc(server_key) if sub == "server" else enc(client_key))

    print("完成。配置 Docker daemon TLS 后按 docs/PLUGIN_RUNNER_TLS.md 重启 runner。")


if __name__ == "__main__":
    main()
