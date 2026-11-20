#!/usr/bin/env python3
"""Build once, gate the digest, promote what was tested (container-image VII).

The logic behind .github/workflows/container-release.yml, kept here so the
refusal paths can be tested; a workflow's inline shell cannot be.

Subcommands, each run by one job of that workflow:

  resolve   on a push to the default branch or a v* tag: find the digest a
            pull request (or main) already gated, so nothing is rebuilt.
            On a pull request, with --outside: reuse the base's gated digest
            when the change touches only files that never reach the image.
  mark      after the gates pass: tag the tested digest gated-<sha>.
  check     refuse, before anything is signed, what promote would refuse:
            not a digest, a tag that is not vX.Y.Z or not on the branch, or
            an image whose version label names another of its releases.
            A floating major tag (v4) is skipped, not refused, here and in
            resolve: skip=true, exit 0.
  promote   move main / latest / semver to a gated digest by copy, refusing
            to move a floating tag backwards, and verify every copy.
  boot      the boot gate: does the image actually start and answer.

Every registry write is `skopeo copy --all --preserve-digests` followed by a
read-back. Not `docker buildx imagetools create`: given a single manifest it
writes a new one-entry index, and the tag then resolves to a digest no gate
tested (constitution#90).
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# major-tag.yml's moving tag (v1, v4): it names a release, it is not one (#176).
FLOATING = re.compile(r"^v\d+$")
# The MCP revision the gate speaks; servers negotiate down from it.
MCP_PROTOCOL = "2025-06-18"
BOOT_TIMEOUT = 120  # seconds; the workflow passes its own boot-timeout
HTTP_TIMEOUT = 10  # seconds per request to the server under test
POLL_SECONDS = 2
LOG_TAIL = 4000  # characters of a failed container's log worth showing
MISSING = re.compile(r"manifest unknown|not found|no such|name unknown", re.I)
# Never outside the image, whatever the caller's globs say: a pull request that
# widens `outside-image` edits a workflow, so it cannot skip its own build.
ALWAYS_BUILT = (".github/*",)
COMPARE_FILES_CAP = 300  # GitHub's compare API lists no more than this many files


class Refused(Exception):
    """A promotion that must not happen. Exit 1, tags untouched."""


class NotReady(Refused):
    """The server answered, but with an HTTP error: retried until the boot deadline."""


class Superseded(Exception):
    """A newer commit owns main; this run stands down. Exit 0, tags untouched."""


class Skipped(Exception):
    """A floating major tag moved; there is nothing to release. Exit 0, skip=true."""


def tag_name(ref: str) -> str | None:
    """The tag a ref names, None for a branch; Skipped for a floating major tag (#176).

    major-tag.yml moves v4 to each release and a caller's `tags: ["v*"]`
    matches it, but the release it points at was promoted by its own tag.
    Anything else not vX.Y.Z (v1.2, v1.2.3-rc1) still looks like a release
    and is refused by check.
    """
    if not ref.startswith("refs/tags/"):
        return None
    name = ref.removeprefix("refs/tags/")
    if FLOATING.match(name):
        raise Skipped(f"tag '{name}' is a floating major tag, not a release: nothing to promote")
    return name


@dataclass
class Result:
    rc: int
    out: str
    err: str


Runner = Callable[[Sequence[str]], Result]


def run(argv: Sequence[str]) -> Result:
    proc = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    return Result(proc.returncode, proc.stdout, proc.stderr)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def output(name: str, value: str) -> None:
    """Write a step output when running in Actions; print it otherwise."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")
    print(f"{name}={value}")


# ------------------------------------------------------------------ registry


