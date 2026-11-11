"""scripts/container_release.py: what reaches a floating tag, and what never does.

The registry and GitHub are fakes behind the one Runner seam, so every
refusal path runs here instead of in a release.
"""

from __future__ import annotations

import hashlib
import http.server
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "container_release", ROOT / "scripts/container_release.py"
)
assert spec and spec.loader
CR = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = CR
spec.loader.exec_module(CR)

IMAGE = "quay.io/crunchtools/canary"
REPO = "crunchtools/canary"


def manifest(name: str) -> str:
    return json.dumps({"schemaVersion": 2, "name": name})


def digest_of(raw: str) -> str:
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


class World:
    """A fake Quay repository and a fake GitHub repository, one runner."""

    def __init__(self) -> None:
        self.blobs: dict[str, str] = {}  # digest -> raw manifest
        self.tags: dict[str, str] = {}  # tag -> digest
        self.trees: dict[str, str] = {}  # commit -> tree
        self.pulls: dict[str, list] = {}  # commit -> PRs
        self.tip = ""
        self.release: dict[str, str] = {}  # vX.Y.Z -> commit
        self.read_error = False
        self.copies: list[str] = []

    def image(self, name: str, tag: str | None = None) -> str:
        raw = manifest(name)
        d = digest_of(raw)
        self.blobs[d] = raw
        if tag:
            self.tags[tag] = d
        return d

    def skopeo(self, argv):
        """The registry runner: `skopeo copy` and `skopeo inspect --raw`."""
        argv = list(argv)
        result = CR.Result(0, "", "")
        if argv[1] == "copy":
            assert "--preserve-digests" in argv
            tag = argv[-1].rsplit(":", 1)[1]
            self.tags[tag] = argv[-2].split("@", 1)[1]
            self.copies.append(tag)
        elif self.read_error:
            result = CR.Result(1, "", "connection reset by peer")
        else:
            ref = argv[-1].removeprefix(f"docker://{IMAGE}")
            d = ref[1:] if ref.startswith("@") else self.tags.get(ref[1:])
            if d is not None and d in self.blobs:
                result = CR.Result(0, self.blobs[d], "")
            else:
                result = CR.Result(1, "", "manifest unknown")
        return result

    def gh(self, argv):
        """The GitHub runner: tags, commit trees, merged pulls, the branch tip."""
        argv = list(argv)
        if "--paginate" in argv:
            lines = "\n".join(f"{n}\t{c}" for n, c in self.release.items())
            return CR.Result(0, lines, "")
        path = argv[2].removeprefix(f"repos/{REPO}/")
        if path.startswith("git/commits/"):
            found = {"tree": {"sha": self.trees[path.removeprefix("git/commits/")]}}
        elif path.endswith("/pulls"):
            found = self.pulls.get(path.split("/")[1], [])
        else:
            found = {"sha": self.tip}
        return CR.Result(0, json.dumps(found), "")


@pytest.fixture
def w():
    return World()


def parts(w):
    return CR.Registry(IMAGE, w.skopeo), CR.GitHub(REPO, w.gh)


def merged(w, merge, head, number=7, same_tree=True):
    w.trees[merge] = "T1"
    w.trees[head] = "T1" if same_tree else "T2"
    w.pulls[merge] = [
        {
            "number": number,
            "merge_commit_sha": merge,
            "merged_at": "2026-11-11T00:00:00Z",
            "head": {"sha": head},
        }
    ]


# ---------------------------------------------------------------- resolve


def test_merge_promotes_the_pr_image_without_rebuilding(w):
    d = w.image("pr", "gated-head1")
    merged(w, "merge1", "head1")
    digest, why = CR.resolve(*parts(w), "merge1", "refs/heads/main")
    assert digest == d and "PR #7" in why


def test_merge_whose_source_differs_from_the_tested_head_rebuilds(w):
    w.image("pr", "gated-head1")
    merged(w, "merge1", "head1", same_tree=False)
    digest, why = CR.resolve(*parts(w), "merge1", "refs/heads/main")
    assert digest is None and "tree differs" in why


def test_merge_of_a_pr_that_could_not_push_rebuilds(w):
    merged(w, "merge1", "head1")
    digest, why = CR.resolve(*parts(w), "merge1", "refs/heads/main")
    assert digest is None and "never gated" in why


def test_a_rerun_finds_its_own_marker(w):
    d = w.image("main", "gated-merge1")
    assert CR.resolve(*parts(w), "merge1", "refs/heads/main")[0] == d


def test_a_release_of_a_commit_main_never_promoted_is_refused(w):
    with pytest.raises(CR.Refused, match="never promoted"):
        CR.resolve(*parts(w), "c9", "refs/tags/v1.2.0")


