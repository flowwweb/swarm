#!/usr/bin/env python3
"""Delegate one eligible typed judgment through the configured upstream Jev CLI."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.jev_adapter import JevDecisionAdapter
from runtime.jev_policy import Context, encode, parse_json, require
from runtime.jev_transport import JevBudget, JevCliTransport


def configured_adapter():
    # Host-owned config, never a field in the model/tool payload.
    configured = os.environ.get("SWARM_JEV_CONFIG")
    path = Path(configured) if configured else Path.home() / ".codex/swarm-jev.json"
    require(path.is_absolute(), "invalid_config")
    if not path.is_file():
        return JevDecisionAdapter()
    raw = path.read_bytes()
    require(len(raw) <= 8192, "invalid_config")
    config = parse_json(raw)
    require(type(config) is dict and set(config) == {"mode", "node", "entrypoint", "bundle_sha256", "budget_root", "budget_scope", "cap_nanousd"}, "invalid_config")
    require(config["mode"] in ("off", "auto", "shadow", "mock"), "invalid_config")
    if config["mode"] == "off":
        return JevDecisionAdapter()
    budget = JevBudget(config["budget_root"], config["budget_scope"], config["cap_nanousd"])
    transport = JevCliTransport(node=config["node"], entrypoint=config["entrypoint"],
        bundle_sha256=config["bundle_sha256"], budget=budget, mock=config["mode"] == "mock")
    return JevDecisionAdapter(mode="shadow" if config["mode"] == "shadow" else "advisory", transport=transport)


def route(envelope, adapter):
    require(type(envelope) is dict and set(envelope) == {"schema_id", "state", "context", "decision_id", "final_decision"}, "invalid_request")
    context = envelope["context"]
    require(type(context) is dict, "invalid_request")
    context = dict(context)
    if "allowed_options" in context:
        require(type(context["allowed_options"]) is list, "invalid_request")
        context["allowed_options"] = tuple(context["allowed_options"])
    return adapter.route_decision(envelope["schema_id"], envelope["state"], context=Context(**context),
        decision_id=envelope["decision_id"], final_decision=envelope["final_decision"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Local availability only; no provider ping or state write")
    parser.add_argument("--telemetry", action="store_true", help="Separate stderr JSON for a trusted analyst sink")
    args = parser.parse_args(argv)
    try:
        adapter = configured_adapter()
        if args.status:
            status = "off" if not adapter.enabled else adapter.transport.availability()
            print(encode({"status": status, "transport": "upstream_cli", "live_verified": False}).decode())
            return 0
        raw = sys.stdin.buffer.read(16385)
        require(len(raw) <= 16384, "invalid_request")
        public, event = route(parse_json(raw), adapter)
        print(encode(public).decode())
        if args.telemetry:
            print(encode(event).decode(), file=sys.stderr)
        return 0
    except Exception:
        print(encode({"status": "abstain", "reason": "configuration_or_input_invalid",
                      "selected_provider": "existing", "suggestion": None}).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
