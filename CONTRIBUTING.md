# Contributing

Bug reports and focused pull requests are welcome. Include the affected SWARM version, the observed behavior, the expected behavior, and the smallest safe reproduction. Remove credentials, private paths, prompts, customer data, task messages, and unrelated logs before submitting anything.

Keep changes narrow. Preserve outcome ownership, authority boundaries, independent review, and honest proof classes. Do not add hierarchy, configuration, dependencies, or compatibility paths for hypothetical use.

Before opening a pull request, run:

```text
python scripts/sync_plugin_mirror.py --check
python -m unittest discover -s skills/swarm/tests -p "test_*.py"
python -m unittest discover -s console/tests -p "test_console.py"
node --test console/tests/test_console_ui.mjs
```

The browser test requires Playwright. Contributions are submitted under the repository's [MIT License](LICENSE).

When changing the HQ bundle or literal pooler, also run `node skills/swarm/tests/test_compact_hq_literals.cjs <path-to-pinned-acorn.js>` with the Acorn digest required by `build_hq_app.py`.

For suspected vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
