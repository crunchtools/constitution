#!/usr/bin/env python3
"""Open the Inherits-bump PR in every fleet repo after a constitution release (issue #22).

A repo's `Inherits:` and its pre-commit hook rev move in one PR. Before v1.45.0
the validate.yml pin moved with them; from v1.45.0 an exact constitution
workflow pin becomes the major tag (`@v1`), which each release moves (XV rule
5), and stays there. For each manifest repo behind the target this rewrites
them (the hook rev where the repo has a pre-commit config), opens a PR and
queues it for auto-merge. Validation at the new tag decides whether it lands;
a repo the new rules break keeps its PR open for a human, and the drift report
lists it.

Usage:
    fleet-bump.py [--version 1.19.0] [--only repo,repo] [--dry-run]
    fleet-bump.py --renovate [--only repo,repo] [--dry-run]
    fleet-bump.py --zizmor-callers [--only repo,repo] [--dry-run]

Run after tagging a release. Needs GH_TOKEN with contents, pull-requests and
workflows write across the org. `--renovate` is the one-off Dependabot teardown (XV):
in every repo it drops dependabot.yml and the auto-merge caller workflows. Renovate
needs no per-repo file; it runs from the org config in crunchtools/renovate-config.
`--zizmor-callers` is the one-off that marks the triggers of each repo's Gatehouse and
Ashigaru callers as reviewed for zizmor's dangerous-triggers audit (a860).
"""

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fleet_common import MANIFEST, ORG, clone, gh, load_validator, select_repos

