#!/usr/bin/env bash
# Sourced by the ProdDataOps route. Produces an argv array; never evals input.
cavid_source_batch_args() {
  local cavid_org="$1" cavid_actor="$2" cavid_batch="$3" cavid_apply="$4" cavid_tag="${5:-}"
  [[ "$cavid_org" == qku && -n "$cavid_actor" && -z "$cavid_tag" ]] || return 2
  args=(--org "$cavid_org" --actor "$cavid_actor" --source-sha256 3c87f7f625b57360522c0f3eb31a29dc464dea52edba0e0dc8b9137c5019f32f)
  if [[ "$cavid_batch" == cavid3536-* ]]; then
    local cavid_undo="${cavid_batch%%:*}"
    [[ "$cavid_undo" =~ ^cavid3536-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$ ]] || return 2
    args+=(--undo "$cavid_undo")
    if [[ "$cavid_batch" == *:* ]]; then
      local cavid_baseline="${cavid_batch#*:}"
      [[ "$cavid_baseline" =~ ^[0-9a-f]{64}$ ]] || return 2
      args+=(--expected-baseline "$cavid_baseline")
    else
      [[ "$cavid_apply" != true ]] || return 2
    fi
  elif [[ -n "$cavid_batch" ]]; then
    [[ "$cavid_batch" =~ ^[0-9a-f]{64}$ ]] || return 2
    args+=(--expected-baseline "$cavid_batch")
  else
    [[ "$cavid_apply" != true ]] || return 2
  fi
}
