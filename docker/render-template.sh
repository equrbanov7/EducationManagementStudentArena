#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — konteyner start-ında konfiq şablonu render edən köməkçi
# ═══════════════════════════════════════════════════════════════════════════
# 2026-09-14 infra auditi P3-8 (Alertmanager), P3-9 (Blackbox), P3-3 (Redis):
# əvvəl `sed -e "s|__X__|$X|g"` işlədilirdi — dəyərdə `|` (sed ayırıcısı),
# `&` (uyğun gələn mətn) və ya `\` olanda (Brevo SMTP açarı, webhook tokeni)
# render pozulur və Alertmanager qalxmır; parol isə `ps` çıxışında görünürdü.
# `envsubst` seçilmədi: prom/* (busybox) və redis:*-alpine image-lərində
# gettext yoxdur. Bu skript YALNIZ POSIX sh (busybox ash / dash / bash)
# imkanlarından istifadə edir — sed/awk-a ehtiyac yoxdur, xüsusi simvol yoxdur.
#
# İstifadə:  render-template.sh ŞABLON ÇIXIŞ DƏYİŞƏN [DƏYİŞƏN ...]
#   Şablondakı hər `__DƏYİŞƏN__` placeholder-i mühit dəyişəninin dəyəri ilə
#   əvəzlənir. Dəyər ikiqat dırnaq içində (`"__X__"`) yerləşdirilmək üçün
#   `\` → `\\` və `"` → `\"` kimi qaçırılır — YAML double-quoted skalyar və
#   redis.conf `"..."` argumenti üçün eyni qaydadır. Dırnaqsız placeholder
#   (`repeat_interval: __X__`) yalnız sadə token (24h, 6379) daşımalıdır.
#   Boş / təyin olunmamış dəyişən boş sətirlə əvəzlənir (köhnə sed davranışı).
# Test: tests/test_infra_monitoring_config.py (`|&/\"` daşıyan parol → keçərli YAML).
set -eu

if [ "$#" -lt 3 ]; then
  echo "usage: $0 TEMPLATE OUTPUT VAR [VAR...]" >&2
  exit 2
fi

template="$1"
output="$2"
shift 2

if [ ! -r "$template" ]; then
  echo "render-template: template not readable: $template" >&2
  exit 1
fi

# $1 mətnində $2 alt-sətrinin HƏR görünüşünü $3 ilə əvəz edir (hərfi, regex yox).
replace_all() {
  _in="$1"
  _needle="$2"
  _with="$3"
  _out=""
  while :; do
    case "$_in" in
      *"$_needle"*)
        _out="${_out}${_in%%"$_needle"*}${_with}"
        _in="${_in#*"$_needle"}"
        ;;
      *)
        break
        ;;
    esac
  done
  printf '%s' "${_out}${_in}"
}

# Dəyəri ikiqat-dırnaq konteksti üçün qaçırır: əvvəl `\`, sonra `"`.
escape_value() {
  _v="$(replace_all "$1" '\' '\\')"
  replace_all "$_v" '"' '\"'
}

tmp_output="${output}.tmp.$$"
: >"$tmp_output"

for name in "$@"; do
  case "$name" in
    *[!A-Z0-9_]*|"")
      echo "render-template: invalid variable name: $name" >&2
      rm -f "$tmp_output"
      exit 2
      ;;
  esac
done

while IFS= read -r line || [ -n "$line" ]; do
  for name in "$@"; do
    case "$line" in
      *"__${name}__"*)
        eval "raw=\${${name}:-}"
        line="$(replace_all "$line" "__${name}__" "$(escape_value "$raw")")"
        ;;
    esac
  done
  printf '%s\n' "$line" >>"$tmp_output"
done <"$template"

mv "$tmp_output" "$output"
