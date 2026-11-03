#!/usr/bin/env bash
# Goal cap — ported from HoppingCars (card P-4) on 3 Nov 2026.
#
# A Claude Code hook, wired in .claude/settings.json for two events. It reads the hook's JSON on stdin.
#   UserPromptSubmit   a prompt beginning "/goal " starts the count at 0; "/goal clear" ends it
#   PreToolUse         counts the session's tool calls; past the 40th only a Write or Edit under
#                      .agents/handoffs/ passes, five times at most — everything else exits 2
#
# State is one small file per session, ${TMPDIR:-/tmp}/cricpulse-goal-cap/<session_id>:
# line 1 the tool calls counted, line 2 the handoff writes let through past the cap.
#
# The hook's own fault never blocks a call: anything it cannot read or parse exits 0 (P-4 Build 3).

CAP=40            # the 40th tool call is the last
HANDOFF_WRITES=5  # five writes to .agents/handoffs/ at most, past the cap

TMP_ROOT="${TMPDIR:-/tmp}"
STATE_DIR="${TMP_ROOT%/}/cricpulse-goal-cap"

input=$(cat 2>/dev/null) || exit 0

# The governor's session pays this on every tool call (P-4 Build 1): decide in the shell, without
# starting python, whenever there is nothing to do. A quote inside a JSON string is escaped, so these
# patterns only ever match a real key.
re_ev='"hook_event_name"[[:space:]]*:[[:space:]]*"([A-Za-z]+)"'
re_sid='"session_id"[[:space:]]*:[[:space:]]*"([A-Za-z0-9_-]+)"'
[[ "$input" =~ $re_ev ]] || exit 0
case "${BASH_REMATCH[1]}" in
  PreToolUse)
    [[ "$input" =~ $re_sid ]] || exit 0
    [ -f "$STATE_DIR/${BASH_REMATCH[1]}" ] || exit 0
    ;;
  UserPromptSubmit)
    case "$input" in *'/goal'*) ;; *) exit 0 ;; esac
    ;;
  *) exit 0 ;;
esac

# The real parse. Prints "<event> <session_id> <set|clear|none> <1|0>" — the last is 1 for a Write or
# Edit whose file_path lies under .agents/handoffs/ — or nothing at all when the input is not a hook's.
PARSE='
import json, os, re, sys
try:
    d = json.load(sys.stdin)
    ev, sid = d.get("hook_event_name"), d.get("session_id")
    if not (isinstance(ev, str) and re.fullmatch(r"[A-Za-z]+", ev)):
        sys.exit(0)
    if not (isinstance(sid, str) and re.fullmatch(r"[A-Za-z0-9_-]+", sid)):
        sys.exit(0)
    goal, prompt = "none", d.get("prompt")
    if isinstance(prompt, str):
        if prompt.strip() == "/goal clear":
            goal = "clear"
        elif prompt.startswith("/goal "):
            goal = "set"
    handoff, ti = "0", d.get("tool_input")
    path = ti.get("file_path") if isinstance(ti, dict) else None
    if d.get("tool_name") in ("Write", "Edit") and isinstance(path, str) and path:
        cwd = d.get("cwd")
        if not (isinstance(cwd, str) and cwd):
            cwd = os.getcwd()
        full = os.path.normpath(os.path.join(cwd, path))
        for root in (os.environ.get("CLAUDE_PROJECT_DIR"), cwd):
            if root and full.startswith(os.path.normpath(root) + "/.agents/handoffs/"):
                handoff = "1"
    print(ev, sid, goal, handoff)
except Exception:
    pass
'
read -r ev sid goal handoff <<EOF
$(printf '%s' "$input" | python3 -I -c "$PARSE" 2>/dev/null)
EOF
[ -n "${sid:-}" ] || exit 0
state="$STATE_DIR/$sid"

if [ "$ev" = UserPromptSubmit ]; then
  case "$goal" in
    set)   mkdir -p "$STATE_DIR" 2>/dev/null && echo 0 > "$state" ;;
    clear) rm -f "$state" ;;
  esac
  exit 0
fi
[ "$ev" = PreToolUse ] || exit 0
[ -f "$state" ] || exit 0

# Tool calls sent in one message fire their hooks together: count them one at a time. A lock nobody
# releases is waited on for a second, then cleared, so one dead hook costs one slow call and no more.
lock="$state.lock"
tries=0
until mkdir "$lock" 2>/dev/null; do
  tries=$((tries + 1))
  if [ "$tries" -ge 100 ]; then rmdir "$lock" 2>/dev/null; break; fi
  sleep 0.01
done
trap 'rmdir "$lock" 2>/dev/null' EXIT

count="" used=""
{ read -r count; read -r used; } < "$state" 2>/dev/null
case "$count" in ''|*[!0-9]*) exit 0 ;; esac
case "$used" in ''|*[!0-9]*) used=0 ;; esac

save() {
  printf '%s\n%s\n' "$count" "$used" > "$state.new" 2>/dev/null && mv -f "$state.new" "$state" 2>/dev/null
}

count=$((count + 1))
if [ "$count" -le "$CAP" ]; then
  save
  exit 0
fi

if [ "$handoff" = 1 ] && [ "$used" -lt "$HANDOFF_WRITES" ]; then
  used=$((used + 1))
  save
  exit 0
fi

save
echo "Goal cap: 40 tool calls are spent. Write the handoff note at .agents/handoffs/<id>.md now and stop — a report headed BLOCKED also satisfies the goal. Nothing else runs." >&2
exit 2
