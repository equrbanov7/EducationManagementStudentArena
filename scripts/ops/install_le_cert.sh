#!/usr/bin/env bash
# Let's Encrypt sertifikatını nginx-ə quraşdırır (prod-cert.yml install / renew addımları).
#
#   install_le_cert.sh <DOMAIN> <LE_DIR> <APP_DIR> [--if-changed]
#
# Addımlar (əvvəlki inline install addımı ilə eyni qoruyucular):
#   1) validate_direct_tls.sh: sertifikat ≥7 gün etibarlı, domenə uyğun, açar cütü düzgün, zəncir doğrulanır;
#   2) köhnə origin.{crt,key} → .bak-<ts>; yeniləri atomik mv ilə qoyulur;
#   3) `nginx -t` uğursuzdursa köhnə sertifikat QAYTARILIR və exit 1;
#   4) nginx reload; .env HEALTHCHECK_HOST=<domen>, TLS_ALLOW_SELF_SIGNED_LOCAL=false (.env.bak-cert-<ts>);
#   5) blackbox_exporter yenidən yaradılır (probe Host başlığı .env-dən).
# --if-changed: quraşdırılmış sertifikat eynidirsə (SHA-256 barmaq izi) heç nə etmir (renew üçün).
set -euo pipefail

DOMAIN="${1:?domain}"
LE_DIR="${2:?le dir}"
APP_DIR="${3:?app dir}"
IF_CHANGED="${4:-}"

cd "$APP_DIR"
src="$LE_DIR/config/live/$DOMAIN"
if [ ! -s "$src/fullchain.pem" ] || [ ! -s "$src/privkey.pem" ]; then
  echo "Sertifikat yoxdur: $src (əvvəl mode=issue-http)" >&2
  exit 1
fi

fingerprint() { openssl x509 -in "$1" -noout -fingerprint -sha256 2>/dev/null | cut -d= -f2; }
if [ "$IF_CHANGED" = "--if-changed" ] && [ -s docker/nginx/certs/origin.crt ] \
  && [ "$(fingerprint "$src/fullchain.pem")" = "$(fingerprint docker/nginx/certs/origin.crt)" ]; then
  echo "Quraşdırılmış sertifikat artıq ən sonuncudur — dəyişiklik yoxdur."
  exit 0
fi

bash scripts/deploy/validate_direct_tls.sh "$src/fullchain.pem" "$src/privkey.pem" "$DOMAIN" 604800 false "" lan

ts=$(date +%Y%m%d-%H%M%S)
cp -p docker/nginx/certs/origin.crt "docker/nginx/certs/origin.crt.bak-$ts"
cp -p docker/nginx/certs/origin.key "docker/nginx/certs/origin.key.bak-$ts"
chmod 600 "docker/nginx/certs/origin.key.bak-$ts"
cp -L "$src/fullchain.pem" docker/nginx/certs/origin.crt.new
cp -L "$src/privkey.pem" docker/nginx/certs/origin.key.new
chmod 644 docker/nginx/certs/origin.crt.new
chmod 600 docker/nginx/certs/origin.key.new
mv -f docker/nginx/certs/origin.crt.new docker/nginx/certs/origin.crt
mv -f docker/nginx/certs/origin.key.new docker/nginx/certs/origin.key

if ! docker compose -f docker-compose.prod.yml exec -T nginx nginx -t; then
  echo "nginx -t uğursuz — köhnə sertifikat qaytarılır" >&2
  cp -p "docker/nginx/certs/origin.crt.bak-$ts" docker/nginx/certs/origin.crt
  cp -p "docker/nginx/certs/origin.key.bak-$ts" docker/nginx/certs/origin.key
  exit 1
fi
docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload

cp -p .env ".env.bak-cert-$ts"
for kv in "HEALTHCHECK_HOST=$DOMAIN" "TLS_ALLOW_SELF_SIGNED_LOCAL=false"; do
  k="${kv%%=*}"
  if grep -qE "^$k=" .env; then sed -i "s#^$k=.*#$kv#" .env; else printf '\n%s\n' "$kv" >> .env; fi
  echo "  $kv"
done
chmod 600 .env
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate blackbox_exporter
echo "Sertifikat quraşdırıldı ($ts)."
