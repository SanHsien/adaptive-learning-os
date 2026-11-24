"""Compare root package.json dependency floors and pinned Actions with upstream releases.

Adapted from commerce-agents. Reports declarations only; never installs or updates
dependencies. npm uses dist-tags.latest; Actions use Releases API with tags fallback.
Run: python tools/check_dependency_freshness.py --json --strict
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "adaptive-learning-os-dependency-freshness"


_RELEASE_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*")
# `owner/repo`, optionally followed by a sub-path: `github/codeql-action/init` is one
# action published from a directory of `github/codeql-action`. An `owner/repo`-only
# pattern silently matched nothing on those lines, so codeql.yml's two pins never
# reached the report at all -- a check that is blind to a declaration is worse than one
# that reports it stale.
_USES_RE = re.compile(
    r"^\s*(?:-\s*)?uses:\s*([\w.\-]+/[\w.\-]+(?:/[\w.\-]+)*)@([0-9a-fA-F]{40}|\S+)"
    r"(?:\s*#\s*(.*))?\s*$",
    re.MULTILINE,
)
HOLD_MARKER = "freshness-hold:"
DEFERRALS_PATH = REPO_ROOT / ".github" / "dependency-deferrals.json"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


class DependencyCheckError(RuntimeError):
    """Raised when package.json or the workflows directory cannot be read."""


def release_key(version: str) -> tuple[int, ...] | None:
    """Return the numeric release segment of a version, or None if unparsable.

    Pre-release and local suffixes are dropped, so 7.0.0rc1 and 7.0.0 rank the
    same. That is precise enough to answer "has the declared floor aged?"
    without adding a PEP 440 or semver parser to a repo whose declared
    dependencies are npm packages and pinned GitHub Actions.
    """
    match = _RELEASE_RE.match(version.strip().lstrip("vV"))
    if not match:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def is_newer_version(latest: str, declared: str) -> bool:
    """Is `latest` newer than `declared` at the precision `declared` states?

    A floor of `Pillow>=10` says nothing about the minor, so reporting 10.4.0
    against it would be a standing false alarm -- and a monthly report that
    cries wolf gets ignored. The comparison therefore happens at the depth the
    declaration commits to: `>=10` on the major alone, `>=1.26` on major.minor,
    and `v7.0.1` on all three segments for a pinned Action.
    """
    latest_key = release_key(latest)
    declared_key = release_key(declared)
    if latest_key is None or declared_key is None:
        return False
    depth = len(declared_key)
    padded = latest_key + (0,) * (depth - len(latest_key))
    return padded[:depth] > declared_key


def load_deferrals(path: Path = DEFERRALS_PATH) -> dict[str, tuple[str, str]]:
    """Read reviewed-but-not-now decisions: package -> (reviewed release, reason).

    A hold says "this floor is the floor we want" and never expires. A deferral
    says "we looked, and not this month", which is a different claim and must
    not outlive the release it was made against. `deferredLatest` is what makes
    it expire by itself: once the upstream source moves past that release the
    report asks again, so a deferral cannot quietly become a permanently
    silenced check. An entry without it is ignored for exactly that reason.
    """
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("deferrals", {})
    except (OSError, ValueError):
        return {}
    deferrals: dict[str, tuple[str, str]] = {}
    for name, entry in (entries or {}).items():
        if not isinstance(entry, dict):
            continue
        latest = str(entry.get("deferredLatest", "")).strip()
        reason = str(entry.get("reason", "")).strip()
        if latest and reason:
            deferrals[name.lower()] = (latest, reason)
    return deferrals


def parse_workflow_actions(text: str, source: str) -> list[dict[str, str]]:
    """Every `uses: owner/repo@<ref> # vX.Y.Z` declaration in a workflow file."""
    packages: list[dict[str, str]] = []
    for match in _USES_RE.finditer(text):
        action, ref, comment = match.group(1), match.group(2), (match.group(3) or "").strip()
        hold = comment[len(HOLD_MARKER) :].strip() if comment.startswith(HOLD_MARKER) else ""
        # A pinned SHA carries its declared version in the trailing comment
        # (`# v7.0.1`); an unpinned floating tag (`@v6`) carries it in the ref
        # itself. Either is a real declaration worth tracking -- only a hold
        # or a comment/ref with no parseable number leaves `minimum` empty.
        version_source = comment if comment else ref
        version_match = _RELEASE_RE.match(version_source.lstrip("vV")) if not hold else None
        minimum = version_match.group(0) if version_match else ""
        packages.append(
            {
                "name": action,
                "minimum": minimum,
                "requirement": f"{action}@{comment or ref[:12]}",
                "source": source,
                "hold": hold,
                "kind": "github-action",
            }
        )
    return packages


def load_direct_dependencies(root: Path = REPO_ROOT) -> list[dict[str, str]]:
    """Read root npm declarations; unsupported ranges are reported as check failures."""
    try:
        manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DependencyCheckError(f"cannot read package.json: {exc}") from exc
    if not isinstance(manifest, dict):
        raise DependencyCheckError("package.json must be an object")
    packages: list[dict[str, str]] = []
    for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        entries = manifest.get(section, {})
        if not isinstance(entries, dict):
            raise DependencyCheckError(f"package.json {section} must be an object")
        for name, specifier in entries.items():
            # Only simple floors used here; never guess at unions, URLs or workspaces.
            match = re.fullmatch(r"(?:[~^]|>=)?(\d+\.\d+\.\d+)", str(specifier))
            packages.append({
                "name": name,
                "minimum": match.group(1) if match else "",
                "requirement": str(specifier),
                "source": f"package.json ({section})",
                "hold": "",
                "kind": "npm",
            })
    return packages


def load_workflow_actions(root: Path = REPO_ROOT) -> list[dict[str, str]]:
    """Every pinned Action across `.github/workflows/*.yml`, deduplicated.

    The same action pinned to the same declared version in two files is one
    row with both sources listed; pinned to two *different* declared versions
    it is two rows, because that split is itself drift worth seeing.
    """
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        raise DependencyCheckError("missing .github/workflows directory")
    merged: dict[tuple[str, str], dict[str, str]] = {}
    for path in sorted(workflows_dir.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for package in parse_workflow_actions(text, path.name):
            key = (package["name"].lower(), package["minimum"] or package["requirement"])
            existing = merged.get(key)
            if existing is None:
                merged[key] = package
                continue
            sources = existing["source"].split(", ")
            if path.name not in sources:
                sources.append(path.name)
                existing["source"] = ", ".join(sources)
    return sorted(merged.values(), key=lambda p: (p["name"], p["minimum"]))


def fetch_npm_version(package_name: str, timeout: float = 10.0) -> str | None:
    quoted_name = urllib.parse.quote(package_name, safe="")
    request = urllib.request.Request(
        f"https://registry.npmjs.org/{quoted_name}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    version = payload.get("dist-tags", {}).get("latest")
    return str(version) if version else None


def action_repository(action_name: str) -> str:
    """The `owner/repo` that publishes an action, dropping any sub-path.

    `github/codeql-action/init` and `github/codeql-action/analyze` ship from directories
    of one repository and share its releases; asking the API for `repos/github/
    codeql-action/init/releases/latest` 404s, which the caller would read as "could not
    check" rather than as the parsing bug it is.
    """
    owner, _, rest = action_name.partition("/")
    return f"{owner}/{rest.split('/', 1)[0]}" if rest else action_name


def fetch_github_release(action_name: str, timeout: float = 10.0) -> str | None:
    """The latest release tag for an action, or None when it cannot be read.

    The token matters: unauthenticated api.github.com allows 60 requests an hour per
    address, and past it every lookup here returns 403. That reads as "latest unknown"
    on every Action row at once -- a whole half of the report going quiet without
    saying why -- so `GITHUB_TOKEN` (or `GH_TOKEN`) is sent when the environment has
    one. Absent a token this still works, just against the anonymous limit.
    """
    quoted_name = urllib.parse.quote(action_repository(action_name), safe="/")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{quoted_name}/releases/latest",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        payload = {}
    tag = str(payload.get("tag_name") or "")
    if release_key(tag) is not None:
        return tag.lstrip("vV")
    # Some repositories tag their latest *release* with something that is not the
    # action's version: `github/codeql-action` names it `codeql-bundle-v2.27.0`, the
    # CodeQL bundle, while the action itself moves on `v4.37.9` tags. Comparing a
    # `v4.37.9` pin against a bundle tag yields an unparsable "latest" that scores as
    # not-outdated -- a false green. Fall back to the version tags themselves.
    return _fetch_latest_version_tag(quoted_name, headers, timeout)


def _fetch_latest_version_tag(
    quoted_name: str, headers: dict[str, str], timeout: float
) -> str | None:
    """The highest `vX.Y.Z` tag on a repository, ignoring tags that are not versions."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{quoted_name}/tags?per_page=100", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            tags = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(tags, list):
        return None
    best: tuple[tuple[int, ...], str] | None = None
    for entry in tags:
        name = str((entry or {}).get("name") or "") if isinstance(entry, dict) else ""
        key = release_key(name)
        if key is None or not name.lstrip("vV")[:1].isdigit():
            continue
        if best is None or key > best[0]:
            best = (key, name.lstrip("vV"))
    return best[1] if best else None