class Registry:
    def __init__(self, image: str, runner: Runner = run, authfile: str | None = None):
        self.image = image
        self.run = runner
        self.auth = ["--authfile", authfile] if authfile else []

    def inspect(self, ref: str, *flags: str) -> str | None:
        """`skopeo inspect` of a tag or digest; None if absent.

        Fails closed: any error other than 'not there' is raised, because a
        guard that cannot read the image must not guess.
        """
        res = self.run(["skopeo", "inspect", *flags, *self.auth, f"docker://{self.image}{ref}"])
        if res.rc == 0:
            return res.out
        if MISSING.search(res.err):
            return None
        raise Refused(f"cannot read {self.image}{ref}: {res.err.strip()}")

    def digest(self, ref: str) -> str | None:
        """The manifest digest a tag (or digest) resolves to; None if absent."""
        raw = self.inspect(ref, "--raw")
        return None if raw is None else "sha256:" + hashlib.sha256(raw.encode()).hexdigest()

    def labels(self, digest: str) -> dict[str, str]:
        """The image config's labels at `digest` (none for a missing one, which no copy takes)."""
        return json.loads(self.inspect(f"@{digest}") or "{}").get("Labels") or {}

    def copy(self, digest: str, tag: str) -> None:
        res = self.run(
            [
                "skopeo",
                "copy",
                "--all",
                "--preserve-digests",
                *self.auth,
                f"docker://{self.image}@{digest}",
                f"docker://{self.image}:{tag}",
            ]
        )
        if res.rc != 0:
            raise Refused(f"copy to {self.image}:{tag} failed: {res.err.strip()}")
        got = self.digest(f":{tag}")
        if got != digest:
            raise Refused(f"{self.image}:{tag} resolves to {got}, not the promoted {digest}")
        log(f"  {self.image}:{tag} -> {digest}")


# ------------------------------------------------------------------ github


class GitHub:
    def __init__(self, repo: str, runner: Runner = run):
        self.repo = repo
        self.run = runner

    def api(self, path: str) -> object:
        res = self.run(["gh", "api", f"repos/{self.repo}/{path}"])
        if res.rc != 0:
            raise Refused(f"GitHub API {path} failed: {res.err.strip()}")
        return json.loads(res.out)

    def _object(self, path: str) -> dict:
        found = self.api(path)
        if not isinstance(found, dict):
            raise Refused(f"GitHub API {path} returned {type(found).__name__}, not an object")
        return found

    def tree(self, sha: str) -> str:
        return str(self._object(f"git/commits/{sha}")["tree"]["sha"])

    def parent(self, sha: str) -> str | None:
        """The first parent: for a merge commit, the branch before the merge."""
        parents = self._object(f"git/commits/{sha}").get("parents") or []
        return str(parents[0]["sha"]) if parents else None

    def changed(self, base: str, sha: str) -> list[str] | None:
        """Files `sha` changes on top of `base`, or None when `sha` does not descend from it."""
        found = self._object(f"compare/{base}...{sha}")
        if found.get("status") != "ahead":
            return None
        return [str(f["filename"]) for f in found.get("files") or []]

    def tip(self, branch: str) -> str:
        return str(self._object(f"commits/{branch}")["sha"])

    def on_branch(self, sha: str, branch: str) -> bool:
        """Whether `sha` is the tip of `branch` or behind it (an ancestor)."""
        status = self._object(f"compare/{branch}...{sha}").get("status")
        return status in ("behind", "identical")

    def merged_pr(self, sha: str) -> dict | None:
        pulls = self.api(f"commits/{sha}/pulls")
        if not isinstance(pulls, list):
            raise Refused(f"GitHub API commits/{sha}/pulls returned {type(pulls).__name__}")
        for pr in pulls:
            if pr.get("merge_commit_sha") == sha and pr.get("merged_at"):
                return pr
        return None

    def release_tags(self) -> dict[tuple[int, int, int], str]:
        """vX.Y.Z tags (no pre-releases) -> commit sha."""
        res = self.run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{self.repo}/tags?per_page=100",
                "-q",
                ".[] | [.name, .commit.sha] | @tsv",
            ]
        )
        if res.rc != 0:
            raise Refused(f"cannot list tags: {res.err.strip()}")
        tags = {}
        for line in res.out.splitlines():
            name, _, sha = line.partition("\t")
            m = SEMVER.match(name)
            if m:
                tags[(int(m[1]), int(m[2]), int(m[3]))] = sha
        return tags


# ------------------------------------------------------------------ resolve


