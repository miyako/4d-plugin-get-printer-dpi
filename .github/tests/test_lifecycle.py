import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
import version
import publish

SHA = "a" * 40


class Versions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in (version.PBX, version.PLIST, version.STRINGS):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, self.root / path)

    def test_live_and_temporary_bumps(self):
        current = version.read_version()
        major, minor, patch_number = map(int, current.split("."))
        for mode, expected in (
            ("patch", f"{major}.{minor}.{patch_number + 1}"),
            ("minor", f"{major}.{minor + 1}.0"),
            ("major", f"{major + 1}.0.0"),
        ):
            with self.subTest(mode=mode):
                for path in (version.PBX, version.PLIST, version.STRINGS):
                    shutil.copyfile(ROOT / path, self.root / path)
                self.assertEqual(version.bump(mode, self.root), expected)
                self.assertEqual(version.read_version(self.root), expected)
                self.assertEqual(version.bump("patch", self.root),
                                 expected.rsplit(".", 1)[0] + "." +
                                 str(int(expected.rsplit(".", 1)[1]) + 1))

    def test_malformed_and_drift(self):
        path = self.root / version.PBX
        original = path.read_text()
        current = version.read_version(self.root)
        for bad in ("01.2.3", "1.2", "1.2.3-beta", "garbage", "999.888.777"):
            with self.subTest(bad=bad):
                path.write_text(original.replace(
                    f"CURRENT_PROJECT_VERSION = {current};",
                    f"CURRENT_PROJECT_VERSION = {bad};", 1))
                with self.assertRaises(ValueError):
                    version.read_version(self.root)

    def test_plist_references(self):
        path = self.root / version.PLIST
        data = path.read_text().replace(
            f"<string>{version.read_version(self.root)}</string>",
            "<string>$(MARKETING_VERSION)</string>")
        data = data.replace("</dict>", "<key>CFBundleVersion</key>"
                            "<string>$(CURRENT_PROJECT_VERSION)</string></dict>")
        path.write_text(data)
        version.bump("patch", self.root)
        self.assertIn("$(MARKETING_VERSION)", path.read_text())
        self.assertIn("$(CURRENT_PROJECT_VERSION)", path.read_text())

    def test_localized_and_plist_drift(self):
        current = version.read_version(self.root)
        for relative in (version.PLIST, version.STRINGS):
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(original.replace(current.encode(), b"99.88.77"))
                with self.assertRaises(ValueError):
                    version.read_version(self.root)
                path.write_bytes(original)

    def test_malformed_plist(self):
        path = self.root / version.PLIST
        original = path.read_text()
        for data in ("not XML", original.replace(
                "</dict>", "<key>CFBundleShortVersionString</key>"
                "<string>99.88.77</string></dict>"),
                '<?xml version="1.0"?><plist version="1.0"><array/></plist>'):
            with self.subTest(data=data):
                path.write_text(data)
                with self.assertRaises(ValueError):
                    version.read_version(self.root)


