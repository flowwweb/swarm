"""Advisory background hook: opt-in telemetry only, no workflow output."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/swarm/scripts"))
from swarm_telemetry import capture

if __name__ == "__main__":
    try:
        capture(json.load(sys.stdin))
    except (ValueError, OSError):
        pass
