"""Freshness contracts adapted from commerce-agents, using the standard library."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_dependency_freshness as checker


def test_comparison_uses_the_precision_the_declaration_states() -> None:
    # `>=7` says nothing about the minor, so 7.4.0 must not be a monthly alarm.
    assert not checker.is_newer_version("7.4.0", "7")
    assert checker.is_newer_version("8.0.0", "7")
    assert checker.is_newer_version("7.4.0", "7.3")
    assert not checker.is_newer_version("7.3.2", "7.3")


def test_prerelease_suffix_does_not_count_as_newer() -> None:
    assert not checker.is_newer_version("7.0.0rc1", "7.0.0")


def test_leading_v_is_stripped_for_github_action_tags() -> None:
    assert checker.is_newer_version("v7.1.0", "7.0.1")
    assert not checker.is_newer_version("v7.0.1", "7.0.1")


def test_workflow_actions_are_parsed_with_their_declared_version() -> None:
    text = (
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
        "      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0\n"
    )

    packages = checker.parse_workflow_actions(text, "ci.yml")

    by_name = {p["name"]: p for p in packages}
    assert by_name["actions/checkout"]["minimum"] == "7.0.1"
    assert by_name["actions/checkout"]["source"] == "ci.yml"
    assert by_name["actions/checkout"]["hold"] == ""


def test_workflow_action_hold_marker_is_read_off_the_uses_line() -> None:
    text = (
        "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
        " # freshness-hold: pinned for a documented reason\n"
    )

    packages = checker.parse_workflow_actions(text, "ci.yml")

    assert packages[0]["hold"] == "pinned for a documented reason"
    assert packages[0]["minimum"] == ""


def test_real_workflows_declare_at_least_one_pinned_action() -> None:
    actions = checker.load_workflow_actions()

    assert len(actions) >= 3
    assert all(a["minimum"] or a["hold"] for a in actions)


def test_the_repos_own_deferrals_file_parses() -> None:
    """This fork now raises its own declared floors directly instead of waiting on
    upstream's pace (see docs/DIVERGENCE.md), so `.github/dependency-deferrals.json`
    starts empty; a deferral is reserved for a floor that would genuinely break
    something if raised right now, not for "waiting on upstream"."""
    assert checker.load_deferrals() == {}


def test_an_action_published_from_a_subdirectory_is_parsed_and_resolved() -> None:
    """`github/codeql-action/init` is a real declaration; an owner/repo-only pattern
    matched nothing on those lines, so codeql.yml's two pins were invisible to the
    report -- silently, which is the worst way for a check to be wrong."""
    text = (
        "      - uses: github/codeql-action/init"
        "@a35ac6e6798d72df5475948b28efb89edc2e19ca # v4.37.9\n"
    )
    parsed = checker.parse_workflow_actions(text, "codeql.yml")

    assert [p["name"] for p in parsed] == ["github/codeql-action/init"]
    assert parsed[0]["minimum"] == "4.37.9"
    # Releases live on the publishing repository, not the sub-path.
    assert checker.action_repository("github/codeql-action/init") == "github/codeql-action"
    assert checker.action_repository("actions/checkout") == "actions/checkout"


def test_a_latest_that_cannot_be_compared_is_a_failed_check_not_an_ok_row() -> None:
    """The false green this whole fix exists to remove.

    `github/codeql-action` tags its latest *release* `codeql-bundle-v2.27.0`. Compared
    against a `v4.37.9` pin that parses to nothing, scores as "not newer", and reports
    OK -- forever, no matter how far behind the pin drifts. A check that cannot fail is
    not a check, so an unresolvable latest has to land in `check_failed`.
    """
    rows = checker.collect_status(
        [{"name": "github/codeql-action/init", "minimum": "4.37.9", "hold": ""}],
        lambda _name: None,
        deferrals={},
    )

    assert rows[0]["latest"] == "unknown"
    assert rows[0]["check_failed"] is True
    assert rows[0]["outdated"] is False


def test_a_bundle_style_release_tag_falls_back_to_the_version_tags() -> None:
    """`fetch_github_release` must return a comparable version or None -- never a tag
    whose text happens to parse to nothing. The fallback reads `/tags` for the newest
    `vX.Y.Z`, which is where the action's own version actually lives."""
    calls: list[str] = []

    def fake_urlopen(request, timeout):  # noqa: ANN001, ARG001
        calls.append(request.full_url)
        body = (
            b'{"tag_name": "codeql-bundle-v2.27.0"}'
            if "releases/latest" in request.full_url
            else b'[{"name": "codeql-bundle-v2.27.0"}, {"name": "v4.37.9"}, {"name": "v4.37.8"}]'
        )

        class _Response:
            def read(self) -> bytes:
                return body

            def __enter__(self) -> _Response:
                return self

            def __exit__(self, *_: object) -> None:
                return None

        return _Response()

    original = checker.urllib.request.urlopen
    checker.urllib.request.urlopen = fake_urlopen
    try:
        latest = checker.fetch_github_release("github/codeql-action/init")
    finally:
        checker.urllib.request.urlopen = original

    assert latest == "4.37.9"
    # The sub-path never reaches the API: releases and tags live on the repository.
    assert all("codeql-action/init" not in url for url in calls)