def refuse_off_branch(gh: GitHub, sha: str, ref: str, branch: str) -> None:
    """A tag names a commit the branch carries, or nothing is released.

    Through the API with the job's token, so a private repo needs no fetch.
    """
    try:
        on_branch = gh.on_branch(sha, branch)
    except Refused as exc:
        raise Refused(f"{ref} names {sha}; cannot confirm it is on {branch}: {exc}") from exc
    if not on_branch:
        raise Refused(
            f"{ref} names {sha}, which is not on {branch}; only what {branch} carries is released"
        )


def resolve(
    reg: Registry, gh: GitHub, sha: str, ref: str, branch: str = "main"
) -> tuple[str | None, str]:
    """(digest, why) for a push. digest None means: no gated image, rebuild.

    A release promotes gated bytes of the tag commit. It rebuilds only when
    that commit was never gated, and gates the rebuild first: a caller whose
    push trigger filters by path builds nothing for a release commit that
    touches none of its inputs, so that commit has no gated- tag (RT#1550).
    A tag on a commit outside the default branch is refused before anything
    else, gated or not: a PR head carries gated-<sha> before it merges, and
    only what the branch carries is released.
    """
    if tag_name(ref):
        refuse_off_branch(gh, sha, ref, branch)
    marker = reg.digest(f":gated-{sha}")
    if marker:
        return marker, f"gated-{sha} exists"
    pr = gh.merged_pr(sha)
    if pr is None:
        return None, f"no merged pull request produced {sha}"
    head = pr["head"]["sha"]
    if gh.tree(sha) != gh.tree(head):
        return None, (
            f"{sha} is not the source PR #{pr['number']} tested "
            f"(tree differs from {head}); the branch was not up to date"
        )
    gated = reg.digest(f":gated-{head}")
    if gated is None:
        return None, f"PR #{pr['number']} head {head} was never gated (no push credentials?)"
    return gated, f"PR #{pr['number']} gated {head}, same tree as {sha}"


def outside_only(
    reg: Registry, gh: GitHub, base: str, sha: str, outside: Sequence[str]
) -> tuple[str | None, str]:
    """The digest gated for `base`, if `sha` adds to it only files that never reach the image.

    `outside` is the caller's own claim (the `outside-image` input): globs of
    files its Containerfile never COPYs, such as VERSION and CHANGELOG.md. A
    release commit that moves only those builds the same filesystem, so the
    bytes already gated for `base` stand for it, and a release costs a tag
    move instead of a second build (RT#1660). The image's revision label
    keeps naming the commit that was built. `sha` must descend from `base`.
    """
    files = gh.changed(base, sha)
    if files is None:
        return None, f"{sha} does not descend from {base}"
    if len(files) >= COMPARE_FILES_CAP:
        return None, f"{sha} changes {len(files)}+ files on {base}; not checked as release-only"
    inside = [
        f
        for f in files
        if any(fnmatch(f, g) for g in ALWAYS_BUILT) or not any(fnmatch(f, g) for g in outside)
    ]
    if inside:
        return None, f"{sha} changes {inside[0]}, which may reach the image"
    gated = reg.digest(f":gated-{base}")
    if gated is None:
        return None, f"{base} was never gated"
    return gated, f"{sha} changes only {' '.join(files) or 'nothing'} on gated {base}; reused"


def resolve_parent(
    reg: Registry, gh: GitHub, sha: str, outside: Sequence[str]
) -> tuple[str | None, str]:
    """resolve's last resort for a push that was never gated: its first parent's digest."""
    parent = gh.parent(sha)
    if parent is None:
        return None, f"{sha} has no parent"
    return outside_only(reg, gh, parent, sha, outside)


def resolve_pr(
    reg: Registry, gh: GitHub, base: str, head: str, outside: Sequence[str]
) -> tuple[str | None, str]:
    """(digest, why) for a pull request: None means build and gate it as usual."""
    marker = reg.digest(f":gated-{head}")
    if marker:
        return marker, f"gated-{head} exists"
    return outside_only(reg, gh, base, head, outside)


