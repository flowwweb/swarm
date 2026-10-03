"""Load the canonical SWARM workflow pointer at native task boundaries."""
import json
import hashlib
from pathlib import Path
import sys
import time


def main():
    started = time.perf_counter()
    event = json.load(sys.stdin)
    name = event.get("hook_event_name") if isinstance(event, dict) else None
    if name not in {"SessionStart", "SubagentStart"}:
        raise ValueError("SWARM activation requires SessionStart or SubagentStart")
    skill = Path(__file__).resolve().parents[1] / "skills/swarm/SKILL.md"
    if not skill.is_file():
        raise FileNotFoundError(skill)
    sys.path.insert(0, str(skill.parent / "scripts"))
    from swarm_mcp import DEFAULT_TELEMETRY, _telemetry
    context = (
        "SWARM is active for this Codex task. Before substantive work, read "
        f"{skill} and apply its workflow within this task's assigned role. "
        "CTRL is the switchboard operator: user conversation, bounded task intake, "
        "delegation, dependencies and result relay only. Every build, fix, test, "
        "review or release goes to an eligible owner, even a tiny edit; missing "
        "owners never permit CTRL fallback. Assigned LEAD/DOER agents keep their role. "
        "Explicit user instructions and opt-outs take precedence. "
        "Resolve the skill's relative references from its directory."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": name, "additionalContext": context,
    }}), flush=True)
    manifest = json.loads((skill.parents[2] / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    recorded = _telemetry(DEFAULT_TELEMETRY, tool="workflow_activation", started=started,
        ok=True, result_bytes=len(context.encode("utf-8")), activation={
            "hook_event": name,
            "session_hash": hashlib.sha256(str(event.get("session_id", "unknown")).encode()).hexdigest()[:16],
            "plugin_version": manifest["version"],
            "skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
        })
    if not recorded:
        print("SWARM activation telemetry unavailable", file=sys.stderr)


if __name__ == "__main__":
    main()