def test_the_repos_own_codeql_pins_reach_the_report() -> None:
    """The live contract: both codeql.yml declarations must be collected."""
    names = {action["name"] for action in checker.load_workflow_actions()}

    assert "github/codeql-action/init" in names
    assert "github/codeql-action/analyze" in names


def test_json_output_surfaces_the_check_error() -> None:
    payload = json.loads(checker.render_json([], [], "missing requirements file: nope.txt"))

    assert payload["error"] == "missing requirements file: nope.txt"


def test_a_held_workflow_action_is_held_not_a_failed_check() -> None:
    """A hold leaves `minimum` empty (the comment is the reason, not a version), and
    `check_failed` was derived from the empty minimum: a deliberately held Action showed
    "CHECK FAILED" and kept `needs_attention` true on every monthly run."""
    packages = checker.parse_workflow_actions(
        "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
        " # freshness-hold: pinned for a documented reason\n",
        "ci.yml",
    )

    rows = checker.collect_status(packages, lambda _name: "9.0.0", deferrals={})

    assert rows[0]["check_failed"] is False
    assert checker.needs_review(rows[0]) is False


def test_npm_manifest_collects_every_declared_dependency() -> None:
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    packages = checker.load_direct_dependencies()
    assert {p["name"] for p in packages} == set(manifest["devDependencies"])
    assert all(p["minimum"] and p["kind"] == "npm" for p in packages)
    assert next(p for p in packages if p["name"] == "fake-indexeddb")["minimum"] == "6.2.8"


def test_npm_scoped_name_is_encoded_and_latest_tag_used() -> None:
    calls = []
    def fetch(request, timeout):
        calls.append(request.full_url)
        class Response:
            def read(self):
                return b'{"dist-tags":{"latest":"2.0.0","next":"3.0.0-rc.1"}}'
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
        return Response()
    with patch.object(checker.urllib.request, "urlopen", fetch):
        assert checker.fetch_npm_version("@scope/package") == "2.0.0"
    assert calls == ["https://registry.npmjs.org/%40scope%2Fpackage"]


def test_manifest_errors_and_unsupported_ranges_are_not_green() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        root = Path(directory)
        with unittest.TestCase().assertRaises(checker.DependencyCheckError):
            checker.load_direct_dependencies(root)
        (root / "package.json").write_text('{broken', encoding="utf-8")
        with unittest.TestCase().assertRaises(checker.DependencyCheckError):
            checker.load_direct_dependencies(root)
        (root / "package.json").write_text(json.dumps({"dependencies":{"example":"workspace:*"}}), encoding="utf-8")
        rows = checker.collect_status(checker.load_direct_dependencies(root), lambda _: "1.0.0", {})
        assert rows[0]["check_failed"] is True


def test_deferral_expires_and_unreviewed_deferrals_are_ignored() -> None:
    package = {"name":"example", "minimum":"1.0.0", "requirement":"^1.0.0", "source":"package.json", "hold":"", "kind":"npm"}
    rows = checker.collect_status([package], lambda _: "2.0.0", {"example":("2.0.0", "compatibility")})
    assert not checker.needs_review(rows[0])
    rows = checker.collect_status([package], lambda _: "3.0.0", {"example":("2.0.0", "compatibility")})
    assert checker.needs_review(rows[0])
    assert "REVIEW UPDATE" in checker.render_markdown(rows)
    assert json.loads(checker.render_json(rows, [], None))["needs_review"] == ["example"]
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        path = Path(directory) / "deferrals.json"
        path.write_text(json.dumps({"deferrals":{"kept":{"deferredLatest":"2.0.0", "reason":"compatibility"}, "ignored":{"reason":"no release"}}}), encoding="utf-8")
        assert checker.load_deferrals(path) == {"kept":("2.0.0", "compatibility")}
        assert checker.load_deferrals(Path(directory) / "missing.json") == {}


def test_token_is_sent_without_exposing_it() -> None:
    seen = {}
    def fetch(request, timeout):
        seen.update(request.headers)
        class Response:
            def read(self):
                return b'{"tag_name":"v7.0.1"}'
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
        return Response()
    with patch.dict(checker.os.environ, {"GITHUB_TOKEN":"synthetic-token"}), patch.object(checker.urllib.request, "urlopen", fetch):
        assert checker.fetch_github_release("actions/checkout") == "7.0.1"
    assert seen["Authorization"] == "Bearer synthetic-token"


def test_github_output_marks_unknown_as_attention() -> None:
    rows = checker.collect_status([{"name":"example", "minimum":"1.0.0", "hold":""}], lambda _: None, {})
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        output = Path(directory) / "output"
        with patch.dict(checker.os.environ, {"GITHUB_OUTPUT":str(output)}):
            checker.write_github_output(rows, [], Path("report.md"))
        text = output.read_text(encoding="utf-8")
        assert "check_failed=true" in text
        assert "needs_attention=true" in text


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(value) for name, value in globals().items() if name.startswith("test_") and callable(value))


if __name__ == "__main__":
    unittest.main()
