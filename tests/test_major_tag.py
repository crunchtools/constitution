"""major_tag.py: the major tag moves forward only, and only for a release."""

import pytest

import major_tag

TAGS = ["v0.9.0", "v1", "v1.44.0", "v1.45.0", "v1.100.0", "v2.0.0-rc1", "vnext"]


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.100.0", "v1"),  # the newest of its major, compared as numbers
        ("v1.101.0", "v1"),  # newer than every tag listed
        ("v1.45.1", None),  # a late patch to an older minor
        ("v0.9.0", "v0"),  # each major has its own tag
        ("v2.0.0", "v2"),  # the first release of a major
        ("v2.0.0-rc1", None),
        ("v1", None),
        ("main", None),
    ],
)
def test_only_the_newest_release_of_a_major_moves_its_tag(tag, expected):
    assert major_tag.major_tag(tag, TAGS) == expected


def delivered(monkeypatch, tag):
    calls = []

    def gh(*args):
        if "--jq" in args:
            return "".join(f"refs/tags/{name}\n" for name in TAGS)
        if args[:2] == ("api", f"repos/o/r/commits/{tag}"):
            return '{"sha": "abcdef0123"}'
        calls.append(args)
        return ""

    monkeypatch.setattr(major_tag, "gh", gh)
    return major_tag.deliver("o/r", tag), calls


def test_an_existing_major_tag_is_moved_to_the_release(monkeypatch):
    said, calls = delivered(monkeypatch, "v1.101.0")
    assert calls == [
        (
            "api",
            "-X",
            "PATCH",
            "repos/o/r/git/refs/tags/v1",
            "-f",
            "sha=abcdef0123",
            "-F",
            "force=true",
        )
    ]
    assert said == "v1 now points at v1.101.0 (abcdef0)"


def test_the_first_release_of_a_major_creates_its_tag(monkeypatch):
    _, calls = delivered(monkeypatch, "v2.0.0")
    assert calls == [
        (
            "api",
            "-X",
            "POST",
            "repos/o/r/git/refs",
            "-f",
            "ref=refs/tags/v2",
            "-f",
            "sha=abcdef0123",
        )
    ]


def test_an_older_patch_moves_nothing(monkeypatch):
    said, calls = delivered(monkeypatch, "v1.45.1")
    assert calls == []
    assert "stays where it is" in said


def test_a_non_release_asks_github_nothing(monkeypatch):
    asked = []
    monkeypatch.setattr(major_tag, "gh", lambda *args: asked.append(args) or "")
    assert "not a release tag" in major_tag.deliver("o/r", "nightly")
    assert asked == []