PIN = re.compile(r"(crunchtools/constitution/\.github/workflows/[\w-]+\.yml@)v\d+\.\d+\.\d+")
INHERITS = re.compile(r"^(>\s*\*\*Inherits:\*\*.*?)v\d+\.\d+\.\d+", re.MULTILINE)
HOOK_REV = re.compile(
    r"(repo:\s*https://github\.com/crunchtools/constitution/?\s*\n\s*rev:\s*)v\d+\.\d+\.\d+"
)
# Gatehouse and Ashigaru are called at the major tag, which their releases move
# (XII, from v1.24.0). An exact pin left from before is rewritten in the same PR
# that moves Inherits: the validator a repo ran until then rejects `@v0`.
MAJOR_TAGGED = re.compile(
    r"(crunchtools/(?:gatehouse|ashigaru)/\.github/workflows/[\w-]+\.yml@v\d+)\.\d+\.\d+"
)
MAJOR_TAGS_SINCE = (1, 24, 0)
CONSTITUTION_MAJOR_SINCE = (1, 45, 0)
PRE_COMMIT = ".pre-commit-config.yaml"
# A caller of Gatehouse's or Ashigaru's reusable workflows, and the triggers
# zizmor's dangerous-triggers audit flags in one. A trigger that already carries
# a comment is left alone.
CALLER_USES = re.compile(r"crunchtools/(gatehouse|ashigaru)/\.github/workflows/[\w-]+\.ya?ml@\S+")
ON_BLOCK = re.compile(
    r"^(?:on|\"on\"|'on'):[ \t]*(?:#.*)?\n(?:(?:[ \t]+.*|[ \t]*#.*|[ \t]*)\n)*", re.MULTILINE
)
FLAGGED_TRIGGER = re.compile(
    r"^(?P<indent>[ \t]+)(?P<event>pull_request_target|workflow_run|issue_comment):[ \t]*$",
    re.MULTILINE,
)
# Why each trigger is safe, as the templates in crunchtools/gatehouse examples/
# and crunchtools/ashigaru examples/ word it. Neither product's workflows check
# out a fork's code; a caller that adds a checkout of its own is not touched.
TRIGGER_REASONS = {
    ("gatehouse", "pull_request_target"): (
        "Nothing from the PR is checked out or run: the guard reads the file list",
        "and the reviewer reads the diff, which is what makes this trigger safe here.",
    ),
    ("gatehouse", "workflow_run"): ("Re-runs a job by id; nothing from the PR is read or run.",),
    ("ashigaru", "pull_request_target"): (
        "Only a merged ashigaru/release- branch in this repository is acted on,",
        "and nothing from the pull request is checked out.",
    ),
    ("ashigaru", "workflow_run"): (
        "Only fix.yml acts on it, for an ashigaru/ branch in this repository that",
        "the Ashigaru app wrote; it never checks out a fork's code.",
    ),
    ("ashigaru", "issue_comment"): (
        "Ashigaru runs no comment's content and checks out nothing for one; an",
        "event it does not act on ends in a job that reads no secret.",
    ),
}
# The only expressions a caller may hand its jobs, through a shell job's `env:`
# or a reusable call's `with:`: none is text a pull request's author can choose
# (a number, an enum, a token, an owner/repo name and a job result). They are
# every such expression the Gatehouse templates have ever used.
SAFE_EXPRESSIONS = {
    "needs.review.result",
    "github.token",
    "github.event_name",
    "github.event.pull_request.number",
    "github.event.pull_request.head.repo.full_name",
    "github.event.pull_request.author_association",
}
# SHA-256 of each Gatehouse guard script ever shipped: a guard job's `run:`
# texts joined by newlines, from every revision of gatehouse.yml in
# crunchtools/gatehouse (examples/ and its own), crunchtools/ashigaru and this
# repo. Each was read for a checkout, a fetch, an eval and a read of the event
# payload, and has none. A shell job matching none of them is left for a human.
# Each hash is noted with the first revision that shipped it; hashing that
# revision's guard `run:` texts reproduces it.
REVIEWED_GUARDS = {
    # ashigaru .github/workflows/gatehouse.yml@550ed7a
    "adb434830b8cf3e7aee212ba15da475cafbbe1b4ddfbe8766e4a0c3207d9d9a3",
    # ashigaru .github/workflows/gatehouse.yml@6a7329d
    "64a3eb2c04ae13e796177a06b87e1fc4bbebc6af2583775744a5c593168d66c6",
    # gatehouse .github/workflows/gatehouse.yml@173ba07
    "4cc09ed71d9d347eca5b24a9ed0788c7d9209ebd4910eeb4fad3920bf3e81542",
    # gatehouse .github/workflows/gatehouse.yml@4ae89d0
    "8f5a7a79b88ac9def8e9ab6fb0fb10387454e239edf8ed9b9ad79933c5b65453",
    # gatehouse .github/workflows/gatehouse.yml@8235062
    "a6c2ddc57a742ff60c6d93f5b1ee1de60b5f8d95b50c5ff24720307230db3fe3",
    # gatehouse .github/workflows/gatehouse.yml@a9b67b6
    "7921d7109241cfa32d7be537335be247506a375dedad3b163c0c0c1d302517ca",
    # gatehouse .github/workflows/gatehouse.yml@bb5f91f
    "2b5923194ff1d0b427e3aafe47fb23a5406d14d9629f410fddfecf85b84996ee",
    # gatehouse examples/gatehouse.yml@173ba07
    "f42245d70470ae8e6cbf53c79874c2e92f65148ba9275cfd68164e644a678cf9",
    # gatehouse examples/gatehouse.yml@4ae89d0
    "945a65a82ea4caf3235365197c4c1356b5a19757dc3eb34d65b25ad0b8d3e6a6",
    # gatehouse examples/gatehouse.yml@a9b67b6
    "29e1939e73aaf3ec6cf6deeb9c44de63d60c900f7c01e7bb90f7a9dda5c619a7",
    # gatehouse examples/gatehouse.yml@bb5f91f
    "8100d68227be371beda228802cbf5445365e36e3669456cb6666fd98a6dd3112",
    # gatehouse examples/gatehouse.yml@cad0611
    "0a89f0cdc0e82e469c2c3c478eb948310b87784ae87eebde92d7829e574a086c",
}
EXPRESSION = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
ZIZMOR_IGNORE = "  # zizmor: ignore[dangerous-triggers]"
AUTOMERGE_USES = re.compile(r"(?:^|/)\.github/workflows/dependabot-automerge\.ya?ml(?:@|$)")