def collect_status(
    packages: list[dict[str, str]],
    fetch: Callable[[str], str | None],
    deferrals: dict[str, tuple[str, str]] | None = None,
) -> list[dict[str, object]]:
    deferrals = deferrals if deferrals is not None else load_deferrals()
    rows: list[dict[str, object]] = []
    for package in packages:
        minimum = package["minimum"]
        latest = fetch(package["name"])
        reviewed, reason = deferrals.get(package["name"].lower(), ("", ""))
        deferred = bool(reviewed and latest and not is_newer_version(latest, reviewed))
        rows.append(
            {
                **package,
                "latest": latest or "unknown",
                "outdated": bool(minimum and latest and is_newer_version(latest, minimum)),
                # A hold leaves `minimum` empty on purpose (its comment is the reason,
                # not a version), so an empty minimum only fails an un-held row.
                "check_failed": (not minimum and not package.get("hold")) or latest is None,
                "deferred_reason": reason if deferred else "",
            }
        )
    return rows


def needs_review(row: dict[str, object]) -> bool:
    """An aged floor still counts unless a hold or a live deferral covers it."""
    return bool(row["outdated"]) and not row.get("hold") and not row.get("deferred_reason")


def _render_table(rows: list[dict[str, object]]) -> list[str]:
    lines = [
        "| Package | Declared in | Requirement | Latest | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row["check_failed"]:
            status = "CHECK FAILED"
        elif row.get("hold") and row["outdated"]:
            status = f"HELD: {row['hold']}"
        elif row.get("deferred_reason") and row["outdated"]:
            status = f"DEFERRED at {row['latest']}: {row['deferred_reason']}"
        elif row["outdated"]:
            status = "REVIEW UPDATE"
        else:
            status = "OK"
        lines.append(
            f"| `{row['name']}` | `{row['source']}` | `{row['requirement']}` | "
            f"`{row['latest']}` | {status} |"
        )
    if not rows:
        lines.append("| - | - | - | - | CHECK FAILED |")
    return lines


def render_markdown(
    rows_npm: list[dict[str, object]],
    rows_actions: list[dict[str, object]] | None = None,
    error: str | None = None,
) -> str:
    rows_actions = rows_actions if rows_actions is not None else []
    lines = ["# Dependency freshness report", ""]
    if error:
        lines.extend(["## Check failed", "", f"```text\n{error}\n```", ""])
        return "\n".join(lines)

    lines.extend(["## npm dependencies (package.json)", ""])
    lines.extend(_render_table(rows_npm))
    lines.extend(["", "## GitHub Actions (pinned in .github/workflows/)", ""])
    lines.extend(_render_table(rows_actions))
    lines.extend([
        "",
        "Declared floors are compared against npm dist-tags.latest and GitHub releases.",
        "package-lock.json and vendored files are not inspected or changed.",
        "There are no Python dependency manifests in this repo; Python tools are optional.",
        "",
        "## Review policy",
        "",
        "1. Read release notes, raise the declaration, then run npm ci, npm test and Python tests.",
        "2. Repin Actions by full SHA with a version comment; never replace a SHA with a floating tag.",
        "3. If an update would break something, record a reviewed version and reason in",
        "   .github/dependency-deferrals.json using deferredLatest; it expires on a newer release.",
        "   Actions can use # freshness-hold: <why> for a standing policy.",
        "",
    ])
    return "\n".join(lines)


def write_github_output(
    rows_npm: list[dict[str, object]],
    rows_actions: list[dict[str, object]],
    report_path: Path,
) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    rows = rows_npm + rows_actions
    outdated = any(needs_review(row) for row in rows)
    check_failed = not rows or any(bool(row["check_failed"]) for row in rows)
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"outdated={'true' if outdated else 'false'}\n")
        output.write(f"check_failed={'true' if check_failed else 'false'}\n")
        output.write(f"needs_attention={'true' if outdated or check_failed else 'false'}\n")
        output.write(f"report_path={report_path.as_posix()}\n")


