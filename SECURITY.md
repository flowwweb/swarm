# Security

Report suspected vulnerabilities through [GitHub private vulnerability reporting](https://github.com/flowwweb/rush/security/advisories/new). If that channel is unavailable, contact the repository owner privately before sharing technical details.

Include the affected RUSH version, impact, prerequisites, and a minimal reproduction. Do not include live credentials, access tokens, private task content, customer data, or unrelated diagnostics. Use synthetic values and redact local paths.

Do not open a public issue until the repository owner confirms that disclosure is appropriate. Receipt, investigation, remediation, and disclosure timing are handled case by case; this document does not promise a response deadline or bounty.

RUSH reads local Codex metadata for its console and can write validated RUSH settings. Reports involving path handling, loopback isolation, request authorization, configuration writes, Docker mounts, or unintended data exposure are especially useful.
