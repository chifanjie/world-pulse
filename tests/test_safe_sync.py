from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from tools.safe_sync import ORIGIN, RepositorySync, SyncError


def response(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["git"], code, stdout, stderr)


class SyncTests(unittest.TestCase):
    def test_real_preflight_rejects_dirty_tree_branch_and_push_origin(self):
        sync = RepositorySync()
        baseline = [str(sync.root), ORIGIN, ORIGIN, "main", ""]
        for position, bad_value, error in (
            (2, "https://github.com/someone/else.git", "Origin"),
            (3, "feature", "main branch"),
            (4, "?? user-notes.md", "not clean"),
        ):
            replies = baseline.copy()
            replies[position] = bad_value
            sync = RepositorySync()
            with patch.object(sync, "git", side_effect=replies), \
                    patch("tools.safe_sync.EXPECTED_ROOT", sync.root):
                with self.assertRaisesRegex(SyncError, error):
                    sync.preflight()

    def test_schannel_fallback_is_per_command_and_keeps_certificate_verification(self):
        sync = RepositorySync()
        with patch("tools.safe_sync.subprocess.run", side_effect=[
            response(1, stderr="schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS"),
            response(stdout="ok"),
        ]) as run:
            self.assertEqual(sync.network("pull", "--ff-only", "origin", "main"), "ok")
        self.assertEqual(run.call_args_list[1].args[0],
                         ["git", "-c", "http.sslVerify=true", "-c", "http.sslBackend=openssl",
                          "pull", "--ff-only", "origin", "main"])
        self.assertNotIn("timeout", run.call_args.kwargs)
        self.assertEqual(len(sync.recoveries), 1)

    def test_url_specific_or_environment_tls_bypass_blocks_publication(self):
        for environment, config in (("true", "true"), ("", "false")):
            sync = RepositorySync()
            replies = [str(sync.root), ORIGIN, ORIGIN, "main", "", str(sync.root / ".git"), config]
            with patch.object(sync, "git", side_effect=replies), \
                    patch("tools.safe_sync.EXPECTED_ROOT", sync.root), \
                    patch("tools.safe_sync.Path.exists", return_value=False), \
                    patch.dict("tools.safe_sync.os.environ", {"GIT_SSL_NO_VERIFY": environment}), \
                    patch.object(sync, "network") as network:
                with self.assertRaisesRegex(SyncError, "certificate verification"):
                    sync.pull()
            network.assert_not_called()

    def test_transient_errors_retry_but_stop_after_three_attempts(self):
        sync = RepositorySync()
        with patch.object(sync, "execute", return_value=response(1, stderr="Failed to connect")) as run, \
                patch("tools.safe_sync.time.sleep"):
            with self.assertRaises(SyncError):
                sync.network("fetch", "origin", "main")
        self.assertEqual(run.call_count, 3)

    def test_authentication_and_certificate_errors_do_not_trigger_workarounds(self):
        for error in ("Authentication failed", "SSL certificate problem", "Permission denied",
                      "Failed to connect: SSL certificate problem", "The requested URL returned error: 403"):
            sync = RepositorySync()
            with patch.object(sync, "execute", return_value=response(1, stderr=error)) as run:
                with self.assertRaises(SyncError):
                    sync.network("pull", "--ff-only", "origin", "main")
            self.assertEqual(run.call_count, 1)
            self.assertFalse(sync.openssl)

    def test_dirty_tree_stops_before_network(self):
        sync = RepositorySync()
        with patch.object(sync, "preflight", side_effect=SyncError("Working tree is not clean")), \
                patch.object(sync, "network") as network:
            with self.assertRaises(SyncError):
                sync.pull()
        network.assert_not_called()

    def test_remote_advance_blocks_push(self):
        sync = RepositorySync()
        with patch.object(sync, "preflight"), patch.object(sync, "git", return_value="local"), \
                patch.object(sync, "remote_head", return_value="someone-else"), \
                patch.object(sync, "network") as network:
            with self.assertRaisesRegex(SyncError, "Remote changed"):
                sync.push("base")
        network.assert_not_called()

    def test_successful_push_must_be_observed_on_live_remote(self):
        sync = RepositorySync()
        with patch.object(sync, "preflight"), patch.object(sync, "git", return_value="local"), \
                patch.object(sync, "remote_head", side_effect=["base", "base"]), \
                patch.object(sync, "network"):
            with self.assertRaisesRegex(SyncError, "live remote"):
                sync.push("base")

    def test_already_published_does_not_push_twice(self):
        sync = RepositorySync()
        with patch.object(sync, "preflight"), patch.object(sync, "git", return_value="local"), \
                patch.object(sync, "remote_head", return_value="local"), \
                patch.object(sync, "network") as network:
            self.assertEqual(sync.push("base")["status"], "already-published")
        network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
