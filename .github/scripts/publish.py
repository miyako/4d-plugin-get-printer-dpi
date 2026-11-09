#!/usr/bin/env python3
"""Create a new release only; never modify or delete existing publication state."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from version import read_version


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout


def absent(repo, tag):
    refs = run("git", "ls-remote", "--tags", "origin",
               f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}")
    if refs.strip():
        raise ValueError(f"Remote tag {tag} already exists")
    page = 1
    seen = set()
    while True:
        entries = json.loads(run(
            "gh", "api", "--method", "GET",
            f"repos/{repo}/releases?per_page=100&page={page}"))
        if not isinstance(entries, list) or len(entries) > 100:
            raise ValueError(f"Releases page {page} is not an array")
        for entry in entries:
            if (not isinstance(entry, dict)
                    or type(entry.get("id")) is not int or entry["id"] <= 0
                    or not isinstance(entry.get("tag_name"), str) or not entry["tag_name"]
                    or type(entry.get("draft")) is not bool):
                raise ValueError(f"Malformed release entry on page {page}")
            if entry["id"] in seen:
                raise ValueError(f"Repeated release ID on page {page}; listing changed")
            seen.add(entry["id"])
            if entry["tag_name"] == tag:
                raise ValueError(f"Release {tag} already exists (including drafts)")
        if not entries:
            return
        page += 1


def publish(repo, sha, assets):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Selected SHA must be a full immutable commit SHA")
    if run("git", "rev-parse", "HEAD").strip() != sha:
        raise ValueError("Checkout does not match selected SHA")
    tag = "v" + read_version()
    for asset in assets:
        if not Path(asset).is_file() or Path(asset).stat().st_size == 0:
            raise ValueError(f"Missing or empty release asset: {asset}")
    absent(repo, tag)
    # Push the exact selected object, without force or implicit annotated tags.
    run("git", "-c", "push.followTags=false", "push", "--no-follow-tags",
        "origin", f"{sha}:refs/tags/{tag}")
    refs = run("git", "ls-remote", "--tags", "origin",
               f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}")
    if refs.strip() != f"{sha}\trefs/tags/{tag}":
        raise ValueError("Remote tag target differs from selected SHA")
    payload = json.dumps(dict(tag_name=tag, target_commitish=sha, name=tag,
                              draft=False, prerelease=False))
    created = json.loads(run("gh", "api", "--method", "POST",
                             f"repos/{repo}/releases", "--input", "-", input=payload))
    if (not isinstance(created, dict) or type(created.get("id")) is not int
            or created["id"] <= 0 or created.get("tag_name") != tag
            or created.get("draft") is not False):
        raise ValueError("Malformed create-release response; inspect remote state")
    run("gh", "release", "upload", tag, *assets, "--repo", repo)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "publish"))
    parser.add_argument("assets", nargs="*")
    args = parser.parse_args()
    try:
        repo = os.environ["GITHUB_REPOSITORY"]
        sha = os.environ["GITHUB_SHA"]
        if args.action == "check":
            absent(repo, "v" + read_version())
        else:
            if len(args.assets) != 2:
                raise ValueError("Expected the original ZIP and DMG assets")
            publish(repo, sha, args.assets)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Publication stopped: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        print("No rollback or retry was attempted. Inspect tags, releases (including "
              "drafts), and assets; retain partial state for manual recovery. "
              "Do not rerun blindly.", file=sys.stderr)
        sys.exit(1)