# ------------------------------------------------------------------ promote


def _backup(reg: Registry, tag: str, new: str) -> None:
    """Keep the digest a floating tag held as rollback-<tag> before moving it."""
    old = reg.digest(f":{tag}")
    if old and old != new:
        reg.copy(old, f"rollback-{tag}")


@dataclass
class Event:
    """What is being promoted: the commit, the ref that triggered it, and how."""

    sha: str
    ref: str
    branch: str = "main"
    cascade: bool = False


def check(
    gh: GitHub, digest: str, event: Event, reg: Registry | None = None
) -> tuple[int, int, int] | None:
    """Refuse what must never be signed or promoted; the release version, if a tag.

    resolve runs only on push, so a workflow_dispatch or schedule run on a v*
    ref reaches promote without it; this is the check every path makes (#146).
    Given the registry, a release also refuses an image labelled another version.
    """
    if not DIGEST.match(digest):
        raise Refused(f"'{digest}' is not a sha256 digest")
    name = tag_name(event.ref)
    if name is None:
        return None
    m = SEMVER.match(name)
    if not m:
        raise Refused(f"tag '{name}' is not vX.Y.Z")
    refuse_off_branch(gh, event.sha, event.ref, event.branch)
    if reg is not None:
        refuse_mislabelled(reg, gh, digest, name)
    return (int(m[1]), int(m[2]), int(m[3]))


def release_number(label: str) -> str:
    """The release a version label claims: `v1.1.2` and ` 1.1.2+build` both claim 1.1.2."""
    return label.strip().removeprefix("v").removeprefix("V").split("+", 1)[0]


def refuse_mislabelled(reg: Registry, gh: GitHub, digest: str, tag: str) -> None:
    """A release labelled one of this repo's other releases is refused (#171).

    Read off the image, not the Containerfile, so it holds however the label
    is set. A tag cut on a feature merge, with no release PR to move the
    version strings, ships the previous release's number. Only a label that
    names a release of this repo is compared: an image that sets none inherits
    its base's (ubi10's 10.3, Hummingbird's runtime 3.14.10), which is no
    claim about this repo and must not block its release.
    `org.opencontainers.image.version` stands in when `version` is absent.
    """
    version = tag.removeprefix("v")
    labels = reg.labels(digest)
    raw = labels.get("version", labels.get("org.opencontainers.image.version"))
    if raw is None or release_number(raw) == version:
        return
    if release_number(raw) not in {"{}.{}.{}".format(*v) for v in gh.release_tags()}:
        log(f"  version={raw} names no release of {gh.repo}; inherited, not compared")
        return
    raise Refused(
        f"{tag} would promote {reg.image}@{digest}, which is labelled version={raw}, "
        f"another release of {gh.repo}; cut the release PR that moves the version to {version}"
    )


def promote(reg: Registry, gh: GitHub, digest: str, event: Event) -> list[str]:
    """Move the floating tags this event earns to `digest`; return them.

    `cascade`: an image other images build FROM (the ubi10 chain) cuts no
    release, so its `latest` tracks the default branch with `main`
    (container-image profile, "The cascade is the one exception").
    """
    version = check(gh, digest, event, reg)
    moved: list[str] = []
    releases = gh.release_tags()

    if version:
        tags = _release_tags(version, releases)
    else:
        tip = gh.tip(event.branch)
        if event.sha != tip:
            raise Superseded(
                f"{event.branch} has moved to {tip}; {event.sha} is older and main is "
                "not moved backwards (the newer run promotes it)"
            )
        tags = ["main", f"gated-{event.sha}"] + (["latest"] if event.cascade else [])
        # A rebuild of the released commit (weekly errata) refreshes the release too.
        for version, commit in releases.items():
            if commit == event.sha:
                tags += _release_tags(version, releases)

    for tag in dict.fromkeys(tags):
        if tag in ("main", "latest"):
            _backup(reg, tag, digest)
        reg.copy(digest, tag)
        moved.append(tag)
    return moved


