#!/usr/bin/env bash
set -euo pipefail

CERT_FILE="${1:?certificate path is required}"
KEY_FILE="${2:?private-key path is required}"
TLS_HOST="${3:?TLS hostname is required}"
MIN_VALIDITY_SECONDS="${4:?minimum validity seconds is required}"
ALLOW_SELF_SIGNED_LOCAL="${5:-false}"
# Test/staging may pass a private CA explicitly. Production leaves this empty
# and OpenSSL uses the host public trust store.
CA_FILE="${6:-}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to validate direct-edge TLS material." >&2
  exit 1
fi
if [ ! -s "$CERT_FILE" ] || [ ! -s "$KEY_FILE" ]; then
  echo "TLS certificate or private key is missing/empty." >&2
  exit 1
fi
if ! [[ "$MIN_VALIDITY_SECONDS" =~ ^[0-9]+$ ]] || [ "$MIN_VALIDITY_SECONDS" -lt 3600 ]; then
  echo "minimum validity must be an integer of at least 3600 seconds." >&2
  exit 1
fi
if [ "$ALLOW_SELF_SIGNED_LOCAL" != "true" ] && [ "$ALLOW_SELF_SIGNED_LOCAL" != "false" ]; then
  echo "ALLOW_SELF_SIGNED_LOCAL must be true or false." >&2
  exit 1
fi

if ! openssl x509 -in "$CERT_FILE" -noout -checkend "$MIN_VALIDITY_SECONDS" >/dev/null; then
  echo "TLS certificate is invalid or expires inside the required safety window." >&2
  exit 1
fi

case "$TLS_HOST" in
  *:*) openssl x509 -in "$CERT_FILE" -noout -checkip "$TLS_HOST" >/dev/null ;;
  *[!0-9.]*) openssl x509 -in "$CERT_FILE" -noout -checkhost "$TLS_HOST" >/dev/null ;;
  *) openssl x509 -in "$CERT_FILE" -noout -checkip "$TLS_HOST" >/dev/null ;;
esac || {
  echo "TLS certificate does not cover the configured hostname." >&2
  exit 1
}

cert_public_key="$(openssl x509 -in "$CERT_FILE" -pubkey -noout | openssl pkey -pubin -outform DER 2>/dev/null | openssl dgst -sha256)"
key_public_key="$(openssl pkey -in "$KEY_FILE" -pubout -outform DER 2>/dev/null | openssl dgst -sha256)"
if [ -z "$cert_public_key" ] || [ "$cert_public_key" != "$key_public_key" ]; then
  echo "TLS certificate and private key do not match." >&2
  exit 1
fi

cert_subject="$(openssl x509 -in "$CERT_FILE" -noout -subject -nameopt RFC2253)"
cert_issuer="$(openssl x509 -in "$CERT_FILE" -noout -issuer -nameopt RFC2253)"
if [ "${cert_subject#subject=}" = "${cert_issuer#issuer=}" ]; then
  if [ "$ALLOW_SELF_SIGNED_LOCAL" != "true" ]; then
    echo "Self-signed TLS certificates are rejected for direct production." >&2
    exit 1
  fi
  case "$TLS_HOST" in
    localhost|127.0.0.1|::1) ;;
    *)
      echo "Self-signed override is restricted to a loopback hostname." >&2
      exit 1
      ;;
  esac
else
  verify_args=(-purpose sslserver -verify_hostname "$TLS_HOST" -untrusted "$CERT_FILE")
  if [ -n "$CA_FILE" ]; then
    verify_args=(-CAfile "$CA_FILE" "${verify_args[@]}")
  fi
  if ! openssl verify "${verify_args[@]}" "$CERT_FILE" >/dev/null; then
    echo "TLS certificate chain is not trusted by the selected CA store." >&2
    exit 1
  fi
fi

echo "Direct-edge TLS material validated for ${TLS_HOST}."
