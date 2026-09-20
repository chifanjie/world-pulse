#!/usr/bin/env python3
"""Synchronize this repository with bounded retries and verified remote state."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ROOT = Path(r"C:\Users\cfj\Documents\Codex\2026-08-03\ni-k\outputs\world-pulse")
ORIGIN = "https://github.com/chifanjie/world-pulse.git"
TRANSIENT_ERRORS = (
    "could not resolve host", "failed to connect", "connection reset",
    "connection was reset", "connection timed out", "operation timed out",
    "remote end hung up", "http 502", "http 503", "http 504",
    "requested url returned error: 502", "requested url returned error: 503",
    "requested url returned error: 504",
)
BLOCKING_ERRORS = (
    "authentication failed", "permission denied", "access denied",
    "certificate problem", "certificate verify failed", "certificate verification failed",
    "requested url returned error: 401", "requested url returned error: 403",
)


class SyncError(RuntimeError):
    pass


class RepositorySync:
    def __init__(self, root: Path = ROOT):
        self.root = root.resolve()
        self.openssl = False
        self.recoveries: list[str] = []

    def execute(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        command = ["git", "-c", "http.sslVerify=true"]
        if self.openssl:
            command += ["-c", "http.sslBackend=openssl"]
        # No total runtime deadline: a running fetch/push is allowed to finish.
        return subprocess.run(
            command + args, cwd=self.root, capture_output=True,
            text=True, encoding="utf-8", errors="replace", check=False,
        )

    def git(self, *args: str) -> str:
        result = self.execute(list(args))
        if result.returncode:
            raise SyncError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def network(self, *args: str) -> str:
        for attempt in range(3):
            result = self.execute(list(args))
            if result.returncode == 0:
                return result.stdout.strip()
            error = (result.stderr + "\n" + result.stdout).strip()
            lower = error.lower()
            if any(token in lower for token in BLOCKING_ERRORS):
                raise SyncError(error)
            if ("schannel" in lower and "sec_e_no_credentials" in lower
                    and not self.openssl and attempt < 2):
                self.openssl = True
                self.recoveries.append("Schannel credentials failed; retry using per-command OpenSSL")
            elif any(token in lower for token in TRANSIENT_ERRORS) and attempt < 2:
                self.recoveries.append(f"Transient connection failure; retry {attempt + 1}")
                time.sleep(attempt + 1)
            else:
                raise SyncError(error)
        raise SyncError("Network recovery exhausted")

    def preflight(self) -> None:
        if self.root != EXPECTED_ROOT.resolve():
            raise SyncError("Repository path is not the authorized World Pulse directory")
        if Path(self.git("rev-parse", "--show-toplevel")).resolve() != self.root:
            raise SyncError("Git root does not match the authorized directory")
        for extra in ([], ["--push"]):
            urls = self.git("remote", "get-url", *extra, "--all", "origin").splitlines()
            if urls != [ORIGIN]:
                raise SyncError("Origin fetch/push URL does not match the authorized repository")
        if self.git("branch", "--show-current") != "main":
            raise SyncError("Expected main branch")
        if self.git("status", "--porcelain=v1", "--untracked-files=all"):
            raise SyncError("Working tree is not clean; preserve changes and inspect ownership")
        git_dir = Path(self.git("rev-parse", "--absolute-git-dir"))
        for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD",
                     "rebase-merge", "rebase-apply", "sequencer", "BISECT_START", "index.lock"):
            if (git_dir / name).exists():
                raise SyncError(f"In-progress Git operation or lock: {name}")
        no_verify = os.environ.get("GIT_SSL_NO_VERIFY", "").lower()
        if no_verify not in ("", "0", "false", "no", "off"):
            raise SyncError("GIT_SSL_NO_VERIFY would bypass certificate verification; stop without changing it")
        verification = self.git("config", "--get-urlmatch", "http.sslVerify", ORIGIN).lower()
        if verification not in ("true", "1", "yes", "on"):
            raise SyncError("Effective certificate verification for origin is disabled; stop without changing config")

    def remote_head(self) -> str:
        lines = self.network("ls-remote", "origin", "refs/heads/main").splitlines()
        if len(lines) != 1 or lines[0].split()[1:] != ["refs/heads/main"]:
            raise SyncError("Remote main cannot be identified unambiguously")
        return lines[0].split()[0]

    def pull(self) -> dict[str, object]:
        self.preflight()
        self.network("pull", "--ff-only", "origin", "main")
        self.preflight()
        head = self.git("rev-parse", "HEAD")
        if head != self.remote_head():
            raise SyncError("Local and live remote main differ; inspect pending commits/concurrency")
        return {"status": "synchronized", "head": head, "recoveries": self.recoveries}

    def push(self, expected_remote: str) -> dict[str, object]:
        self.preflight()
        head = self.git("rev-parse", "HEAD")
        live = self.remote_head()
        if live == head:
            return {"status": "already-published", "head": head, "recoveries": self.recoveries}
        if live != expected_remote:
            raise SyncError("Remote changed since the approved work began; stop for concurrency review")
        self.git("merge-base", "--is-ancestor", expected_remote, head)
        self.network("push", "origin", "main")
        if self.remote_head() != head:
            raise SyncError("Push returned but live remote main does not equal the published commit")
        return {"status": "published", "head": head, "recoveries": self.recoveries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pull", "push"])
    parser.add_argument("--expected-remote", help="Live main SHA recorded before this work (required for push)")
    args = parser.parse_args(argv)
    if args.action == "push" and not args.expected_remote:
        parser.error("push requires --expected-remote")
    sync = RepositorySync()
    try:
        result = sync.pull() if args.action == "pull" else sync.push(args.expected_remote)
    except (SyncError, OSError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc), "recoveries": sync.recoveries}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