def render_json(
    rows_npm: list[dict[str, object]],
    rows_actions: list[dict[str, object]],
    error: str | None,
) -> str:
    """A machine-readable mirror of the Markdown report.

    Every row already round-trips through ``json.dumps`` (strings and bools
    only), so this is a thin wrapper, not a second source of truth: the same
    ``rows_npm`` / ``rows_actions`` feed both `render_markdown` and this.
    """
    payload = {
        "error": error,
        "npm_dependencies": rows_npm,
        "github_actions": rows_actions,
        "needs_review": [row["name"] for row in rows_npm + rows_actions if needs_review(row)],
        "check_failed": any(bool(row["check_failed"]) for row in rows_npm + rows_actions),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dependency-freshness-report.md")
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Write status fields to GITHUB_OUTPUT",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON mirror of the report to stdout instead of Markdown "
        "(the Markdown file at --output is still written).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when a declared range has aged.",
    )
    args = parser.parse_args()

    rows_npm: list[dict[str, object]] = []
    rows_actions: list[dict[str, object]] = []
    error: str | None = None
    try:
        deferrals = load_deferrals()
        rows_npm = collect_status(load_direct_dependencies(), fetch_npm_version, deferrals)
        rows_actions = collect_status(load_workflow_actions(), fetch_github_release, deferrals)
    except DependencyCheckError as exc:
        error = str(exc)

    report = render_markdown(rows_npm, rows_actions, error)
    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")
    print(render_json(rows_npm, rows_actions, error) if args.json else report)

    if args.github_output:
        write_github_output(rows_npm, rows_actions, output_path)
    if error:
        return 2
    if args.strict and any(
        needs_review(row) or bool(row["check_failed"]) for row in rows_npm + rows_actions
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