def major_tag_refusal(version: str) -> str | None:
    """Why pins cannot move to `@vN` yet, or None when refs/tags/vN names this release.

    A repo rewritten to `@v1` before the tag exists, or while it still names an
    older release, would run something other than what its `Inherits` adopts.
    """
    major = f"v{version.split('.')[0]}"

    def commit(tag: str) -> str:
        path = f"repos/{ORG}/constitution/commits/refs/tags/{tag}"
        return gh("api", path, "--jq", ".sha", check=False).strip()

    want, have = commit(f"v{version}"), commit(major)
    if not want:
        return f"v{version} is not tagged"
    if have != want:
        where = f"points at {have[:7]}" if have else "does not exist"
        return f"{major} {where}, not v{version} ({want[:7]}); run major-tag.yml first"
    return None


def git(root: Path, *args: str) -> None:
    """Run git in a clone; a failure raises with git's own message."""
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {root.name}: {result.stderr.strip()}")


def bump(root: Path, version: str) -> list[Path]:
    """Rewrite Inherits, every constitution workflow pin and the pre-commit hook rev.

    From v1.24.0 an exact Gatehouse or Ashigaru pin also becomes its major tag,
    and from v1.45.0 so does a constitution pin. Returns changed files.
    """
    target = tuple(int(part) for part in version.split("."))
    gates_use_major_tags = target >= MAJOR_TAGS_SINCE
    pin = f"v{target[0]}" if target >= CONSTITUTION_MAJOR_SINCE else f"v{version}"
    changed = []
    targets = [root / MANIFEST, *sorted((root / ".github" / "workflows").glob("*.y*ml"))]
    if (root / PRE_COMMIT).is_file():
        targets.append(root / PRE_COMMIT)
    for path in targets:
        text = path.read_text()
        new = INHERITS.sub(rf"\g<1>v{version}", text) if path.name == "constitution.md" else text
        new = PIN.sub(rf"\g<1>{pin}", new)
        if gates_use_major_tags:
            new = MAJOR_TAGGED.sub(r"\g<1>", new)
        if path.name == PRE_COMMIT:
            new = HOOK_REV.sub(rf"\g<1>v{version}", new)
        if new != text:
            path.write_text(new)
            changed.append(path)
    return changed


def open_pr(root: Path, name: str, branch: str, title: str, body: str) -> str:
    """Commit the clone's changes on a branch, push it, open the PR, queue auto-merge."""
    git(root, "checkout", "-b", branch)
    git(root, "add", "-A")
    git(root, "commit", "-m", title)
    git(root, "push", "-u", "origin", branch)
    url = gh(
        "pr", "create", "-R", f"{ORG}/{name}", "--head", branch, "--title", title, "--body", body
    ).strip()
    queue = subprocess.run(
        ["gh", "pr", "merge", "--auto", "--squash", url], capture_output=True, text=True
    )
    if queue.returncode != 0:
        # The PR stands; it just needs merging by hand once green.
        print(f"  warning: auto-merge not queued: {queue.stderr.strip()}", file=sys.stderr)
    return url


def open_bump_pr(root: Path, name: str, version: str, changed: list[Path]) -> str:
    """Commit the bump on a branch, push it, open the PR, queue auto-merge."""
    return open_pr(
        root,
        name,
        f"chore/constitution-v{version}",
        f"chore: inherit constitution v{version}",
        f"Moves `Inherits:` to v{version} (opened by constitution/scripts/fleet-bump.py). "
        f"An exact crunchtools workflow pin becomes its major tag (`@v1`, `@v0`, `@v2`), "
        f"which each release moves (constitution XV rule 5). Auto-merges if the repo "
        f"passes validation; otherwise it needs a fix here.",
    )


def automerge_jobs(workflow: dict) -> set[str]:
    """Ids of the jobs that call dependabot-automerge.yml (a reusable-workflow `uses:`)."""
    jobs = workflow.get("jobs") or {}
    return {
        job_id
        for job_id, job in jobs.items()
        if isinstance(job, dict) and AUTOMERGE_USES.search(str(job.get("uses", "")))
    }


