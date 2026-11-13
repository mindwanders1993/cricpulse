#!/usr/bin/env bash
# ==============================================================================
# CricPulse M0b cloud: the owner's one command (task card M0b.10, dossier §5.10, D-13, D-14)
#
#   PROJECT_ID=… ALERT_EMAIL=… DEPLOYER_SA=… bash scripts/infra_m0b.sh [--dry-run] setup
#   PROJECT_ID=… bash scripts/infra_m0b.sh [--dry-run] first-build | bench | status | open
#
#   setup        before the first deploy: bucket, the job's and the API's accounts and their rights,
#                the API's access to the GEMINI_API_KEY secret, the job-failure email alert
#   first-build  after the deploy: the job's rights on the API service and on itself, one full
#                build, then the two schedules, only if the build succeeded
#   bench        run the bench job and print its output (D-3)
#   status       print LATEST.json from the bucket and /ready from the API service
#   open         the private API service on http://localhost:8080 (the chat page is /ui/)
#
# Re-runnable: creates what is missing and changes nothing that exists. --dry-run prints every
# gcloud command instead of running it. The project, the alert address and the deploy account
# come from the environment, so nothing personal is written into the repo. BUCKET (default
# cricpulse-data) names the bucket; set the same name as the repository variable BUCKET.
# ==============================================================================
set -euo pipefail

REGION="${REGION:-us-central1}" # M0b dossier D-13c
# M0b dossier §5.10; task card M0b.10 landing audit: bucket names are global, so it may be taken
BUCKET="${BUCKET:-cricpulse-data}"
GAR_REPO="cricpulse"            # the image registry .github/workflows/deploy.yml pushes to
SERVICE="cricpulse-api"
JOB="cricpulse-ingest"
BENCH_JOB="cricpulse-bench"     # M0b dossier D-13e
NIGHTLY="cricpulse-nightly"
SUNDAY="cricpulse-sunday-full"
TIME_ZONE="Asia/Kolkata"        # M0b dossier D-13d: the schedules are in IST
ALERT_NAME="cricpulse-ingest failed"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi
COMMAND="${1:-}"

usage() {
  sed -n '5,6p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}
case "$COMMAND" in
setup | first-build | bench | status | open) ;;
*) usage ;;
esac

: "${PROJECT_ID:?PROJECT_ID is required}"
JOB_SA="cricpulse-job@${PROJECT_ID}.iam.gserviceaccount.com"
API_SA="cricpulse-api@${PROJECT_ID}.iam.gserviceaccount.com"
RUN_JOB_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB}:run"

exec 3>&1 # the terminal: --dry-run prints here, even from inside $(…)

# Quote an argument for printing only when the shell would need it.
quote() {
  local safe='^[[:alnum:]_./:=@,+-]+$'
  if [[ "$1" =~ $safe ]]; then printf '%s' "$1"; else printf "'%s'" "$1"; fi
}

# Run gcloud on the project, or print the command under --dry-run.
gc() {
  if ((DRY_RUN)); then
    local a line="+ gcloud"
    for a in "$@" "--project=${PROJECT_ID}"; do line+=" $(quote "$a")"; done
    echo "$line" >&3
    return 0
  fi
  gcloud "$@" --project="$PROJECT_ID"
}

# True when the resource exists. Under --dry-run nothing is checked, so the create is printed too.
exists() {
  if ((DRY_RUN)); then
    gc "$@"
    return 1
  fi
  gcloud "$@" --project="$PROJECT_ID" >/dev/null 2>&1
}

note() { echo "= $*"; }

setup() {
  : "${ALERT_EMAIL:?ALERT_EMAIL is required for setup}"
  : "${DEPLOYER_SA:?DEPLOYER_SA is required for setup}"
  local created=0 sa channel policy

  gc services enable run.googleapis.com cloudscheduler.googleapis.com monitoring.googleapis.com \
    secretmanager.googleapis.com artifactregistry.googleapis.com iam.googleapis.com

  if exists storage buckets describe "gs://${BUCKET}"; then
    note "bucket gs://${BUCKET} exists"
  else
    gc storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access
  fi

  if exists artifacts repositories describe "$GAR_REPO" --location="$REGION"; then
    note "image registry ${GAR_REPO} exists"
  else
    gc artifacts repositories create "$GAR_REPO" --location="$REGION" --repository-format=docker
  fi

  for sa in "cricpulse-job:CricPulse nightly job" "cricpulse-api:CricPulse API service"; do
    if exists iam service-accounts describe "${sa%%:*}@${PROJECT_ID}.iam.gserviceaccount.com"; then
      note "account ${sa%%:*} exists"
    else
      gc iam service-accounts create "${sa%%:*}" --display-name="${sa#*:}"
      created=1
    fi
  done
  if ((created && !DRY_RUN)); then
    note "waiting 30 s for the new accounts to reach IAM"
    sleep 30
  fi

  # M0b dossier §5.10 and D-14b: rights per resource, never project-wide
  gc storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member="serviceAccount:${JOB_SA}" --role=roles/storage.objectAdmin
  gc storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member="serviceAccount:${API_SA}" --role=roles/storage.objectViewer
  gc secrets add-iam-policy-binding GEMINI_API_KEY \
    --member="serviceAccount:${API_SA}" --role=roles/secretmanager.secretAccessor
  for sa in "$JOB_SA" "$API_SA"; do
    gc iam service-accounts add-iam-policy-binding "$sa" \
      --member="serviceAccount:${DEPLOYER_SA}" --role=roles/iam.serviceAccountUser
  done

  # M0b dossier Q-1: a failed job execution sends an email
  channel=$(gc alpha monitoring channels list --filter="displayName=\"${ALERT_NAME}\"" --format='value(name)')
  if [[ -n "$channel" ]]; then
    note "alert email channel exists"
  else
    channel=$(gc alpha monitoring channels create --display-name="$ALERT_NAME" --type=email \
      --channel-labels="email_address=${ALERT_EMAIL}" --format='value(name)')
    if ((DRY_RUN)); then channel="projects/${PROJECT_ID}/notificationChannels/NEW"; fi
  fi
  policy=$(gc alpha monitoring policies list --filter="displayName=\"${ALERT_NAME}\"" --format='value(name)')
  if [[ -n "$policy" ]]; then
    note "alert policy exists"
  else
    gc alpha monitoring policies create --policy="$(
      cat <<JSON
{
  "displayName": "${ALERT_NAME}",
  "combiner": "OR",
  "conditions": [{
    "displayName": "An execution of ${JOB} failed",
    "conditionThreshold": {
      "filter": "resource.type = \"cloud_run_job\" AND resource.labels.job_name = \"${JOB}\" AND metric.type = \"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result = \"failed\"",
      "aggregations": [{"alignmentPeriod": "300s", "perSeriesAligner": "ALIGN_SUM"}],
      "comparison": "COMPARISON_GT",
      "thresholdValue": 0,
      "duration": "0s"
    }
  }],
  "notificationChannels": ["${channel}"]
}
JSON
    )"
  fi
  note "setup done: next, run the deploy workflow, then: bash scripts/infra_m0b.sh first-build"
}