class Publication(unittest.TestCase):
    def test_later_page_draft_and_successful_empty_end(self):
        tag = "v" + version.read_version()
        first = [dict(id=i + 1, tag_name=f"other-{i}", draft=False)
                 for i in range(100)]
        for last, fails in (([dict(id=101, tag_name=tag, draft=True)], True),
                            ([], False)):
            with patch.object(publish, "run",
                              side_effect=["", json.dumps(first), json.dumps(last)]) as run:
                if fails:
                    with self.assertRaises(ValueError):
                        publish.absent("owner/repo", tag)
                else:
                    publish.absent("owner/repo", tag)
                self.assertIn("page=2", run.call_args.args[-1])

    def test_fail_closed(self):
        error = subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 404")
        for response in ("{}", "null", "not json", '[{}]',
                         '[{"id":true,"tag_name":"x","draft":false}]',
                         '[{"id":1,"tag_name":"x","draft":"false"}]', error):
            with self.subTest(response=response):
                with patch.object(publish, "run", side_effect=["", response]):
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        publish.absent("owner/repo", "v1.2.3")
        with patch.object(publish, "run", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                publish.absent("owner/repo", "v1.2.3")
        with patch.object(publish, "run", return_value="existing tag"):
            with self.assertRaises(ValueError):
                publish.absent("owner/repo", "v1.2.3")

    def test_later_page_errors_and_repeated_pages(self):
        first = json.dumps([dict(id=1, tag_name="another-tag", draft=False)])
        for later in ('{}', '[null]', 'invalid', first,
                      subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 403"),
                      subprocess.CalledProcessError(1, ["gh"], stderr="network failure")):
            with self.subTest(later=later):
                with patch.object(publish, "run", side_effect=["", first, later]):
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        publish.absent("owner/repo", "v1.2.3")

    def test_selected_sha(self):
        for sha, head in (("branch", SHA), (SHA, "b" * 40)):
            with patch.object(publish, "run", return_value=head):
                with self.assertRaises(ValueError):
                    publish.publish("owner/repo", sha, [])

    def test_create_and_upload_failures_retain_state(self):
        tag = "v" + version.read_version()
        for failure in ("push", "verify", "post", "upload", None):
            calls = []

            def fake(*args, **kwargs):
                calls.append(args)
                if args[:2] == ("git", "rev-parse"):
                    return SHA + "\n"
                if args[:2] == ("git", "ls-remote"):
                    if any("push" in c for c in calls[:-1]):
                        return f"{'b' * 40 if failure == 'verify' else SHA}\trefs/tags/{tag}\n"
                    return ""
                if args[:4] == ("gh", "api", "--method", "GET"):
                    return "[]"
                if args[0] == "git" and "push" in args:
                    self.assertIn("--no-follow-tags", args)
                    self.assertEqual(args[-1], f"{SHA}:refs/tags/{tag}")
                    if failure == "push":
                        raise subprocess.CalledProcessError(1, args, stderr="tag race")
                    return ""
                if args[:4] == ("gh", "api", "--method", "POST"):
                    self.assertEqual(json.loads(kwargs["input"]), dict(
                        tag_name=tag, name=tag, target_commitish=SHA,
                        draft=False, prerelease=False))
                    if failure == "post":
                        raise subprocess.CalledProcessError(1, args, stderr="post failed")
                    return json.dumps(dict(id=42, tag_name=tag, draft=False))
                if args[:3] == ("gh", "release", "upload"):
                    if failure == "upload":
                        raise subprocess.CalledProcessError(1, args, stderr="upload failed")
                    return ""
                self.fail(f"Unexpected command: {args}")

            with tempfile.TemporaryDirectory() as temp:
                assets = [str(Path(temp) / name) for name in ("plugin.zip", "plugin.dmg")]
                for asset in assets:
                    Path(asset).write_bytes(b"fixture")
                with patch.object(publish, "run", side_effect=fake):
                    if failure:
                        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                            publish.publish("owner/repo", SHA, assets)
                    else:
                        publish.publish("owner/repo", SHA, assets)
            flat = [arg for call in calls for arg in call]
            for forbidden in ("DELETE", "PATCH", "--clobber", "--force", "delete", "create"):
                self.assertNotIn(forbidden, flat)
            self.assertEqual(sum(call[:4] == ("gh", "api", "--method", "POST")
                                 for call in calls), int(failure not in ("push", "verify")))


class WorkflowContract(unittest.TestCase):
    def test_manual_immutable_and_gate_order(self):
        build = (ROOT / ".github/workflows/release.yml").read_text()
        bump = (ROOT / ".github/workflows/bump-version.yml").read_text()
        self.assertIn("name: Build\n", build)
        trigger = build.split("\non:\n")[1].split("\npermissions:")[0]
        self.assertEqual(trigger.strip(), "workflow_dispatch:")
        self.assertIn("group: release-publication", build)
        self.assertEqual(build.count("uses: actions/checkout@v4"),
                         build.count("ref: ${{ github.sha }}"))
        steps = ["check prebuilt libraries", "import Developer ID certificate",
                 "store notarytool credentials", "build macOS plugin",
                 "verify universal binary", "name: codesign",
                 "name: package, notarize & staple", "name: create GitHub Release"]
        positions = [build.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('xcrun stapler staple "$DMG_PATH"', build)
        self.assertNotIn("continue-on-error", build)
        self.assertNotIn("if: always()", build)
        self.assertIn('publish.py publish "$ZIP_PATH" "$DMG_PATH"', build)
        self.assertIn('[ "$GITHUB_REF_TYPE" != branch ]', bump)
        self.assertIn('[ "$(git rev-parse HEAD)" != "$GITHUB_SHA" ]', bump)
        self.assertIn('git ls-remote --heads origin "refs/heads/$GITHUB_REF_NAME"', bump)
        self.assertIn('--no-follow-tags origin "HEAD:refs/heads/$GITHUB_REF_NAME"', bump)
        self.assertNotIn("git tag", bump)
        self.assertNotIn("--force", bump)
        for mode in ("patch", "minor", "major"):
            self.assertIn(f"- {mode}", bump)

    def test_nonforced_branch_and_tag_races(self):
        def git(*args, cwd):
            return subprocess.run(("git", *args), cwd=cwd, check=True,
                                  text=True, capture_output=True).stdout.strip()

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote, first, second = [root / p for p in ("remote.git", "first", "second")]
            git("init", "--bare", str(remote), cwd=root)
            git("clone", str(remote), str(first), cwd=root)
            for path in (first,):
                git("config", "user.email", "fixture@example.invalid", cwd=path)
                git("config", "user.name", "Fixture", cwd=path)
            git("commit", "--allow-empty", "-m", "base", cwd=first)
            git("push", "origin", "HEAD:refs/heads/selected", cwd=first)
            base = git("rev-parse", "HEAD", cwd=first)
            git("clone", "--branch", "selected", str(remote), str(second), cwd=root)
            git("config", "user.email", "fixture@example.invalid", cwd=second)
            git("config", "user.name", "Fixture", cwd=second)
            git("commit", "--allow-empty", "-m", "race", cwd=second)
            git("push", "origin", "HEAD:refs/heads/selected", cwd=second)
            git("commit", "--allow-empty", "-m", "bump", cwd=first)
            with self.assertRaises(subprocess.CalledProcessError):
                git("-c", "push.followTags=false", "push", "--no-follow-tags",
                    "origin", "HEAD:refs/heads/selected", cwd=first)
            git("push", "origin", f"{base}:refs/tags/v1.2.3", cwd=second)
            with self.assertRaises(subprocess.CalledProcessError):
                git("-c", "push.followTags=false", "push", "--no-follow-tags",
                    "origin", "HEAD:refs/tags/v1.2.3", cwd=first)
            self.assertEqual(git("ls-remote", "--tags", "origin",
                                 "refs/tags/v1.2.3", cwd=first),
                             f"{base}\trefs/tags/v1.2.3")


if __name__ == "__main__":
    unittest.main()