def cut_job(text: str, job_id: str) -> str:
    """The workflow text without job `job_id`'s block, everything else byte for byte.

    Comments trailing the block introduce whatever follows it, so they stay;
    only the blank lines separating the cut job from them go with it.
    """
    lines = text.splitlines(keepends=True)

    def inert(line: str) -> bool:
        return not line.strip() or line.lstrip().startswith("#")

    # Only a key directly under the top-level `jobs:` is a job; the same name
    # under `on:`, `env:` or inside another job is not.
    jobs = next((i for i, line in enumerate(lines) if re.match(r"jobs:\s*(?:#.*)?$", line)), None)
    if jobs is None:
        return text
    body = [i for i in range(jobs + 1, len(lines)) if not inert(lines[i])]
    block = next((n for n, i in enumerate(body) if not lines[i][0].isspace()), len(body))
    body = body[:block]
    if not body:
        return text
    indent = len(lines[body[0]]) - len(lines[body[0]].lstrip())
    head = re.compile(rf"^ {{{indent}}}{re.escape(job_id)}:\s*(?:#.*)?$")
    start = next((i for i in body if head.match(lines[i])), None)
    if start is None:
        return text

    def outside(line: str) -> bool:
        return not inert(line) and len(line) - len(line.lstrip()) <= indent

    end = next((i for i in range(start + 1, len(lines)) if outside(lines[i])), len(lines))
    keep = next((i for i in range(start + 1, end) if all(map(inert, lines[i:end]))), end)
    while keep < end and not lines[keep].strip():
        keep += 1
    return "".join(lines[:start] + lines[keep:])


def drop_automerge(root: Path, path: Path, validator) -> str | None:
    """Remove the auto-merge caller from one workflow; returns the change, or None.

    A file whose every job is the caller is deleted. In a file with other jobs
    only the caller's job is cut, and only if the rest parses back to exactly
    the same jobs and none of them `needs` it; otherwise this raises before
    writing anything, and the repo is listed for hand work rather than losing
    its other jobs.
    """
    import yaml  # deferred, like the validator's load_yaml

    where = path.relative_to(root)
    workflow = validator.load_yaml(path)
    if workflow is None or "workflow_call" in validator.triggers(workflow):
        return None  # the reusable definition itself, or nothing we can read
    callers = automerge_jobs(workflow)
    if not callers:
        return None
    jobs = workflow.get("jobs") or {}
    if callers == set(jobs):
        path.unlink()
        return f"-{where}"
    text = path.read_text()
    for job_id in callers:
        text = cut_job(text, job_id)
    kept = {k: v for k, v in jobs.items() if k not in callers}
    needs = {
        n
        for job in kept.values()
        if isinstance(job, dict)
        for n in ([job["needs"]] if isinstance(job.get("needs"), str) else job.get("needs") or [])
    }
    try:
        after = yaml.safe_load(text)
    except yaml.YAMLError:
        after = None
    if not isinstance(after, dict) or (after.get("jobs") or {}) != kept or needs & callers:
        raise RuntimeError(
            f"{where} mixes the Dependabot auto-merge job with others and cannot be "
            f"cut cleanly; remove job(s) {', '.join(sorted(callers))} by hand"
        )
    path.write_text(text)
    return f"~{where} (-job {', '.join(sorted(callers))})"


def drop_dependabot(root: Path, validator) -> list[str]:
    """Delete the auto-merge callers, then dependabot.yml; returns the changes.

    The workflows go first: one that must be left for hand work raises before
    dependabot.yml is touched.
    """
    changes = [
        change
        for path in sorted((root / ".github" / "workflows").glob("*.y*ml"))
        if (change := drop_automerge(root, path, validator))
    ]
    dependabot = root / ".github" / "dependabot.yml"
    if dependabot.is_file():
        dependabot.unlink()
        changes.insert(0, "-.github/dependabot.yml")
    return changes


@dataclass(frozen=True)
class OneOff:
    """A one-off fleet change: what the dry run calls it, and the PR that carries it."""

    what: str
    branch: str
    title: str
    body: str


RENOVATE = OneOff(
    "drop Dependabot",
    "chore/renovate",
    "chore: drop Dependabot; Renovate runs from the org config",
    "Renovate now applies the fleet policy to every repo from "
    "`crunchtools/renovate-config`'s `org-inherited-config.json`, which extends "
    "`crunchtools/constitution` `renovate/default.json` (constitution XV), so the repo "
    "needs no config of its own. Drops `.github/dependabot.yml` and the Dependabot "
    "auto-merge caller. Opened by constitution/scripts/fleet-bump.py --renovate.",
)
ZIZMOR_CALLERS = OneOff(
    "justify caller triggers",
    "chore/zizmor-callers",
    "chore: justify the Gatehouse and Ashigaru caller triggers for zizmor",
    "zizmor (constitution XV rule 8) flags `pull_request_target`, `workflow_run` "
    "and `issue_comment` as dangerous triggers. In a Gatehouse or Ashigaru caller "
    "each is needed and safe, because neither checks out a fork's code, so each "
    "now carries an inline `zizmor: ignore[dangerous-triggers]` with its reason, "
    "as the templates do. No trigger or job changes. Opened by "
    "constitution/scripts/fleet-bump.py --zizmor-callers.",
)


