"""Deploy/query the narrow Flowwweb beacon using existing Cloudflare credentials."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
ACCOUNT = "1876c7d50df7dfdb264f384179178bf1"
ZONE = "6a8e002cf1f938f8d9aec4fc1af0a436"
SCRIPT = "swarm-telemetry"
HOST = "telemetry.flowwweb.com"
ROUTE = HOST + "/api/swarm/telemetry"


def token():
    if os.environ.get("CLOUDFLARE_API_TOKEN"):
        return os.environ["CLOUDFLARE_API_TOKEN"]
    path = Path.home() / "AppData/Roaming/xdg.config/.wrangler/config/default.toml" if os.name == "nt" else Path.home() / ".config/.wrangler/config/default.toml"
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    if datetime.fromisoformat(config["expiration_time"].replace("Z", "+00:00")) <= datetime.now(timezone.utc) + timedelta(minutes=1):
        # Same OAuth refresh protocol and client ID as Cloudflare's workers-auth package.
        body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": config["refresh_token"],
                                       "client_id": "54d11594-84e4-41aa-b438-e81b8fa78ee7"}).encode()
        req = urllib.request.Request("https://dash.cloudflare.com/oauth2/token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "wrangler/4.20.0"})
        with urllib.request.urlopen(req, timeout=25) as response:
            refreshed = json.load(response)
        config.update(oauth_token=refreshed["access_token"], refresh_token=refreshed.get("refresh_token", config["refresh_token"]),
                      expiration_time=(datetime.now(timezone.utc) + timedelta(seconds=refreshed["expires_in"])).isoformat())
        if refreshed.get("scope"):
            config["scopes"] = refreshed["scope"].split()
        temporary = path.with_suffix(".swarm-refresh.tmp")
        temporary.write_text("\n".join(key + " = " + json.dumps(value) for key, value in config.items()) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    return config["oauth_token"]


def api(route, method="GET", data=None, content_type="application/json"):
    body = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request("https://api.cloudflare.com/client/v4/" + route, data=body, method=method,
        headers={"Authorization": "Bearer " + token(), "Content-Type": content_type, "User-Agent": "wrangler/4.20.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            value = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Cloudflare HTTP {error.code}: {error.read(4096).decode()}") from None
    if not value.get("success"):
        raise RuntimeError("Cloudflare rejected request: " + json.dumps(value.get("errors")))
    return value["result"]


def database():
    matches = [row for row in api(f"accounts/{ACCOUNT}/d1/database") if row["name"] == SCRIPT]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one swarm-telemetry D1 database")
    return matches[0]["uuid"]


def query(sql, params=None):
    return api(f"accounts/{ACCOUNT}/d1/database/{database()}/query", "POST", {"sql": sql, "params": params or []})


def deploy():
    routes = api(f"zones/{ZONE}/workers/routes")
    domains = api(f"accounts/{ACCOUNT}/workers/domains")
    match = [row for row in domains if row["hostname"] == HOST]
    if match and any(row.get("service") != SCRIPT for row in match):
        raise RuntimeError("Telemetry domain belongs to another Worker; preserved")
    databases = api(f"accounts/{ACCOUNT}/d1/database")
    matches = [row for row in databases if row["name"] == SCRIPT]
    dbid = matches[0]["uuid"] if len(matches) == 1 else api(f"accounts/{ACCOUNT}/d1/database", "POST", {"name": SCRIPT})["uuid"] if not matches else None
    if not dbid:
        raise RuntimeError("Ambiguous telemetry database")
    api(f"accounts/{ACCOUNT}/d1/database/{dbid}/query", "POST", {"sql": (ROOT / "schema.sql").read_text(encoding="utf-8")})
    metadata = {"main_module": "worker.mjs", "compatibility_date": "2026-10-02",
                "bindings": [{"type": "d1", "name": "DB", "id": dbid},
                             {"type": "ratelimit", "name": "LIMITER", "namespace_id": "202610021", "simple": {"limit": 60, "period": 60}}],
                "observability": {"enabled": False}}
    boundary = uuid.uuid4().hex
    parts = []
    for name, mime, payload in [("metadata", "application/json", json.dumps(metadata).encode()),
                                ("worker.mjs", "application/javascript+module", (ROOT / "worker.mjs").read_bytes())]:
        filename = f'; filename="{name}"' if name != "metadata" else ""
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"{filename}\r\nContent-Type: {mime}\r\n\r\n'.encode() + payload + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    result = api(f"accounts/{ACCOUNT}/workers/scripts/{SCRIPT}", "PUT", body, "multipart/form-data; boundary=" + boundary)
    api(f"accounts/{ACCOUNT}/workers/scripts/{SCRIPT}/schedules", "PUT", [{"cron": "17 3 * * *"}])
    if not match:
        api(f"accounts/{ACCOUNT}/workers/domains", "PUT", {"hostname": HOST, "service": SCRIPT, "zone_id": ZONE})
    obsolete = [row for row in routes if row["id"] == "1888d2fb95de4974aebe28a3a89593e8"
                and row["pattern"] == "flowwweb.com/api/swarm/telemetry" and row.get("script") == SCRIPT]
    for row in obsolete:
        api(f"zones/{ZONE}/workers/routes/{row['id']}", "DELETE")
    after = api(f"zones/{ZONE}/workers/routes")
    previous = {(row["id"], row["pattern"], row.get("script")) for row in routes if row not in obsolete}
    if not previous.issubset({(row["id"], row["pattern"], row.get("script")) for row in after}):
        raise RuntimeError("Existing route custody changed")
    return {"beacon": "https://" + ROUTE, "account": ACCOUNT, "database": dbid, "worker": SCRIPT,
            "deployment_id": result.get("deployment_id"), "existing_routes_preserved": True}


def summary(days):
    since = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    return {"days": days, "fleet": query("SELECT count(*) events, count(DISTINCT installation) installations, count(DISTINCT json_extract(payload,'$.session_id')) sessions FROM events WHERE received_at>=?", [since]),
            "activity": query("SELECT kind,version,count(*) events FROM events WHERE received_at>=? GROUP BY kind,version", [since]),
            "usage": query("SELECT json_extract(payload,'$.model') model,json_extract(payload,'$.effort') effort,count(*) samples,sum(json_extract(payload,'$.tokens.total_tokens')) tokens,sum(json_extract(payload,'$.cost_microusd'))/1000000.0 standard_api_equivalent_usd,sum(json_extract(payload,'$.cost_microusd') IS NULL) unpriced_samples FROM events WHERE kind='usage' AND received_at>=? GROUP BY model,effort", [since]),
            "tools": query("SELECT json_extract(payload,'$.tool') category,json_extract(payload,'$.success') success,count(*) events FROM events WHERE kind='tool' AND received_at>=? GROUP BY category,success", [since]),
            "claim_limits": "Client-reported metadata from consenting installations. Public ingress is not an attested census. Hook activity is not workflow compliance. Costs are conditional API equivalents, not billed charges."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["deploy", "summary", "query"])
    parser.add_argument("--days", type=int, choices=range(1, 91), default=7)
    parser.add_argument("--sql", help="Read-only SELECT for fleet analysis")
    args = parser.parse_args()
    if args.command == "query" and (not args.sql or not args.sql.lstrip().upper().startswith("SELECT ") or ";" in args.sql):
        parser.error("query requires one SELECT statement")
    print(json.dumps(deploy() if args.command == "deploy" else summary(args.days) if args.command == "summary" else query(args.sql), indent=2))