# Create a schedule that starts the job, unless it exists. Arguments: name, cron, request body.
schedule() {
  if exists scheduler jobs describe "$1" --location="$REGION"; then
    note "schedule $1 exists"
    return 0
  fi
  gc scheduler jobs create http "$1" --location="$REGION" --schedule="$2" --time-zone="$TIME_ZONE" \
    --uri="$RUN_JOB_URI" --http-method=POST --headers=Content-Type=application/json \
    --message-body="$3" --oauth-service-account-email="$JOB_SA"
}

first_build() {
  # M0b dossier D-14b: the job's account may update the API service only, as the API's account
  gc run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
    --member="serviceAccount:${JOB_SA}" --role=roles/run.developer
  gc iam service-accounts add-iam-policy-binding "$API_SA" \
    --member="serviceAccount:${JOB_SA}" --role=roles/iam.serviceAccountUser
  # M0b dossier D-14b: the schedules run as the job's account, which may start this job only,
  # with the Sunday run's override
  gc run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
    --member="serviceAccount:${JOB_SA}" --role=roles/run.jobsExecutorWithOverrides

  # M0b dossier D-14b: the first full build; a failure stops the script here, before any schedule
  gc run jobs execute "$JOB" --region="$REGION" --args=run,--archive,all_json --wait

  # M0b dossier D-13d: Mon-Sat 02:00 IST the nightly archive, Sunday 03:00 IST the full one
  schedule "$NIGHTLY" "0 2 * * 1-6" '{}'
  schedule "$SUNDAY" "0 3 * * 0" '{"overrides":{"containerOverrides":[{"args":["run","--archive","all_json"]}]}}'
  note "first build done: bash scripts/infra_m0b.sh status"
}

bench() {
  local since out
  since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  gc run jobs execute "$BENCH_JOB" --region="$REGION" --wait
  # Cloud Logging shows a job's output a little after the job ends: look for a minute
  for _ in 1 2 3 4 5 6; do
    out=$(gc logging read "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${BENCH_JOB}\" AND timestamp>=\"${since}\"" \
      --order=asc --format='value(textPayload)')
    if ((DRY_RUN)) || [[ "$out" == *"D-3:"* ]]; then break; fi
    sleep 10
  done
  if [[ -n "$out" ]]; then echo "$out" | grep -v '^$'; fi
  if ((!DRY_RUN)) && [[ "$out" != *"D-3:"* ]]; then
    echo "The bench output is not in Cloud Logging yet: see the ${BENCH_JOB} job's logs in the console." >&2
    return 1
  fi
}

status() {
  local url token
  note "LATEST.json in gs://${BUCKET}:"
  gc storage cat "gs://${BUCKET}/snapshots/LATEST.json"
  url=$(gc run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')
  # Task card M0b.10 landing audit: the service is private, so /ready is called as the owner
  token=$(gc auth print-identity-token)
  note "/ready on ${SERVICE}:"
  if ((DRY_RUN)); then
    echo "+ curl -s -H 'Authorization: Bearer \$TOKEN' \$URL/ready" >&3
  else
    curl -s -H "Authorization: Bearer ${token}" "${url}/ready"
    echo
  fi
}

open_service() {
  # Task card M0b.10 landing audit: the private service reached through the owner's own sign-in
  note "chat page on http://localhost:8080/ui/ (Ctrl-C stops the proxy)"
  gc run services proxy "$SERVICE" --region="$REGION" --port=8080
}

case "$COMMAND" in
setup) setup ;;
first-build) first_build ;;
bench) bench ;;
status) status ;;
open) open_service ;;
*) usage ;;
esac