def test_a_failed_registry_read_fails_closed(w):
    w.read_error = True
    with pytest.raises(CR.Refused, match="cannot read"):
        CR.resolve(*parts(w), "merge1", "refs/heads/main")


# ---------------------------------------------------------------- promote


def test_main_moves_and_the_old_digest_is_kept_for_rollback(w):
    old = w.image("old", "main")
    new = w.image("new")
    w.tip = "c2"
    moved = CR.promote(*parts(w), new, CR.Event("c2", "refs/heads/main"))
    assert moved == ["main", "gated-c2"]
    assert w.tags["main"] == new and w.tags["rollback-main"] == old


def test_an_older_commit_never_moves_main_back(w):
    current = w.image("newer", "main")
    w.tip = "c3"
    with pytest.raises(CR.Superseded):
        CR.promote(*parts(w), w.image("older"), CR.Event("c2", "refs/heads/main"))
    assert w.tags["main"] == current and not w.copies


def test_a_same_commit_rebuild_moves_main(w):
    w.image("monday", "main")
    tuesday = w.image("tuesday")
    w.tip = "c2"
    CR.promote(*parts(w), tuesday, CR.Event("c2", "refs/heads/main"))
    assert w.tags["main"] == tuesday


def test_a_rebuild_of_the_released_commit_refreshes_the_release(w):
    w.release = {"v1.4.0": "c2"}
    errata = w.image("errata")
    w.tip = "c2"
    moved = CR.promote(*parts(w), errata, CR.Event("c2", "refs/heads/main"))
    assert {"main", "1.4.0", "1.4", "latest"} <= set(moved)


def test_a_release_moves_latest_and_its_versions(w):
    w.release = {"v1.3.0": "c1", "v1.4.0": "c2"}
    d = w.image("rel")
    moved = CR.promote(*parts(w), d, CR.Event("c2", "refs/tags/v1.4.0"))
    assert moved == ["1.4.0", "1.4", "latest"]


def test_a_patch_to_an_old_line_never_takes_latest(w):
    w.release = {"v1.3.1": "c5", "v1.4.0": "c4"}
    latest = w.image("1.4.0", "latest")
    moved = CR.promote(*parts(w), w.image("1.3.1"), CR.Event("c5", "refs/tags/v1.3.1"))
    assert moved == ["1.3.1", "1.3"] and w.tags["latest"] == latest


def test_a_tag_that_is_not_semver_is_refused(w):
    with pytest.raises(CR.Refused, match=r"not vX\.Y\.Z"):
        CR.promote(*parts(w), w.image("x"), CR.Event("c1", "refs/tags/v1.4"))


def test_a_failed_read_of_the_tag_being_moved_fails_closed(w):
    w.tip = "c2"
    d = w.image("new")
    w.read_error = True
    with pytest.raises(CR.Refused):
        CR.promote(*parts(w), d, CR.Event("c2", "refs/heads/main"))
    assert not w.copies


def test_a_copy_that_lands_a_different_digest_fails(w):
    w.tip = "c2"
    d = w.image("new")

    def mutating(argv):
        res = w.skopeo(argv)
        if list(argv)[:2] == ["skopeo", "copy"]:
            w.tags[list(argv)[-1].rsplit(":", 1)[1]] = w.image("rewrapped")
        return res

    with pytest.raises(CR.Refused, match="not the promoted"):
        CR.promote(
            CR.Registry(IMAGE, mutating),
            CR.GitHub(REPO, w.gh),
            d,
            CR.Event("c2", "refs/heads/main"),
        )


def test_promote_refuses_something_that_is_not_a_digest(w):
    with pytest.raises(CR.Refused, match="not a sha256"):
        CR.promote(*parts(w), "latest", CR.Event("c2", "refs/heads/main"))


def test_the_cli_exits_zero_when_superseded_and_one_when_refused(w, monkeypatch, capsys):
    monkeypatch.setattr(CR.Registry.__init__, "__defaults__", (w.skopeo, None))
    monkeypatch.setattr(CR.GitHub.__init__, "__defaults__", (w.gh,))
    w.tip = "c3"
    d = w.image("x")
    args = [
        "promote",
        "--image",
        IMAGE,
        "--repo",
        REPO,
        "--digest",
        d,
        "--sha",
        "c2",
        "--ref",
        "refs/heads/main",
    ]
    assert CR.main(args) == 0
    w.tip = "c2"
    w.read_error = True
    assert CR.main(args) == 1