def _release_tags(version: tuple[int, int, int], releases: dict) -> list[str]:
    """X.Y.Z always; X.Y and latest only if nothing newer holds them."""
    tags = ["{}.{}.{}".format(*version)]
    same_minor = [v for v in releases if v[:2] == version[:2]]
    if not same_minor or version >= max(same_minor):
        tags.append("{}.{}".format(*version[:2]))
    if not releases or version >= max(releases):
        tags.append("latest")
    else:
        log(f"  latest stays: {'{}.{}.{}'.format(*max(releases))} is newer")
    return tags


# ------------------------------------------------------------------ boot


@dataclass
class Boot:
    """One boot gate: the image under test and how to start it."""

    image: str
    env: Sequence[str] = ()
    run_args: str = ""
    cmd: str = ""
    units: Sequence[str] = ()
    port: int = 8080
    path: str = "/mcp"
    timeout: int = BOOT_TIMEOUT

    def args(self) -> list[str]:
        """podman run arguments: the dummy environment, then the repo's extras."""
        out: list[str] = []
        for kv in self.env:
            out += ["--env", kv]
        return out + shlex.split(self.run_args)


def _podman(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["podman", *args], capture_output=True, text=True, check=check)


def _initialize() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "container-release-gate", "version": "1"},
        },
    }


def _exchange(proc: subprocess.Popen, errlog: Any, timeout: int) -> dict[int, dict]:
    """Speak initialize / initialized / tools/list on the process's stdio."""
    if proc.stdin is None or proc.stdout is None:
        raise Refused("podman run gave no stdio pipes")
    stdin, stdout = proc.stdin, proc.stdout
    # readline() blocks; a reader thread lets the deadline actually bite.
    lines: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        for line in stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()

    def stderr_tail() -> str:
        errlog.seek(0)
        return str(errlog.read())[-LOG_TAIL:]

    msgs: list[dict[str, Any]] = [
        _initialize(),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    deadline = time.monotonic() + timeout
    replies: dict[int, dict] = {}
    for msg in msgs:
        try:
            stdin.write(json.dumps(msg) + "\n")
            stdin.flush()
        except BrokenPipeError as exc:
            raise Refused(f"server exited before {msg['method']}:\n{stderr_tail()}") from exc
        while "id" in msg and msg["id"] not in replies:
            try:
                line = lines.get(timeout=max(deadline - time.monotonic(), 0.1))
            except queue.Empty:
                raise Refused(f"no reply to {msg['method']} within {timeout}s") from None
            if line is None:
                raise Refused(f"server exited before answering {msg['method']}:\n{stderr_tail()}")
            try:
                reply = json.loads(line)
            except json.JSONDecodeError:
                continue  # a log line on stdout; keep reading
            if isinstance(reply, dict) and "id" in reply:
                replies[reply["id"]] = reply
    return replies


def boot_mcp_stdio(spec: Boot) -> list[str]:
    """Run the image with stdin attached and speak MCP over stdio.

    Sends initialize, notifications/initialized and tools/list; returns the
    tool names. Refused when the server exits, stays silent past
    `spec.timeout`, fails initialize, or lists no tools.
    """
    # stderr goes to a file: a chatty server must not fill a pipe nobody reads.
    with tempfile.TemporaryFile(mode="w+") as errlog:
        proc = subprocess.Popen(
            ["podman", "run", "--rm", "-i", *spec.args(), spec.image, *shlex.split(spec.cmd)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errlog,
            text=True,
        )
        try:
            replies = _exchange(proc, errlog, spec.timeout)
        finally:
            proc.kill()
            proc.wait()
    return _tools(replies[1], replies[2])


def _post(port: int, path: str, body: dict, session: str | None) -> tuple[dict | None, str | None]:
    """POST one JSON-RPC message to the server under test on 127.0.0.1."""
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=HTTP_TIMEOUT)
    try:
        conn.request("POST", path, body=json.dumps(body), headers=headers)
        resp = conn.getresponse()
        sid = resp.getheader("Mcp-Session-Id") or session
        text = resp.read().decode()
    finally:
        conn.close()
    if resp.status >= http.HTTPStatus.BAD_REQUEST:
        raise NotReady(f"{path} answered HTTP {resp.status}: {text[:500]}")
    if "text/event-stream" in (resp.getheader("Content-Type") or ""):
        for line in text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:]), sid
        return None, sid
    return (json.loads(text) if text.strip() else None), sid


