# Jev decision routing

Use `python -B scripts/swarm_jev.py --status` to check local configuration without a provider call. The route requires the pinned CLI bundle, key and explicit shared spending cap. Availability is not connectivity proof.

Model selection is opt-in through `execution.jev_model_selection`. Build the
eligible set with `plan_jev_model_selection`, ask `model_profile.v1` only when it
returns at least two distinct model/reasoning pairs, then apply the advisory with
`resolve_jev_model_assignment`. Explicit user selections and model locks always
win. A disabled route, unavailable transport, abstention, or zero/one eligible
pair keeps the existing configured assignment without a provider call.

For one atomic classification, routing judgment or relevance score with supplied facts, invoke `python -B scripts/swarm_contract.py jev` with a JSON-stdin envelope containing `schema_id`, `state`, trusted `context`, unique opaque `decision_id`, and `final_decision` (null when no baseline exists). Closed schemas and fields live in runtime/jev_questions.py and runtime/jev_policy.py. Reuse the same decision ID after an uncertain attempt; a different ID is new billable work. The command selects the configured Jev transport only after deterministic policy and sanitization admit the decision.

When `selected_provider` is `jev`, consume the typed `suggestion` as the atomic result. It does not launch a worker or grant authorization. Keep an existing baseline unchanged. On unavailable, uncertain, low-confidence, exhausted or invalid results, continue the existing Codex/ChatGPT route. Coding, open-ended reasoning, protected work, proof and acceptance stay with their existing owners. Preserve explicit model choices. Avoid calls for deterministic work or simply because a new turn began.

Host configuration is JSON at `SWARM_JEV_CONFIG`, defaulting to the user's `.codex/swarm-jev.json`. Fields: mode (`off`, `auto`, `shadow`, `mock`), absolute node and entrypoint paths, reviewed bundle_sha256, absolute host-global budget_root, stable budget_scope, and cap_nanousd (integer; one dollar is one billion units). Config and budget root are host-owned, never fields in a decision payload. All projects must share one budget root. The key is `TYPESAFE_API_KEY` in the host environment; keep it out of source and config.

No automatic budget reset exists. Cap/scope changes require explicit host reconciliation; unknown attempts retain their full reservation. Version 1 pins jev-1.13.0 and the September 19 tariff: reserve 65536 input tokens at 42 nanodollars per token. Reverify pricing before paid activation. The reviewed upstream build disables retries. Missing configuration defaults off; a key alone cannot enable paid routing.

The integration uses the upstream MCP project's CLI `eval --stdin`, not an MCP client. A process deadline, isolated environment, fixed origin/model, payload limits and strict answer validation apply. Only curated public/approved summaries or synthetic fixtures are eligible. The lexical sanitizer is not universal DLP. Context is trusted host input, not external authority.

Public stdout excludes shadow answers. Optional `--telemetry` on swarm_jev.py emits analyst-only JSON on stderr; never merge it into model context during shadow measurement. Budget state retains only decision identity/digest and reserved/measured usage. Mock estimates are hypothetical; uncertain live cost is unknown. Measure total latency, fallback rates, tokens and outcome quality against the existing route before claiming savings.
