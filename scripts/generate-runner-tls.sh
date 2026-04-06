#!/bin/sh
set -eu

OUT_DIR="${1:-deploy/runner-tls}"
MODE="${2:-generate}"
DAYS=825
CA_DAYS=3650
CN="${TLS_CLIENT_CN:-hfusionhub-plugin-runner}"
SERVER_SAN="${TLS_SERVER_SAN:-DNS:host.docker.internal,DNS:localhost,IP:127.0.0.1}"

mkdir -p "$OUT_DIR"

materialize_dind_layout() {
  for file in ca.pem cert.pem key.pem server-cert.pem server-key.pem; do
    if [ ! -s "$OUT_DIR/$file" ]; then
      echo "::error::missing TLS file: $OUT_DIR/$file" >&2
      exit 1
    fi
  done
  dind_dir="$OUT_DIR/dind-certs"
  mkdir -p "$dind_dir/server" "$dind_dir/client"
  cp "$OUT_DIR/ca.pem" "$dind_dir/server/ca.pem"
  cp "$OUT_DIR/server-cert.pem" "$dind_dir/server/cert.pem"
  cp "$OUT_DIR/server-key.pem" "$dind_dir/server/key.pem"
  cp "$OUT_DIR/ca.pem" "$dind_dir/client/ca.pem"
  cp "$OUT_DIR/cert.pem" "$dind_dir/client/cert.pem"
  cp "$OUT_DIR/key.pem" "$dind_dir/client/key.pem"
  chmod 700 "$dind_dir" "$dind_dir/server" "$dind_dir/client"
  chmod 600 "$dind_dir/server/key.pem" "$dind_dir/client/key.pem"
  chmod 644 "$dind_dir/server/ca.pem" "$dind_dir/server/cert.pem" \
            "$dind_dir/client/ca.pem" "$dind_dir/client/cert.pem"
}

if [ "$MODE" = "--dind-layout" ]; then
  materialize_dind_layout
  exit 0
fi
if [ "$MODE" != "generate" ]; then
  echo "usage: $0 [output-dir] [--dind-layout]" >&2
  exit 2
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "::error::openssl is required to generate runner TLS certificates" >&2
  exit 1
fi

openssl genrsa -out "$OUT_DIR/ca-key.pem" 4096
openssl req -x509 -new -nodes -sha256 -days "$CA_DAYS" \
  -key "$OUT_DIR/ca-key.pem" -out "$OUT_DIR/ca.pem" \
  -subj "/CN=hfusionhub-ca"

openssl genrsa -out "$OUT_DIR/key.pem" 4096
openssl req -new -key "$OUT_DIR/key.pem" -out "$OUT_DIR/client.csr" \
  -subj "/CN=$CN"
printf '%s\n' 'extendedKeyUsage = clientAuth' > "$OUT_DIR/extfile.cnf"
openssl x509 -req -sha256 -days "$DAYS" -in "$OUT_DIR/client.csr" \
  -CA "$OUT_DIR/ca.pem" -CAkey "$OUT_DIR/ca-key.pem" -CAcreateserial \
  -out "$OUT_DIR/cert.pem" -extfile "$OUT_DIR/extfile.cnf"

openssl genrsa -out "$OUT_DIR/server-key.pem" 4096
openssl req -new -key "$OUT_DIR/server-key.pem" \
  -out "$OUT_DIR/server.csr" -subj "/CN=hfusionhub-engine"
printf 'extendedKeyUsage = serverAuth\nsubjectAltName = %s\n' "$SERVER_SAN" \
  > "$OUT_DIR/server-extfile.cnf"
openssl x509 -req -sha256 -days "$DAYS" -in "$OUT_DIR/server.csr" \
  -CA "$OUT_DIR/ca.pem" -CAkey "$OUT_DIR/ca-key.pem" -CAcreateserial \
  -out "$OUT_DIR/server-cert.pem" -extfile "$OUT_DIR/server-extfile.cnf"

rm -f "$OUT_DIR/client.csr" "$OUT_DIR/extfile.cnf" \
      "$OUT_DIR/server.csr" "$OUT_DIR/server-extfile.cnf"
chmod 600 "$OUT_DIR/key.pem" "$OUT_DIR/ca-key.pem" "$OUT_DIR/server-key.pem"
chmod 644 "$OUT_DIR/ca.pem" "$OUT_DIR/cert.pem" "$OUT_DIR/server-cert.pem"
materialize_dind_layout

echo "Runner TLS certificates generated in $OUT_DIR"
openssl x509 -in "$OUT_DIR/cert.pem" -noout -subject -dates
openssl x509 -in "$OUT_DIR/server-cert.pem" -noout -subject -ext subjectAltName
