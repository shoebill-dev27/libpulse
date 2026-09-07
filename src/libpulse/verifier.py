"""Execution verifier: prove or refute a MigrationCase by running it.

The moat of the whole project lives here. A case is only published when actual
execution in version-pinned virtual environments confirms every claim:

  1. before_snippet passes on package==old_version   (snippet is valid)
  2. before_snippet fails  on package==new_version   (change is really breaking)
  3. after_snippet  passes on package==new_version   (recipe really migrates)

Security note: snippets originate from our own pipeline (never user-submitted),
but they are still LLM-generated code. They run in a subprocess with a scrubbed
environment, a temporary working directory, and a hard timeout.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .models import MigrationCase, StepResult, Verdict, VerificationResult

SNIPPET_TIMEOUT = 60  # seconds per snippet
INSTALL_TIMEOUT = 300  # seconds per environment build

_isolation_prefix_cache: list[str] | None = None


def _isolation_prefix() -> list[str]:
    """Network-isolation wrapper for snippet execution (T14a).

    `unshare -rn` puts the snippet in an empty network namespace. Loopback is
    brought up inside the namespace so snippets may use 127.0.0.1 — local
    server fixtures are legitimate library usage (e.g. aiohttp) — while
    anything beyond loopback still has nowhere to go. Auto-detected once.
    Opt out with LIBPULSE_NO_NET_ISOLATION=1 (e.g. kernels without user
    namespaces).
    """
    global _isolation_prefix_cache
    if os.getenv("LIBPULSE_NO_NET_ISOLATION"):
        return []
    if _isolation_prefix_cache is None:
        prefix: list[str] = []
        unshare = shutil.which("unshare")
        sh = shutil.which("sh")
        ip = shutil.which("ip")
        if unshare and sh:
            lo_up = f'"{ip}" link set lo up 2>/dev/null || true; ' if ip else ""
            candidate = [unshare, "-rn", sh, "-c", f'{lo_up}exec "$@"', "libpulse-isolate"]
            try:
                usable = (
                    subprocess.run([*candidate, "true"], capture_output=True, timeout=10).returncode
                    == 0
                )
            except Exception:
                usable = False
            if usable:
                prefix = candidate
        _isolation_prefix_cache = prefix
    return _isolation_prefix_cache


class EnvSetupError(RuntimeError):
    pass


def _uv() -> str:
    exe = shutil.which("uv")
    if not exe:
        raise EnvSetupError(
            "uv is required for environment management. Install: https://docs.astral.sh/uv/"
        )
    return exe


class VenvCache:
    """Builds and caches version-pinned virtualenvs under a root directory.

    Cache key: hash of the sorted requirement specs + python version, so the
    same (package, version, extras) combination is only ever built once.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or Path.cwd() / "venvs")
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _python_candidates() -> list[tuple[str, str]]:
        """(executable, version-tag) pairs to try for env builds.

        The running interpreter first; newer system interpreters as fallbacks
        for packages whose requires-python exceeds it (e.g. django 6.0 needs
        3.12 while the harness runs on 3.11).
        """
        current = sys.version_info[:2]
        cands = [(sys.executable, f"{current[0]}.{current[1]}")]
        for minor in (12, 13, 14):
            if (3, minor) <= current:
                continue
            exe = shutil.which(f"python3.{minor}")
            if exe:
                cands.append((exe, f"3.{minor}"))
        return cands

    def python_for(self, specs: list[str]) -> str:
        """Return a python executable from a venv with `specs` installed."""
        last_exc: EnvSetupError | None = None
        for exe, tag in self._python_candidates():
            try:
                return self._build(exe, tag, specs)
            except EnvSetupError as exc:
                last_exc = exc
                # uv wraps its error text, so normalize whitespace before
                # matching. Only an interpreter-fit problem justifies trying a
                # newer interpreter; any other failure is final.
                #
                # "no usable wheels" belongs here: with --no-build, a package
                # that ships no wheel for the current interpreter fails with
                # that message rather than a requires-python one, and the
                # newer interpreter usually does have a wheel. Missing it
                # froze the corpus from 2026-06 to 2026-09 — every numpy/polars
                # release came back UNVERIFIABLE without ever trying 3.12.
                msg = " ".join(str(exc).split())
                retryable = ("does not satisfy Python", "requires Python", "no usable wheels")
                if not any(m in msg for m in retryable):
                    raise
        assert last_exc is not None
        raise last_exc

    def _build(self, base_python: str, tag: str, specs: list[str]) -> str:
        key = hashlib.sha256(("|".join(sorted(specs)) + f"|py{tag}").encode()).hexdigest()[:16]
        env_dir = self.root / key
        python = env_dir / "bin" / "python"
        marker = env_dir / ".libpulse-ready"
        if marker.exists() and python.exists():
            return str(python)
        if env_dir.exists():
            shutil.rmtree(env_dir)  # half-built env from a previous crash
        try:
            subprocess.run(
                [_uv(), "venv", str(env_dir), "--python", base_python],
                check=True,
                capture_output=True,
                timeout=INSTALL_TIMEOUT,
            )
            if specs:
                # --no-build: wheels only. Building sdists executes arbitrary
                # setup code at install time (supply-chain surface, T14).
                subprocess.run(
                    [_uv(), "pip", "install", "--no-build", "--python", str(python), *specs],
                    check=True,
                    capture_output=True,
                    timeout=INSTALL_TIMEOUT,
                )
        except subprocess.TimeoutExpired as exc:
            raise EnvSetupError(f"timeout building env for {specs}: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode(errors="replace")[-2000:]
            raise EnvSetupError(f"failed building env for {specs}: {stderr}") from exc
        marker.touch()
        return str(python)


def run_snippet(
    python: str, code: str, timeout: int = SNIPPET_TIMEOUT
) -> tuple[bool, int, str, str]:
    """Run `code` with `python` in an isolated temp dir with a scrubbed env."""
    with tempfile.TemporaryDirectory(prefix="libpulse-run-") as tmp:
        script = Path(tmp) / "snippet.py"
        script.write_text(code, encoding="utf-8")
        env = {
            "PATH": os.defpath,
            "HOME": tmp,
            "TMPDIR": tmp,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONWARNINGS": "ignore",  # deprecation noise must not affect verdicts
        }
        try:
            proc = subprocess.run(
                [*_isolation_prefix(), python, str(script)],
                cwd=tmp,
                env=env,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return False, -1, "", f"timeout after {timeout}s"
        return (
            proc.returncode == 0,
            proc.returncode,
            proc.stdout.decode(errors="replace")[-2000:],
            proc.stderr.decode(errors="replace")[-2000:],
        )


class Verifier:
    def __init__(self, cache: VenvCache | None = None) -> None:
        self.cache = cache or VenvCache()

    def verify(self, case: MigrationCase) -> VerificationResult:
        steps: list[StepResult] = []

        def run(step: str, python: str, code: str) -> StepResult:
            passed, rc, out, err = run_snippet(python, code)
            result = StepResult(step=step, passed=passed, returncode=rc, stdout=out, stderr=err)
            steps.append(result)
            return result

        old_specs = [f"{case.package}=={case.old_version}", *case.extra_requires]
        new_specs = [f"{case.package}=={case.new_version}", *case.extra_requires]

        try:
            py_old = self.cache.python_for(old_specs)
        except EnvSetupError as exc:
            return VerificationResult(case.case_id, Verdict.UNVERIFIABLE, steps, error=str(exc))

        if not run("before_on_old", py_old, case.before_snippet).passed:
            return VerificationResult(
                case.case_id,
                Verdict.UNVERIFIABLE,
                steps,
                error="before_snippet does not pass on the old version; snippet invalid",
            )

        try:
            py_new = self.cache.python_for(new_specs)
        except EnvSetupError as exc:
            return VerificationResult(case.case_id, Verdict.UNVERIFIABLE, steps, error=str(exc))

        if run("before_on_new", py_new, case.before_snippet).passed:
            return VerificationResult(case.case_id, Verdict.NOT_BREAKING, steps)

        if not run("after_on_new", py_new, case.after_snippet).passed:
            return VerificationResult(case.case_id, Verdict.BROKEN_RECIPE, steps)

        # Informational only: does the migrated code also run on the old version?
        after_on_old = run("after_on_old", py_old, case.after_snippet).passed

        return VerificationResult(
            case.case_id, Verdict.VERIFIED, steps, after_works_on_old=after_on_old
        )
