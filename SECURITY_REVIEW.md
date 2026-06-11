# Security Review — LibPulse (T14)

Date: 2026-06-11. Scope: the unattended pipeline (watch → analyze → verify →
export → MCP serve) as it runs on the operator's machine. Status: reviewed
before any public publication of the corpus or server.

## Threat model

### 1. Execution of LLM-generated code (verifier)

The whole product is "run model-generated snippets and see what happens", so
this is inherent, not accidental.

- **In place:** snippets run in a subprocess with a scrubbed environment
  (`PATH`/`HOME`/`TMPDIR` only — no `ANTHROPIC_API_KEY`, no shell rc), a
  throwaway temp working directory, a hard 60s timeout, and output capped at
  2KB per stream. Snippets are never user-submitted; they originate from our
  own pipeline.
- **Residual risk:** no network isolation and no filesystem sandbox beyond the
  cwd — a malicious snippet could read world-readable files or exfiltrate over
  the network. Reachable via threat #3 (prompt injection).
- **Action (T14a, before scale-up beyond the curated list):** run snippets
  network-less (e.g. `unshare -rn`, container, or seccomp wrapper).

### 2. Supply chain via pip installs of watched packages

`verify` installs real PyPI packages into venvs.

- **In place:** package names come only from the curated `data/packages.txt`
  (no user input, no typosquat surface); installs are now **wheels-only**
  (`uv pip install --no-build`) so sdist `setup.py` code never executes;
  install timeout 300s.
- **Residual risk:** a compromised release of a curated package still executes
  at *import* time inside the verifier subprocess (same blast radius as #1 —
  mitigated by the same T14a isolation).

### 3. Prompt injection via release notes (analyzer)

GitHub release bodies are attacker-influenceable input fed to the LLM, whose
output is code we execute. Chain: malicious release notes → injected
instructions → generated snippet → verifier runs it.

- **In place:** the snippet executes under #1's controls (no secrets, no
  credentials, timeout); the analyzer prompt constrains output to a JSON
  schema of migration cases; nothing the model returns is ever shelled out
  directly — only written as a candidate file and executed under the verifier.
- **Residual risk:** same as #1 (network). T14a closes it.

### 4. Secrets

- `ANTHROPIC_API_KEY` lives in `.env` (gitignored, `.env.example` committed
  empty); read via `os.getenv`; never passed into snippet environments; never
  logged. Published artifacts (corpus JSON, reports) contain no env data.

### 5. Published surfaces

- The MCP server is read-only over local JSON files; it executes nothing and
  takes no file paths from clients (package name is interpolated into a
  filename — `corpus_dir / f"{package}.json"`; names not matching
  `[A-Za-z0-9_.-]+` are rejected, closing the path-traversal gap — T14b done
  this review).
- Corpus snippets are published as *data*; consumers execute them at their own
  discretion. The README/dataset card must state they are LLM-generated,
  execution-verified for pass/fail behavior only, and not audited line-by-line.

## Action items

- [x] Wheels-only installs in the verifier (`--no-build`) — done this review.
- [x] T14b Package-name validation in `corpus.load_entries` (MCP input).
- [ ] T14a Network-less snippet execution before corpus scale-up / publication.
- [ ] Dataset card disclaimer text when T15 (HF export) lands.
