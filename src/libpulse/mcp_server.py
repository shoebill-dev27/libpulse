"""MCP server (stdio): serves the verified corpus to AI agents.

First distribution channel per ADR-004. Requires the optional `mcp` extra
(`pip install 'libpulse[mcp]'`) — the approved exception to the stdlib-only
core rule. All data access lives in `corpus` (stdlib-only); this module is
only the protocol wiring.
"""

from __future__ import annotations

from . import corpus


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # keep the core importable without the extra
        raise SystemExit(
            "The MCP server needs the optional dependency: pip install 'libpulse[mcp]'"
        ) from exc

    server = FastMCP("libpulse")

    @server.tool()
    def list_packages() -> list[dict]:
        """List the packages covered by the LibPulse corpus.

        Call this first to discover which packages have execution-verified
        breaking-change data, with the per-package case count and the newest
        release covered.
        """
        return corpus.list_packages()

    @server.tool()
    def query_migrations(
        package: str, from_version: str | None = None, to_version: str | None = None
    ) -> dict:
        """Execution-verified breaking changes and migration recipes for a package upgrade.

        Call this when upgrading a Python dependency or debugging an error that
        appeared after a version bump. Every entry was proven by real execution:
        the `before` snippet passes on the old version and fails on the new one,
        and the `after` snippet (the migration recipe) passes on the new version.
        Omit the version bounds to get every verified case for the package.
        """
        return corpus.query_migrations(package, from_version, to_version)

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
