#!/usr/bin/env python3
"""Validate and bump coordinated source versions, never prebuilt bundles."""
import argparse
from pathlib import Path
import plistlib
import re

ROOT = Path(__file__).resolve().parents[2]
PBX = Path("get-printer-dpi.xcodeproj/project.pbxproj")
PLIST = Path("Info.plist")
STRINGS = Path("English.lproj/InfoPlist.strings")
VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


class UniqueKeys(dict):
    def __setitem__(self, key, value):
        if key in self:
            raise ValueError(f"Duplicate plist key: {key}")
        super().__setitem__(key, value)


def read_version(root=ROOT):
    project = (root / PBX).read_text()
    values = []
    for key in ("MARKETING_VERSION", "CURRENT_PROJECT_VERSION"):
        fields = re.findall(rf"\b{key}\s*=\s*([^;]+);", project)
        if len(fields) != 3:
            raise ValueError(f"{PBX}: expected three {key} fields")
        values.extend(fields)
    with (root / PLIST).open("rb") as stream:
        info = plistlib.load(stream, dict_type=UniqueKeys)
    if not isinstance(info, dict):
        raise ValueError(f"{PLIST}: expected a dictionary")
    for key, reference in (
        ("CFBundleShortVersionString", "$(MARKETING_VERSION)"),
        ("CFBundleVersion", "$(CURRENT_PROJECT_VERSION)"),
    ):
        if key == "CFBundleVersion" and key not in info:
            continue
        value = info.get(key)
        if value != reference:
            values.append(value)
    strings = (root / STRINGS).read_text(encoding="utf-8-sig")
    for pattern in (
        r'CFBundleShortVersionString\s*=\s*"([^"]*)";',
        r'CFBundleGetInfoString\s*=\s*"get-printer-dpi version ([^,]*), Copyright 2016 miyako\.";'
    ):
        matches = re.findall(pattern, strings)
        if len(matches) != 1:
            raise ValueError(f"{STRINGS}: missing or duplicate version field")
        values.extend(matches)
    if any(not isinstance(v, str) or not re.fullmatch(VERSION, v) for v in values):
        raise ValueError(f"Malformed source version metadata: {values!r}")
    if len(set(values)) != 1:
        raise ValueError(f"Source version drift: {values!r}")
    return values[0]


def bump(mode, root=ROOT):
    old = read_version(root)
    parts = list(map(int, old.split(".")))
    index = ("major", "minor", "patch").index(mode)
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    new = ".".join(map(str, parts))
    project = root / PBX
    project.write_bytes(re.sub(
        rb"((?:MARKETING_VERSION|CURRENT_PROJECT_VERSION)\s*=\s*)"
        + old.encode().replace(b".", rb"\.") + rb";",
        lambda m: m[1] + new.encode() + b";", project.read_bytes()))
    plist = root / PLIST
    # Keep recognized Xcode references and the original plist formatting.
    plist.write_bytes(re.sub(
        rb"(<key>CFBundle(?:ShortVersionString|Version)</key>\s*<string>)"
        + old.encode().replace(b".", rb"\.") + rb"(</string>)",
        lambda m: m[1] + new.encode() + m[2], plist.read_bytes()))
    strings = root / STRINGS
    data = strings.read_bytes()
    for prefix, suffix in (
        (rb'(CFBundleShortVersionString\s*=\s*")', rb'(";)'),
        (rb'(CFBundleGetInfoString\s*=\s*"get-printer-dpi version )', rb'(,)'),
    ):
        data = re.sub(prefix + old.encode().replace(b".", rb"\.") + suffix,
                      lambda m: m[1] + new.encode() + m[2], data)
    strings.write_bytes(data)
    assert read_version(root) == new
    return new


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("patch", "minor", "major"))
    args = parser.parse_args()
    try:
        print(bump(args.mode) if args.mode else read_version())
    except (ValueError, OSError, plistlib.InvalidFileException) as error:
        parser.exit(1, f"Version validation failed: {error}\n")