def _in_container(spec: Boot, check: Callable[[str], list[str]], *run: str) -> list[str]:
    """Start the image detached, run `check(name)`, show its logs if refused, remove it."""
    name = f"gate-{os.getpid()}"
    _podman("run", "-d", "--name", name, *run, *spec.args(), spec.image, *shlex.split(spec.cmd))
    try:
        return check(name)
    except Refused:
        log(_podman("logs", name, check=False).stdout[-LOG_TAIL:])
        raise
    finally:
        _podman("rm", "-f", name, check=False)


def boot_mcp_http(spec: Boot) -> list[str]:
    """Run the image detached and speak MCP over streamable HTTP on `spec.port`.

    Retries connection errors and HTTP error statuses (NotReady) until
    `spec.timeout`, then initializes and lists tools; returns the tool names.
    """

    def check(_name: str) -> list[str]:
        deadline = time.monotonic() + spec.timeout
        while True:
            try:
                first, sid = _post(spec.port, spec.path, _initialize(), None)
                break
            except (OSError, http.client.HTTPException, NotReady) as exc:
                if time.monotonic() > deadline:
                    raise Refused(
                        f"127.0.0.1:{spec.port}{spec.path} never answered initialize: {exc}"
                    ) from exc
                time.sleep(POLL_SECONDS)
        initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        _post(spec.port, spec.path, initialized, sid)
        listed = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        tools, _ = _post(spec.port, spec.path, listed, sid)
        return _tools(first or {}, tools or {})

    return _in_container(spec, check, "-p", f"127.0.0.1:{spec.port}:{spec.port}")


def _tools(init: dict, listed: dict) -> list[str]:
    if "result" not in init:
        raise Refused(f"initialize failed: {json.dumps(init)[:500]}")
    tools = (listed.get("result") or {}).get("tools") or []
    if not tools:
        raise Refused(f"tools/list returned no tools: {json.dumps(listed)[:500]}")
    names = [t.get("name", "?") for t in tools]
    server = init["result"].get("serverInfo", {})
    log(f"  {server.get('name', '?')} {server.get('version', '?')}: {len(names)} tools")
    return names


def boot_systemd(spec: Boot) -> list[str]:
    """Boot the image with systemd as PID 1.

    Passes when `systemctl is-system-running` reaches `running` within
    `spec.timeout` and every unit in `spec.units` is active; returns the units.
    """

    def system_state(name: str) -> str:
        # Poll, not --wait: an exec before systemd's bus is up returns nothing.
        deadline = time.monotonic() + spec.timeout
        while True:
            state = _podman("exec", name, "systemctl", "is-system-running", check=False)
            settled = state.stdout.strip()
            if settled in ("running", "degraded", "maintenance", "stopping", "offline"):
                return settled
            if time.monotonic() > deadline:
                return settled or "unreachable"
            time.sleep(POLL_SECONDS)

    def check(name: str) -> list[str]:
        state = system_state(name)
        if state != "running":
            failed = _podman("exec", name, "systemctl", "--failed", "--no-legend", check=False)
            raise Refused(f"systemd is '{state}', not running. Failed units:\n{failed.stdout}")
        inactive = [
            unit
            for unit in spec.units
            if _podman("exec", name, "systemctl", "is-active", unit, check=False).stdout.strip()
            != "active"
        ]
        if inactive:
            raise Refused(f"units not active: {', '.join(inactive)}")
        log(f"  systemd running; {len(spec.units)} required unit(s) active")
        return list(spec.units)

    return _in_container(spec, check, "--systemd=always")