def one_off_repo(name: str, clone_root: Path, one_off: OneOff, change, dry_run: bool) -> None:
    """Apply `change(root)` to one repo and open its PR; a repo it leaves alone is skipped."""
    root = clone(name, clone_root)
    changes = change(root)
    if not changes:
        return
    print(f"{name}: {one_off.what} ({', '.join(changes)})")
    if not dry_run:
        print(f"  {open_pr(root, name, one_off.branch, one_off.title, one_off.body)}")


def drop_repo(name: str, clone_root: Path, validator, dry_run: bool) -> None:
    """Drop Dependabot from one repo; a repo with nothing to delete is skipped."""
    one_off_repo(name, clone_root, RENOVATE, lambda r: drop_dependabot(r, validator), dry_run)


def ignore_caller_triggers(text: str) -> str | None:
    """The caller with each flagged trigger justified and ignored, or None if nothing changes.

    Only the reviewed caller shape is rewritten (see `caller_product`), and only
    the trigger lines under `on:`: the rest of a repo's copy stays as the repo
    has it, whichever template version it came from.
    """
    product = caller_product(text)
    on = ON_BLOCK.search(text)
    if product is None or on is None:
        return None

    def justify(match: re.Match) -> str:
        reason = TRIGGER_REASONS.get((product, match["event"]))
        if reason is None:
            return match[0]
        comments = "".join(f"{match['indent']}# {line}\n" for line in reason)
        return f"{comments}{match[0].rstrip()}{ZIZMOR_IGNORE}"

    block = FLAGGED_TRIGGER.sub(justify, on[0])
    return text[: on.start()] + block + text[on.end() :] if block != on[0] else None


def caller_product(text: str) -> str | None:
    """`gatehouse` or `ashigaru` when the workflow is a caller the trigger reasons hold for.

    That is a workflow whose every job either calls one product's reusable
    workflows (by the job's `uses:`, not by text anywhere in the file, and with
    `with:` inputs no PR author chooses) or, like
    Gatehouse's guard, is `shell_only`. Anything else is left for a human,
    because the reason written next to the ignore would not be known to be true.
    """
    import yaml  # deferred, like drop_automerge's

    try:
        workflow = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    if not isinstance(jobs, dict) or not jobs:
        return None
    products = set()
    for job in jobs.values():
        if not isinstance(job, dict):
            return None
        if "uses" in job:
            call = CALLER_USES.fullmatch(str(job["uses"]))
            if call is None or not safe_expressions(job.get("with")):
                return None
            products.add(call.group(1))
        elif not shell_only(job, workflow.get("env")):
            return None
    return products.pop() if len(products) == 1 else None


def shell_only(job: dict, workflow_env: dict | None) -> bool:
    """Whether the job is a reviewed Gatehouse guard that sees no PR-chosen text.

    Its steps run no action, their scripts together are one of REVIEWED_GUARDS,
    and every expression an `env:` (the workflow's, the job's or a step's)
    feeds them is in SAFE_EXPRESSIONS. What a script does cannot be read off its shape,
    so only scripts already read are let through. `workflow_env` is the
    workflow's top-level `env:` mapping, or None when it has none.
    """
    steps = job.get("steps")
    if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
        return False
    if any("uses" in s for s in steps):
        return False
    script = "\n".join(str(s.get("run", "")) for s in steps)
    if hashlib.sha256(script.encode()).hexdigest() not in REVIEWED_GUARDS:
        return False
    return all(
        map(safe_expressions, [workflow_env, job.get("env"), *(s.get("env") for s in steps)])
    )


