#!/usr/bin/env bash
set -euo pipefail

required=(DB_USERNAME DB_PASSWORD CALLBACK_SECRET PYTHON_AI_INTERNAL_TOKEN ADMIN_PASSWORD)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 1
  fi
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${repo_root}"
exec mvn -f java-backend/pom.xml spring-boot:run -q
