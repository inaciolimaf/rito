#!/usr/bin/env bash
# CI wall-clock gate (CLAUDE.md §3): fails when the whole run, from its start to this
# step, lasted more than CI_WALL_CLOCK_BUDGET seconds. Queue time is included on purpose:
# it is what the person waiting for the run actually sees. Run by `make ci-gate`.
set -uo pipefail

budget="${CI_WALL_CLOCK_BUDGET:-300}"
start=$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID/attempts/$GITHUB_RUN_ATTEMPT" --jq .run_started_at) || {
	echo "::error::could not read the run start time from the GitHub API" >&2
	exit 1
}
total=$(($(date +%s) - $(date -d "$start" +%s)))
echo "run took ${total}s (budget: ${budget}s)"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
	{
		echo "### Tempo do CI"
		echo "Run inteiro, da abertura do run até este passo: ${total} s (orçamento ${budget} s)."
		if [ -f test-timing.json ]; then
			echo '```json'
			cat test-timing.json
			echo '```'
		fi
	} >>"$GITHUB_STEP_SUMMARY"
fi

if [ "$total" -gt "$budget" ]; then
	echo "::error::CI took ${total}s; the limit is ${budget}s"
	exit 1
fi