def safe_expressions(mapping: dict | None) -> bool:
    """Whether every `${{ }}` in an `env:` or `with:` mapping is in SAFE_EXPRESSIONS."""
    return all(e in SAFE_EXPRESSIONS for e in EXPRESSION.findall(str(mapping or "")))


def ignore_callers(root: Path) -> list[str]:
    """Justify the flagged triggers in every Gatehouse and Ashigaru caller; returns the changes.

    A caller whose triggers are still bare but whose shape is not the reviewed
    one is listed as `?path`, for a human.
    """
    changes = []
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        text = path.read_text()
        after = ignore_caller_triggers(text)
        where = str(path.relative_to(root))
        if after is not None:
            path.write_text(after)
            changes.append(where)
        elif CALLER_USES.search(text) and caller_product(text) is None and bare_triggers(text):
            changes.append(f"?{where}")
    return changes


def bare_triggers(text: str) -> bool:
    """Whether the `on:` block still has a flagged trigger with no comment."""
    on = ON_BLOCK.search(text)
    return on is not None and FLAGGED_TRIGGER.search(on[0]) is not None


def callers_repo(name: str, clone_root: Path, dry_run: bool) -> None:
    """Justify one repo's caller triggers; a repo with nothing to change is skipped.

    A repo whose only callers need a human is reported, with no PR.
    """

    def change(root: Path) -> list[str]:
        changes = ignore_callers(root)
        if changes and all(c.startswith("?") for c in changes):
            print(f"{name}: callers for a human ({', '.join(c[1:] for c in changes)})")
            return []
        return changes

    one_off_repo(name, clone_root, ZIZMOR_CALLERS, change, dry_run)


def bump_repo(name: str, version: str, clone_root: Path, validator, dry_run: bool) -> None:
    """Bump one repo if it is a manifest repo behind `version`."""
    root = clone(name, clone_root)
    manifest = root / MANIFEST
    if not manifest.is_file():
        return
    header = validator.parse_header(manifest.read_text())
    current = validator.version_tuple(validator.extract_inherits_version(header))
    behind = validator.MANIFEST_SINCE <= (current or ()) < validator.version_tuple(version)
    if not behind:
        return
    changed = bump(root, version)
    print(f"{name}: v{'.'.join(map(str, current))} -> v{version} ({len(changed)} files)")
    if changed and not dry_run:
        print(f"  {open_bump_pr(root, name, version, changed)}")


def release_version(value: str) -> str:
    """argparse type: a bare X.Y.Z release version."""
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value, re.ASCII):
        raise argparse.ArgumentTypeError(f"{value!r} is not a X.Y.Z version")
    return value


def run(only: str | None, handle) -> int:
    """Call `handle(name, clone_root)` on each selected repo; a failure does not stop the rest."""
    failed = []
    with tempfile.TemporaryDirectory() as clone_root:
        for repo in select_repos(only):
            # One repo's clone or push timing out must not leave the rest of the fleet behind.
            try:
                handle(repo["name"], Path(clone_root))
            except RuntimeError as error:
                print(f"{repo['name']}: FAILED: {error}", file=sys.stderr)
                failed.append(repo["name"])
    if failed:
        print(f"rerun with --only {','.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--version",
        type=release_version,
        help="target version, X.Y.Z (default: this checkout's)",
    )
    for flag, purpose in (
        ("--renovate", "delete Dependabot config and auto-merge callers in every repo"),
        ("--zizmor-callers", "justify the dangerous triggers in Gatehouse and Ashigaru callers"),
    ):
        mode.add_argument(flag, action="store_true", help=f"one-off: {purpose}")
    parser.add_argument("--only", help="comma-separated repo names")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.zizmor_callers:
        return run(args.only, lambda name, root: callers_repo(name, root, args.dry_run))
    if args.renovate:
        validator = load_validator()
        return run(args.only, lambda name, root: drop_repo(name, root, validator, args.dry_run))
    validator = load_validator()
    version = args.version or validator.own_version()
    if tuple(int(part) for part in version.split(".")) >= CONSTITUTION_MAJOR_SINCE and (
        refusal := major_tag_refusal(version)
    ):
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    return run(
        args.only, lambda name, root: bump_repo(name, version, root, validator, args.dry_run)
    )


if __name__ == "__main__":
    sys.exit(main())