def test_a_cascade_image_moves_latest_with_main(w):
    w.image("old", "latest")
    d = w.image("new")
    w.tip = "c2"
    moved = CR.promote(*parts(w), d, CR.Event("c2", "refs/heads/main", "main", cascade=True))
    assert "latest" in moved and w.tags["latest"] == d and "rollback-latest" in w.tags


def test_a_leaf_image_never_moves_latest_from_main(w):
    w.tip = "c2"
    moved = CR.promote(*parts(w), w.image("new"), CR.Event("c2", "refs/heads/main"))
    assert "latest" not in moved


# ---------------------------------------------------------------- MCP over HTTP


class _Server(http.server.BaseHTTPRequestHandler):
    """Answers like a streamable-http MCP server; the class attrs pick the shape."""

    status = 200
    sse = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reply = {"jsonrpc": "2.0", "id": body.get("id"), "result": {"tools": [{"name": "t"}]}}
        payload = (
            f"event: message\ndata: {json.dumps(reply)}\n\n" if self.sse else json.dumps(reply)
        )
        self.send_response(self.status)
        self.send_header("Content-Type", "text/event-stream" if self.sse else "application/json")
        self.send_header("Mcp-Session-Id", "s-1")
        self.end_headers()
        self.wfile.write(payload.encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    def start(status=200, sse=False):
        handler = type("H", (_Server,), {"status": status, "sse": sse})
        httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return httpd.server_address[1]

    started: list = []
    yield start
    for httpd in started:
        httpd.shutdown()


def test_post_reads_a_json_reply_and_the_session(server):
    reply, sid = CR._post(
        server(), "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, None
    )
    assert reply["result"]["tools"] and sid == "s-1"


def test_post_reads_an_event_stream_reply(server):
    asked = {"jsonrpc": "2.0", "id": "list", "method": "tools/list"}
    reply, sid = CR._post(server(sse=True), "/mcp", asked, "s-0")
    assert reply["id"] == asked["id"] and sid == "s-1"


def test_an_http_error_is_not_ready_so_startup_retries_it(server):
    with pytest.raises(CR.NotReady, match="503"):
        CR._post(server(status=503), "/mcp", {"jsonrpc": "2.0", "id": 1}, None)
    assert issubclass(CR.NotReady, CR.Refused)


def test_a_closed_port_is_a_connection_error():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(OSError):
        CR._post(port, "/mcp", {}, None)


def test_tools_refuses_an_empty_tool_list():
    with pytest.raises(CR.Refused, match="no tools"):
        CR._tools({"result": {}}, {"result": {"tools": []}})


def test_the_cli_passes_cascade_through(w, monkeypatch):
    monkeypatch.setattr(CR.Registry.__init__, "__defaults__", (w.skopeo, None))
    monkeypatch.setattr(CR.GitHub.__init__, "__defaults__", (w.gh,))
    w.tip = "c2"
    d = w.image("x")
    args = [
        "promote",
        "--image",
        IMAGE,
        "--repo",
        REPO,
        "--digest",
        d,
        "--sha",
        "c2",
        "--ref",
        "refs/heads/main",
        "--cascade",
    ]
    assert CR.main(args) == 0
    assert w.tags["latest"] == d


# ---------------------------------------------------------------- MCP over stdio

# A real process speaking MCP on stdio, so _exchange is tested against pipes,
# not mocks. MODE picks the behaviour.
STDIO_SERVER = r"""
import json, sys, time
mode = sys.argv[1]
if mode == "exit":
    print("boom", file=sys.stderr)
    sys.exit(3)
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    if mode == "silent":
        time.sleep(30)
    print("a log line on stdout", flush=True)
    result = {"tools": [{"name": "t"}]} if msg["method"] == "tools/list" else {
        "serverInfo": {"name": "fake", "version": "1"}}
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
"""


def stdio(mode, timeout=10):
    with tempfile.TemporaryFile(mode="w+") as errlog:
        proc = subprocess.Popen(
            [sys.executable, "-c", STDIO_SERVER, mode],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errlog,
            text=True,
        )
        try:
            return CR._exchange(proc, errlog, timeout)
        finally:
            proc.kill()
            proc.wait()


def test_stdio_exchange_skips_log_lines_and_lists_tools():
    replies = stdio("ok")
    assert CR._tools(replies[1], replies[2]) == ["t"]


def test_stdio_server_that_exits_is_refused_with_its_stderr():
    with pytest.raises(CR.Refused, match="boom"):
        stdio("exit")


def test_stdio_server_that_never_answers_is_refused_at_the_deadline():
    with pytest.raises(CR.Refused, match="within 1s"):
        stdio("silent", timeout=1)
