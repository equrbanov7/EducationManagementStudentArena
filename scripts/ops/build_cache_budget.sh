#!/usr/bin/env bash
# Manage only the local Docker Engine's build cache, under the production deploy lock.
set -euo pipefail
export LC_ALL=C
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_API_VERSION DOCKER_BUILDKIT BUILDX_BUILDER BUILDKIT_HOST

fail() { printf 'build-cache: %s\n' "$*" >&2; exit 1; }
mode=${1-budget}
[[ $# -le 1 && ( $mode == budget || $mode == clear-unused ) ]] || fail 'expected budget or clear-unused'
readonly budget_bytes=12884901888
readonly lock=/run/emsarena/deploy.lock
readonly socket=/var/run/docker.sock
engine=(docker --context default)

# Open the same existing inode as deploy and selfheal, without creating/truncating it.
[[ -f $lock && ! -L $lock ]] || fail 'production deploy lock missing or invalid'
exec 9<"$lock"
flock -n 9 || fail 'production deploy lock is held or unavailable'
python3 -c 'import os, sys; sys.exit(not os.path.samestat(os.fstat(9), os.stat(sys.argv[1], follow_symlinks=False)))' \
    "$lock" || fail 'production deploy lock changed'
endpoint=$("${engine[@]}" context inspect default --format '{{(index .Endpoints "docker").Host}}')
[[ $endpoint == "unix://$socket" ]] || fail 'default Docker context is not the local production socket'

# Some Docker CLIs dispatch `builder prune` to Buildx. Pin its named builder
# explicitly and verify its driver/endpoint before using the same daemon's counters.
help=$("${engine[@]}" builder prune --help)
[[ $help == *'--force'* ]] || fail 'unsupported Docker builder prune command'
prune=(builder prune --force)
[[ $help == *'docker builder prune'* || $help == *'docker buildx prune'* ]] || fail 'unrecognized Docker builder prune implementation'
if [[ $help == *'--builder '* ]]; then
    info=$("${engine[@]}" buildx inspect default)
    awk '$1=="Driver:" {drivers++; driver=$2} $1=="Endpoint:" {nodes++; endpoint=$2}
         END {exit !(drivers==1 && driver=="docker" && nodes==1 && endpoint=="default")}' <<<"$info" ||
        fail 'default builder is not the single local Docker driver node'
    prune+=(--builder default)
elif [[ $help == *'docker buildx prune'* ]]; then
    fail 'unable to pin the default Buildx builder'
fi
# Read cache accounting only. Requesting every object type can walk all volume contents.
cache_bytes() {
    curl --fail --silent --show-error --noproxy '*' --max-time 75 --unix-socket "$socket" \
        'http://localhost/v1.42/system/df?type=build-cache' |
        python3 -c '
import json, sys
rows = json.load(sys.stdin)["BuildCache"]
if rows is None:
    rows = []
if not isinstance(rows, list) or any(type(r.get("Size")) is not int or r["Size"] < 0 for r in rows):
    sys.exit("invalid Docker build cache sizes")
print(sum(r["Size"] for r in rows))'
}
disk_bytes() {
    df -B1 --output="$1" -- "$2" | awk 'NR==2 && NF==1 && $1~/^[0-9]+$/ {n=$1} END {if(n=="") exit 1; print n}'
}
image_map() {
    "${engine[@]}" image ls --no-trunc --format '{{.Tag}} {{.ID}}' emsarena-prod | sort
}
replica_map() {
    local ids replica
    local -a replicas=()
    ids=$("${engine[@]}" container ls -q --no-trunc --filter label=com.docker.compose.project=educationmanagementstudentarena \
        --filter label=com.docker.compose.service=app --filter label=com.docker.compose.oneoff=False) || return 1
    [[ -n $ids ]] || return 1
    while IFS= read -r replica; do
        [[ $replica =~ ^[0-9a-f]{64}$ ]] || return 1
        replicas+=("$replica")
    done <<<"$ids"
    "${engine[@]}" container inspect --format '{{.Id}} {{.Image}} {{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' \
        "${replicas[@]}" | sort
}

docker_root=$("${engine[@]}" info --format '{{.DockerRootDir}}')
[[ $docker_root == /* ]] || fail 'Docker data filesystem not identified'
images_before=$(image_map) || fail 'cannot read release images'
replicas_before=$(replica_map) || fail 'production app replicas unavailable'
release=''
latest=''
retained_shas=''
tag_count=0
rollback_count=0
while read -r tag id extra; do
    [[ $tag =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ && $id =~ ^sha256:[a-f0-9]{64}$ && -z $extra ]] || fail 'invalid release image map'
    tag_count=$((tag_count+1))
    if [[ $tag == latest ]]; then latest=$id; fi
done <<<"$images_before"
[[ -n $latest ]] || fail 'latest production image missing'
while read -r tag id; do
    if [[ $tag =~ ^[0-9a-f]{40}$ ]]; then
        retained_shas="${retained_shas:+$retained_shas,}$tag"
        if [[ $id == "$latest" ]]; then release=$tag; else rollback_count=$((rollback_count+1)); fi
    elif [[ $tag == manual-* && $id != "$latest" ]]; then rollback_count=$((rollback_count+1)); fi
done <<<"$images_before"
[[ -n $release && $rollback_count -ge 1 ]] || fail 'current SHA or a distinct rollback release unavailable'
replica_count=0
while read -r cid image running health extra; do
    [[ $cid =~ ^[0-9a-f]{64}$ && $image == "$latest" && $running == true && $health == healthy && -z $extra ]] ||
        fail 'app replica is unhealthy or differs from latest'
    replica_count=$((replica_count+1))
done <<<"$replicas_before"

before=$(cache_bytes) || fail 'cannot measure initial build cache'
free_before=$(disk_bytes avail "$docker_root") || fail 'cannot measure initial Docker filesystem space'
total=$(disk_bytes size "$docker_root") || fail 'cannot measure Docker filesystem capacity'
((total > 0 && free_before <= total)) || fail 'invalid Docker filesystem capacity'
pressure_cleanup=false
if [[ $mode == budget ]]; then
    if (( free_before <= total / 5 )); then
        pressure_cleanup=true
    elif [[ $help == *'--max-used-space '* ]]; then prune+=(--max-used-space "$budget_bytes")
    elif [[ $help == *'--keep-storage '* ]]; then prune+=(--keep-storage "$budget_bytes")
    else fail 'Docker CLI has no supported byte budget flag'; fi
fi
printf 'mode=%s\nbudget_target_bytes=%s\ncurrent_release_sha=%s\nprotected_release_tags=%s\nrollback_release_tags=%s\nhealthy_app_replicas=%s\n' \
    "$mode" "$budget_bytes" "$release" "$tag_count" "$rollback_count" "$replica_count"
printf 'cache_before_bytes=%s\nfilesystem_available_before_bytes=%s\n' "$before" "$free_before"
printf 'filesystem_total_bytes=%s\npressure_cleanup=%s\n' "$total" "$pressure_cleanup"

prune_status=0
if [[ $mode == clear-unused || $before -gt $budget_bytes || ( $pressure_cleanup == true && $before -gt 0 ) ]]; then
    # No --all: BuildKit excludes active, image-shared, internal and frontend records.
    # Raw per-record progress is not included in the operator report.
    "${engine[@]}" "${prune[@]}" >/dev/null || prune_status=$?
    printf 'prune_exit_status=%s\n' "$prune_status"
else
    echo 'prune_skipped=within_budget'
fi

# Verify the protected objects even after a partially successful Docker command.
images_after=$(image_map) || fail 'cannot recheck release images'
replicas_after=$(replica_map) || fail 'cannot recheck app replicas'
[[ $images_before == "$images_after" ]] || fail 'protected release tag-to-image mapping changed'
[[ $replicas_before == "$replicas_after" ]] || fail 'production app replica, image or health changed'
echo 'protected_release_tags_verified=true'
printf 'retained_release_shas=%s\n' "$retained_shas"
echo 'app_replicas_verified=true'
after=$(cache_bytes) || fail 'cannot measure final build cache'
free_after=$(disk_bytes avail "$docker_root") || fail 'cannot measure final Docker filesystem space'
printf 'cache_after_bytes=%s\ncache_reported_delta_bytes=%s\n' "$after" "$((before-after))"
printf 'filesystem_available_after_bytes=%s\nfilesystem_available_delta_bytes=%s\n' "$free_after" "$((free_after-free_before))"
if [[ $mode == budget ]]; then
    if ((after <= budget_bytes)); then echo 'budget_target_met=true'; else echo 'budget_target_met=false'; fi
    if ((free_after <= total / 5)); then echo 'filesystem_still_at_or_above_80_percent=true'; fi
fi
exit "$prune_status"