def boot_healthcheck(spec: Boot) -> list[str]:
    """Run the image and wait for its own HEALTHCHECK to pass.

    Refused at once if the image declares no HEALTHCHECK, or if it is not
    healthy within `spec.timeout`.
    """
    declared = _podman(
        "image", "inspect", "--format", "{{json .Config.Healthcheck}}", spec.image
    ).stdout.strip()
    if declared in ("", "null", "<nil>", "{}"):
        raise Refused(
            "boot: healthcheck, but the image carries no HEALTHCHECK "
            "(buildah drops it in OCI format; build with --format docker)"
        )

    def check(name: str) -> list[str]:
        deadline = time.monotonic() + spec.timeout
        while _podman("healthcheck", "run", name, check=False).returncode != 0:
            if time.monotonic() > deadline:
                raise Refused(f"not healthy within {spec.timeout}s")
            time.sleep(POLL_SECONDS)
        log("  healthy")
        return ["healthy"]

    return _in_container(spec, check)


BOOTS: dict[str, Callable[[Boot], list[str]]] = {
    "mcp": boot_mcp_stdio,
    "mcp-http": boot_mcp_http,
    "systemd": boot_systemd,
    "healthcheck": boot_healthcheck,
}


# ------------------------------------------------------------------ cli


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="action", required=True)

    for name in ("resolve", "mark", "check", "promote"):
        p = sub.add_parser(name)
        # check reads the registry only to compare a release's version label.
        p.add_argument("--image", required=name != "check")
        p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
        p.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
        p.add_argument("--ref", default=os.environ.get("GITHUB_REF", ""))
        p.add_argument("--branch", default="main")
        p.add_argument("--digest", default="")
        p.add_argument("--authfile")
        p.add_argument("--cascade", action="store_true")
        p.add_argument("--outside", default="", help="globs that never reach the image")
        p.add_argument("--base", default="", help="resolve a pull request against this base")

    b = sub.add_parser("boot")
    b.add_argument("--image", required=True)
    b.add_argument("--profile", required=True, choices=sorted(BOOTS))
    b.add_argument("--env", action="append", default=[])
    b.add_argument("--run-args", default="")
    b.add_argument("--cmd", default="")
    b.add_argument("--units", default="")
    b.add_argument("--port", type=int, default=Boot.port)
    b.add_argument("--path", default=Boot.path)
    b.add_argument("--timeout", type=int, default=BOOT_TIMEOUT)

    a = ap.parse_args(argv)
    try:
        if a.action == "boot":
            spec = Boot(
                image=a.image,
                env=a.env,
                run_args=a.run_args,
                cmd=a.cmd,
                units=a.units.split(),
                port=a.port,
                path=a.path,
                timeout=a.timeout,
            )
            BOOTS[a.profile](spec)
        elif a.action == "check":
            reg = Registry(a.image, authfile=a.authfile) if a.image else None
            check(GitHub(a.repo), a.digest, Event(a.sha, a.ref, a.branch), reg)
        else:
            _registry_action(a)
    except Superseded as exc:
        log(f"::notice::{exc}")
        output("tags", "")
    except Skipped as exc:
        log(f"::notice::{exc}")
        output("skip", "true")
    except Refused as exc:
        log(f"REFUSED: {exc}")
        return 1
    return 0


def _registry_action(a: argparse.Namespace) -> None:
    reg = Registry(a.image, authfile=a.authfile)
    gh = GitHub(a.repo)
    if a.action == "resolve":
        outside = a.outside.split()
        if a.base:
            digest, why = resolve_pr(reg, gh, a.base, a.sha, outside)
        else:
            digest, why = resolve(reg, gh, a.sha, a.ref, a.branch)
            if digest is None and outside:
                digest, reason = resolve_parent(reg, gh, a.sha, outside)
                why = reason if digest else f"{why}; {reason}"
        log(why)
        output("digest", digest or "")
        output("rebuild", "false" if digest else "true")
    elif a.action == "mark":
        reg.copy(a.digest, f"gated-{a.sha}")
    else:
        event = Event(a.sha, a.ref, a.branch, a.cascade)
        output("tags", " ".join(promote(reg, gh, a.digest, event)))


if __name__ == "__main__":
    sys.exit(main())
