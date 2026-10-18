# 08. Dependencies and Security

## Dependencies

1. **MUST** commit lockfiles (`package-lock.json`, `requirements.txt` with pins or a lock file) so builds are reproducible.
2. **MUST** automate dependency updates (Dependabot or equivalent) on a weekly schedule, with a cap on open PRs (for example five).
3. **MUST** run CI on bot PRs. Merging requires green checks and a human look at the changelog of major upgrades.
4. **SHOULD** group minor and patch updates to reduce noise; handle major updates individually.
5. **SHOULD** add a dependency only with a stated reason: what it does, why not the standard library, its maintenance status, its license.
6. **MUST** act on high-severity advisories promptly: a fix PR within a few working days, or a written exception.
7. **MUST NOT** pin to a floating reference in production (`latest`, a branch).

## Secrets

1. **MUST NOT** commit secrets, tokens, private keys, or `.env` files. Commit `.env.example` with placeholder values and document each variable.
2. **MUST** store secrets in the hosting platform's secret store (GitHub Actions secrets, or a vault). Separate **secrets** from **variables**: model names, ports, and URLs are variables.
3. **MUST** enable secret scanning and push protection where the host offers it.
4. **MUST** rotate a secret immediately if it was exposed, then remove it from history if feasible.
5. **MUST NOT** print secrets in CI logs. Avoid `set -x` around steps that use them.
6. **SHOULD** use distinct credentials per environment (integration versus production).
7. **SHOULD** apply least privilege to tokens and workflow `permissions`.

## Vulnerability Scanning

- **MUST** scan dependencies in CI at a defined threshold (start with `high`).
- **MUST** fail closed (guide 07): a scan that cannot run is a failure or an explicit, visible skip.
- **SHOULD** scan containers and base images if you ship them.
- **SHOULD** add static analysis for security (for example CodeQL or a linter ruleset) when the codebase handles authentication or untrusted input.

## Application Security Baseline

- Validate every external input against a schema (for example Pydantic in Python, a JSON schema, or TypeScript with runtime validation).
- Use framework protections for CSRF, CORS, and session handling. Do not roll your own cryptography.
- Treat user-uploaded or downloaded files as untrusted: sanitize names and paths, and limit sizes and types. MusicMatch's `sanitizer` and staging design are a good example.
- Log security-relevant events (login failures, permission denials) without logging secrets or personal data.

## Minimum Form

- Lockfiles committed.
- Dependabot configured, weekly.
- `.env` ignored, `.env.example` tracked.
- Dependency scan in CI that fails closed.

## Scale-up

- SBOM generation and license checks.
- Signed commits and signed release artifacts.
- Periodic penetration test before major launches.
- A `SECURITY.md` with a reporting contact.

## AI Note

- **Never** put secrets, customer data, or private source in prompts to an external model unless the provider terms and your policy allow it. Agent rules should state what must not be shared.
- Agents sometimes suggest or install packages that do not exist or are typosquats. Verify any new dependency an agent adds: name, publisher, download history.
- Agents may write secrets into example files, tests, or logs. Review the diff for tokens and keys, and let secret scanning catch the rest.
- Give agents scoped credentials, never an administrator token.

## Checklist

- [ ] Lockfile updated with the change.
- [ ] New dependency justified in the PR.
- [ ] No secrets, tokens, or personal data in the diff.
- [ ] Scan passed, or skip is visible and justified.
