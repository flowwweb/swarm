# Contributing

Bug reports and focused pull requests are welcome. Include the affected RUSH version, the observed behavior, the expected behavior, and the smallest safe reproduction. Remove credentials, private paths, prompts, customer data, task messages, and unrelated logs before submitting anything.

Keep changes narrow. Preserve outcome ownership, authority boundaries, independent review, and honest proof classes. Do not add hierarchy, configuration, dependencies, or compatibility paths for hypothetical use.

Before opening a pull request, run:

```text
python -m unittest discover -s skills/rush/tests -p "test_*.py"
python -m unittest discover -s console/tests -p "test_console.py"
node --test console/tests/test_console_ui.mjs
```

The browser test requires Playwright. Contributions are submitted under the repository's [MIT License](LICENSE).

For suspected vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
