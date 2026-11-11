#!/usr/bin/env python3
"""Build once, gate the digest, promote what was tested (container-image VII).

The logic behind .github/workflows/container-release.yml, kept here so the
refusal paths can be tested; a workflow's inline shell cannot be.

Subcommands, each run by one job of that workflow:

  resolve   on a push to the default branch or a v* tag: find the digest a
            pull request (or main) already gated, so nothing is rebuilt.
  mark      after the gates pass: tag the tested digest gated-<sha>.
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
from typing import Any

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# The MCP revision the gate speaks; servers negotiate down from it.
MCP_PROTOCOL = "2025-06-18"
BOOT_TIMEOUT = 120  # seconds; the workflow passes its own boot-timeout
HTTP_TIMEOUT = 10  # seconds per request to the server under test
POLL_SECONDS = 2
LOG_TAIL = 4000  # characters of a failed container's log worth showing
MISSING = re.compile(r"manifest unknown|not found|no such|name unknown", re.I)


class Refused(Exception):
    """A promotion that must not happen. Exit 1, tags untouched."""


class NotReady(Refused):
    """The server answered, but with an HTTP error: retried until the boot deadline."""


class Superseded(Exception):
    """A newer commit owns main; this run stands down. Exit 0, tags untouched."""


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

    def digest(self, ref: str) -> str | None:
        """The manifest digest a tag (or digest) resolves to; None if absent.

        Fails closed: any error other than 'not there' is raised, because a
        guard that cannot read the current tag must not guess.
        """
        res = self.run(["skopeo", "inspect", "--raw", *self.auth, f"docker://{self.image}{ref}"])
        if res.rc != 0:
            if MISSING.search(res.err):
                return None
            raise Refused(f"cannot read {self.image}{ref}: {res.err.strip()}")
        return "sha256:" + hashlib.sha256(res.out.encode()).hexdigest()

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

    def tip(self, branch: str) -> str:
        return str(self._object(f"commits/{branch}")["sha"])

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


def resolve(reg: Registry, gh: GitHub, sha: str, ref: str) -> tuple[str | None, str]:
    """(digest, why) for a push. digest None means: no gated image, rebuild.

    A tag must name a commit that main already promoted; it is never rebuilt,
    because a release that rebuilds ships bytes no gate saw.
    """
    marker = reg.digest(f":gated-{sha}")
    if marker:
        return marker, f"gated-{sha} exists"
    if ref.startswith("refs/tags/"):
        raise Refused(
            f"{ref} names {sha}, which main never promoted (no gated-{sha}); "
            "a release promotes main's tested image and never rebuilds"
        )
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


def promote(reg: Registry, gh: GitHub, digest: str, event: Event) -> list[str]:
    """Move the floating tags this event earns to `digest`; return them.

    `cascade`: an image other images build FROM (the ubi10 chain) cuts no
    release, so its `latest` tracks the default branch with `main`
    (container-image profile, "The cascade is the one exception").
    """
    if not DIGEST.match(digest):
        raise Refused(f"'{digest}' is not a sha256 digest")
    moved: list[str] = []
    releases = gh.release_tags()

    if event.ref.startswith("refs/tags/"):
        name = event.ref.removeprefix("refs/tags/")
        m = SEMVER.match(name)
        if not m:
            raise Refused(f"tag '{name}' is not vX.Y.Z")
        version = (int(m[1]), int(m[2]), int(m[3]))
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

    for name in ("resolve", "mark", "promote"):
        p = sub.add_parser(name)
        p.add_argument("--image", required=True)
        p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
        p.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
        p.add_argument("--ref", default=os.environ.get("GITHUB_REF", ""))
        p.add_argument("--branch", default="main")
        p.add_argument("--digest", default="")
        p.add_argument("--authfile")
        p.add_argument("--cascade", action="store_true")

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
        else:
            _registry_action(a)
    except Superseded as exc:
        log(f"::notice::{exc}")
        output("tags", "")
    except Refused as exc:
        log(f"REFUSED: {exc}")
        return 1
    return 0


def _registry_action(a: argparse.Namespace) -> None:
    reg = Registry(a.image, authfile=a.authfile)
    gh = GitHub(a.repo)
    if a.action == "resolve":
        digest, why = resolve(reg, gh, a.sha, a.ref)
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
