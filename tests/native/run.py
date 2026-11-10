#!/usr/bin/env python3
"""Compile actual native sources plus the unchanged bundled SDK; no project build."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "af4003cef5a196253de556327e90324da196a685"
CASES = (
    "path-owners", "temporary-owner", "copy-byte-units", "command-empty-owners",
    "array-scalar-contracts", "failure-sentinels", "exported-dispatcher",
)
DEFECTS = set(CASES[:4])


def run(source, build, baseline=False):
    sdk = source / "4D Plugin API"
    executable = build / "ownership"
    command = [
        "clang++", "-std=c++17", "-x", "objective-c++", "-g", "-O1",
        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        "-Wno-deprecated-declarations", "-Wno-parentheses",
        "-Wno-return-type-c-linkage", "-Wno-ignored-attributes",
        "-I", str(sdk), "-I", str(sdk / "Classes"),
        "-include", str(ROOT / "tests/native/platform.h"),
        str(sdk / "4DPluginAPI.c"),
        *map(str, sorted((sdk / "Classes").glob("*.cpp"))),
        str(source / "4DPlugin.cpp"), str(ROOT / "tests/native/ownership.mm"),
        "-framework", "Cocoa", "-framework", "Carbon", "-o", str(executable),
    ]
    subprocess.run(command, check=True)
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
               UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
    for case in CASES:
        for empty in ("allocated-empty", "null-empty"):
            result = subprocess.run([executable, case, empty], env=env,
                                    capture_output=True, text=True)
            failed = result.returncode != 0
            expected_failure = baseline and case in DEFECTS
            print(f"{'baseline' if baseline else 'fixed'} {case} {empty}: "
                  f"{'FAIL (expected)' if failed and expected_failure else 'FAIL' if failed else 'PASS'}",
                  flush=True)
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            if failed != expected_failure:
                raise RuntimeError(f"unexpected result: {case} {empty}")
            if expected_failure:
                signatures = {
                    "path-owners": "path string double-disposal",
                    "temporary-owner": "all picture references released",
                    "copy-byte-units": "AddressSanitizer: heap-buffer-overflow",
                    "command-empty-owners": "all picture references released",
                }
                if signatures[case] not in result.stderr:
                    raise RuntimeError(f"baseline failed for the wrong reason: {case}")


def preservation():
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASELINE, "--"], cwd=ROOT, text=True).splitlines()
    allowed = {"4D Plugin API/Classes/C_PICTURE.cpp", "README.md"}
    for path in changed:
        if path not in allowed and not path.startswith("tests/native/"):
            raise RuntimeError(f"unexpected change to preserved baseline: {path}")
    sdk = "4D Plugin API/4DPluginAPI.c"
    expected = subprocess.check_output(
        ["git", "rev-parse", f"{BASELINE}:{sdk}"], cwd=ROOT, text=True).strip()
    actual = subprocess.check_output(["git", "hash-object", sdk], cwd=ROOT, text=True).strip()
    if actual != expected:
        raise RuntimeError("bundled SDK implementation changed")
    print(f"preservation PASS; full unchanged SDK blob {actual}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true",
                        help="also require the exact four named baseline defects")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("This fixture requires macOS and Apple clang; it does not certify Windows/4D.")
    preservation()
    with tempfile.TemporaryDirectory(prefix="printer-dpi-ownership-") as directory:
        build = Path(directory)
        run(ROOT, build)
        if args.baseline:
            archive = build / "baseline.tar"
            with archive.open("wb") as stream:
                subprocess.run(["git", "archive", BASELINE], cwd=ROOT, stdout=stream, check=True)
            source = build / "baseline"
            source.mkdir()
            with tarfile.open(archive) as stream:
                stream.extractall(source, filter="data")
            run(source, build, baseline=True)


if __name__ == "__main__":
    main()
