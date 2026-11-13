#!/usr/bin/env python3
"""Register generated proof media for automatic SWARM console discovery."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))

from runtime.proof_events import ProofEventError, register_proof_event  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--caption", required=True)
    parser.add_argument("--claim-limit", default="Available for review; acceptance is recorded separately.")
    parser.add_argument("--console-url", default="http://127.0.0.1:4788")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    args = parser.parse_args()
    try:
        result = register_proof_event(
            args.codex_home,
            args.path,
            evidence_id=args.evidence_id,
            task_id=args.task_id,
            kind=args.kind,
            caption=args.caption,
            claim_limit=args.claim_limit,
        )
    except (OSError, ProofEventError) as exc:
        parser.error(str(exc))
    if Path(result["locator"]).is_absolute():
        from urllib.parse import urlparse
        parsed = urlparse(args.console_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            parser.error("console URL must be an explicit 127.0.0.1 HTTP origin")
        base = args.console_url.rstrip("/")
        try:
            with urllib.request.urlopen(base + "/api/bootstrap", timeout=5) as response:
                bootstrap = json.load(response)
            if not bootstrap.get("local_only") or not bootstrap.get("token"):
                raise ValueError("console did not provide local authorization")
            # A different configured home must never receive this source.
            if not bootstrap.get("codex_home") or Path(bootstrap["codex_home"]).expanduser().resolve() != args.codex_home.expanduser().resolve():
                raise ValueError("console does not match the requested Codex home")
            payload = json.dumps({**result, "acknowledge": True}).encode("utf-8")
            request = urllib.request.Request(base + "/api/evidence/original", data=payload,
                headers={"Content-Type": "application/json", "X-Swarm-Token": bootstrap["token"]}, method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:
                registered = json.load(response)
            if not registered.get("ok"):
                raise ValueError("console refused original proof")
        except urllib.error.HTTPError as exc:
            try:
                error = json.loads(exc.read(4097).decode("utf-8")) if exc.code == 400 else {}
            except (OSError, UnicodeError, json.JSONDecodeError):
                error = {}
            if isinstance(error, dict) and error.get("error") == "proof media requires an observed task":
                parser.error("original event saved but console registration failed: proof media requires an observed project-bound task")
            parser.error(f"original event saved but console registration failed: {exc}")
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            parser.error(f"original event saved but console registration failed: {exc}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
