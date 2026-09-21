"""Catalog source loading and lightweight GitHub metadata mining.

The miner uses the GitHub REST API and never clones repositories.  Every HTTP
operation is injectable, making catalog refreshes deterministic in tests.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Callable


def load_sources(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path or Path(__file__).with_name("catalog_sources.yaml"))
    text = path.read_text(encoding="utf-8")
    # JSON is a YAML 1.2 subset; the checked-in catalog deliberately uses
    # that subset so the CLI has no third-party dependency.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("non-JSON YAML catalog loading requires PyYAML") from exc
        return yaml.safe_load(text)


def github_json(url: str, opener: Callable[..., Any] | None = None) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "chipignite-catalog"})
    opener = opener or urllib.request.urlopen
    with opener(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def mine_repository(repository: str, *, opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Fetch stable metadata, preserving raw commit/license/artifact fields."""
    base = f"https://api.github.com/repos/{repository}"
    repo = github_json(base, opener)
    result = {
        "repository": repository,
        "name": repo.get("name"),
        "url": repo.get("html_url"),
        "default_branch": repo.get("default_branch"),
        "description": repo.get("description"),
        "license": repo.get("license"),
        "commit": None,
        "artifacts": [],
        "raw": {"repository": repo},
    }
    branch = result["default_branch"] or "HEAD"
    commit = github_json(f"{base}/commits/{branch}", opener)
    result["commit"] = commit
    releases = github_json(f"{base}/releases", opener)
    result["artifacts"] = releases if isinstance(releases, list) else []
    result["raw"].update({"commit": commit, "releases": releases})
    return result


def mine_catalog(sources: dict[str, Any], *, opener: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    return [mine_repository(item["repository"], opener=opener) for item in sources.get("top_candidates", [])]
