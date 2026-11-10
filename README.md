# 4d-plugin-get-printer-dpi

Ask a printer which resolutions it supports, and which one it uses by default. On macOS the plugin reads the printer's PPD through `NSPrinter`; on Windows it asks the print spooler (`DeviceCapabilities`, `GetDeviceCaps`). Results come back as `Real` values in dots per inch, either as two parallel `Real` arrays (horizontal and vertical) or as two `Real` variables. Pass `""` as the printer name to query the default printer.

| Command | Returns | Purpose |
|---|---|---|
| [PRINTER DPI LIST](#printer-dpi-list) | two `Real` arrays (by reference) | Every resolution the printer supports |
| [GET PRINTER DPI](#get-printer-dpi) | two `Real` variables (by reference) | The printer's default resolution |

**Platforms:** macOS 11.5 or later (universal: Apple silicon and Intel), Windows 64-bit.

Releases: <https://github.com/miyako/4d-plugin-get-printer-dpi/releases>

### Release maintenance

Run **Bump version** on the desired branch with `patch`, `minor`, or `major`.
It validates and commits coordinated source metadata, then pushes only that
branch without force or implicit tags. It creates no tag, release, or build.
Run **Build** separately on the updated branch (no inputs beyond the branch
selector). Every checkout uses the selected immutable commit, not a moving
branch or an existing tag. Any branch may be selected.

The source Xcode `MARKETING_VERSION` is authoritative. All three configurations'
`MARKETING_VERSION` and `CURRENT_PROJECT_VERSION`, source `Info.plist`, and
`English.lproj/InfoPlist.strings` must agree on strict `X.Y.Z`; recognized plist
references `$(MARKETING_VERSION)` and `$(CURRENT_PROJECT_VERSION)` are preserved.
The localized source strings were normalized from `1.0` to the existing `1.0.0`
without a version increment. Localization revision/schema counters, the
manifest command IDs, and tracked prebuilt bundle metadata are independent
and are not bumped.

Build retains the universal macOS 11.5 build, prebuilt-library and bundle
verification, Developer ID signing, ZIP/DMG notarization, and DMG stapling.
Windows binaries and other committed bundle resources ship as-is; this workflow
does not build Windows. Publication is serialized repository-wide across
branches. It rejects existing remote tags and same-tag releases, including
drafts, using authenticated, schema-checked paginated listing. API or network
errors fail closed. These checks run before building and again immediately
before publication, after all required gates succeed.

Only then does Build push a new nonforced `vX.Y.Z` tag at the exact selected
commit, verify its remote target, create a new public non-prerelease via REST
(without generated notes), and upload the original ZIP and DMG without
overwriting assets. It never updates or deletes an existing release.
If tag creation, release creation, or upload fails, the workflow fails and
retains partial state: inspect the run diagnostics, remote tag target, releases
(including drafts), and uploaded assets before manually deciding how to recover.
There is no automatic rollback, destructive cleanup, or publication retry;
do not rerun blindly, as existing publication state is intentionally rejected.

Local lifecycle checks (no native build, signing, or publication):
`python3 -m unittest discover -s .github/tests -v` and `actionlint`.

### Native ownership maintenance

Run `python3 tests/native/run.py --baseline` on macOS with Apple clang and
Python 3.12 or later. This direct, unsigned compile does not invoke either
project build or any release workflow. It compiles the actual entry point,
all 16 first-party wrapper implementations, and the complete unchanged bundled
`4DPluginAPI.c`. Synthetic engine callbacks track string allocations, handles,
and picture reference counts. Compile-time substitutions replace `NSPrinter`
and `NSPrintInfo` before the actual exported dispatcher runs: no real printers,
jobs, defaults, settings, print operations, or dialogs are accessed.

The same final harness is compiled against an immutable `git archive` of
`af4003cef5a196253de556327e90324da196a685`. Four named baseline cases fail:
`path-owners` detects the path's double disposal and leaked initial/output
owners; `temporary-owner` detects the retained `setBytes` temporary;
`copy-byte-units` reports an ASan heap-buffer-overflow in `createCopy`;
`command-empty-owners` detects overwritten initial picture owners. The fixed
sources pass all seven cases with both allocated-empty and null-empty strings.
The other cases exercise array replacement/shrink/clear, independent transfers,
borrowed copies, synchronous argument cleanup, owning returns and handoffs,
raw command-failure sentinels, and both actual exported command selectors.
Fixtures assert exact ASCII, BMP, supplementary, and empty text, conversion
byte counts versus UTF-16 code units, terminators, and balanced explicit
owners under ASan/UBSan. LeakSanitizer is unavailable on macOS; explicit
accounting covers the modeled native owners, not arbitrary framework leaks.

**Inventory and reachability (baseline above):**

| Tracked native surface | Ownership classification / reachability |
|---|---|
| `4DPlugin.cpp`, `4DPlugin.h`, `4D Plugin_Prefix.pch` | SDK `FourDPackex` calls `PluginMain`, then `CommandDispatcher`: selector 1 calls `PRINTER_DPI_LIST`, selector 2 calls `GET_PRINTER_DPI`. Text inputs are copied by `C_TEXT`; outputs are real arrays/scalars. No first-party JSON/object/collection or method callback consumer exists. |
| `C_TEXT.cpp/.h`, `ARRAY_TEXT.cpp/.h`, `C_TYPES.h` in `4D Plugin API/Classes` | Scalar content setters, independent C++ copies of borrowed inputs, fresh per-element text allocations transferred to arrays. Text-array wrapper is compiled but not used by either DPI command. |
| `C_PICTURE.cpp/.h` | Compiled dormant helper: path string now has one argument-variable owner; retained output releases its argument owner; `setBytes` releases its temporary after retain; shallow-setter input slots start Undefined; format conversion bytes are divided by `sizeof(PA_Unichar)`. Borrowed picture inputs still detach before cleanup; owning picture returns remain caller-owned. Output-only picture slots still initialize an empty picture for command replacement. |
| `C_POINTER.cpp/.h` | Compiled dormant pointer/variable metadata bridge; ownership of `PA_GetPointerValue` metadata is deferred rather than clearing or relabeling ambiguous references. |
| `C_BLOB.cpp/.h` | Compiled dormant byte/handle copies and handoffs; no string descriptors or command callbacks. Unrelated byte-stream algorithms and allocation-error redesign are outside this string audit. |
| `C_INTEGER`, `C_LONGINT`, `C_REAL`, `C_DATE`, `C_TIME` (`.cpp/.h` each) | Value-only wrappers; `C_REAL` is used by scalar DPI output. No string ownership or callbacks. |
| `ARRAY_BOOLEAN`, `ARRAY_INTEGER`, `ARRAY_LONGINT`, `ARRAY_REAL`, `ARRAY_DATE`, `ARRAY_TIME` (`.cpp/.h` each) | Value-only array wrappers; `ARRAY_REAL` is used by list output. No text-element owners; SDK handle-allocation failure behavior is not certified. |
| `4DPluginAPI.c/.h/.def`, `EntryPoints.h`, `Flags.h`, `PrivateTypes.h`, `PublicTypes.h` | Bundled SDK engine boundary, layout, platform types, and export declarations; preserved, not production fix targets. Windows exports `FourDPackex`; macOS gives that entry default visibility. |
| `get-printer-dpi.vcxproj`, `.vcxproj.filters`, `get-printer-dpi.xcodeproj/project.pbxproj` and tracked workspace/scheme metadata | Both source lists compile the SDK, dispatcher, and all 16 wrappers, with shared header includes. Dormant helpers cannot be excluded from this audit by the manifest alone. Preserved; no project build executed. |
| Source `manifest.json` and bundled `Contents/Resources/manifest.json` | Identical two-command declarations: `PRINTER DPI LIST(&T;&Y;&Y;&T)` and `GET PRINTER DPI(&T;&8;&8;&T)`. No text-array command. Bundled binaries/resources/database files were preserved and not executed. |

**SDK provenance and contracts:** the baseline SDK implementation's Git blob
is `478081f0238f6bc5393222f574bc2656f010b67b`, carried through relocation
commit `02f5efc6db83a02853fc2088f42ccbb43bbe8f5e` from repository first commit
`07ccc2020d3bb826a0f76ca2d8f1ae8b4849025a` at
`printer-dpi/4D Plugin API/4DPluginAPI.c` (not its separate `v11` copy).
There is no verified upstream
release pin; the `.c` v14 / `.h` v13 comments are not upstream identity.
This blob differs from the Poppler skill's reference implementation.
Canonical guidance read for this audit: `miyako/skills`,
`4d-skills/skills/4dplugin/SKILL.md` at `e6b492f`.

The actual bundled `PA_SetStringInArray` accepts only Unicode arrays with a
non-null data handle, `0 <= index <= fNbElements`, and a non-null descriptor
pointer. Accepted assignment disposes the old element and shallow-transfers
the new descriptor; rejection retains caller ownership. `PA_GetStringInArray`
is borrowed. `PA_SetStringVariable` and `PA_SetPictureVariable` shallow-assign
without clearing old owners; `PA_GetPictureVariable` remains variable-owned.
`PA_ReturnString`/`PA_SetUnistring` use the engine content setter, not descriptor
transfer. Picture duplicate with `retainOnly=1` retains. The SDK documents
charset conversion's result as a byte size; the synthetic conversion reports
payload bytes, without writing over the caller's preinitialized terminator.
Command handle failure returns a raw
kind-0 sentinel even though the kind normalizer calls it a string; method
handle failure returns Undefined. The sentinel must not be cleaned as an
owned string.

**Deferred boundaries:** pointer metadata, SDK-only application-path outputs,
and `PA_GetPictureData` metadata string ownership need real host evidence.
`PA_ResizeArray` can update the logical count after a failed handle resize;
ordinary array tests do not certify resize-OOM safety. Failed initial
array/string creation also needs a verified host failure representation,
caller-parameter preservation, and an explicit error channel. The existing
dispatcher silently catches exceptions and no established native error
notification channel exists; this patch does not invent a success-shaped
fallback or claim those paths fixed. The tests do not inject those unsupported
creation/resize failures. No SDK internals, project/manifest metadata, bundled
binaries, or manual release workflows are changed. This evidence is an Apple
silicon macOS synthetic-host regression, not a real 4D host, Windows, Intel
runtime, or exact Poppler crash reproduction.

![image](https://cloud.githubusercontent.com/assets/1725068/13600847/01ea0f78-e56f-11e5-8169-4279708ee76d.png)

---

## Requirements & platform notes

- **Failure is silent.** Neither command raises a 4D error or sets `OK`. A printer that reports nothing gives you empty arrays or `0`.
- **An unknown name is not an error, it is the default printer.** On both platforms, if the name you pass does not match an installed printer (including `""`), the command queries the system default printer instead. You cannot tell from the result which printer answered.
- **Printer names** are the names the operating system shows: the printer name in macOS System Settings > Printers & Scanners (e.g. `"EPSON EW-056A Series"`), or the printer name in the Windows Printers list.
- **macOS reads the PPD, not the driver.** The values are whatever the printer's PPD file declares. Printers set up as driverless (AirPrint/IPP Everywhere) may declare no `Resolution` option at all, so [PRINTER DPI LIST](#printer-dpi-list) returns empty arrays for them while [GET PRINTER DPI](#get-printer-dpi) still returns the default (seen on an HP OfficeJet Pro 9010 on macOS 26). The `NSPrinter` PPD methods used here have been deprecated by Apple since macOS 10.9; they still work on macOS 26.
- **The two platforms measure different things for the default resolution.** macOS returns the PPD's `DefaultResolution`; Windows returns the resolution of the printer's current default settings (`LOGPIXELSX`/`LOGPIXELSY`). They usually agree but are not guaranteed to.

---

## PRINTER DPI LIST

### Syntax

```
PRINTER DPI LIST ( printerName ; dpiX ; dpiY {; portName} )
```

| Parameter | Type | Description |
|---|---|---|
| `printerName` | Text | Printer name. `""` or an unknown name = default printer |
| `dpiX` | Real array | Receives the horizontal resolution of each supported setting |
| `dpiY` | Real array | Receives the vertical resolution of each supported setting |
| `portName` | Text | **Windows only**, optional. Port passed to `DeviceCapabilities`; `"LPT1"` when omitted or `""`. **Ignored on macOS** |
| Result | | None. The results are written into `dpiX` and `dpiY` |

### Description

[PRINTER DPI LIST](#printer-dpi-list) fills `dpiX` and `dpiY` with one element per supported resolution. Element `n` of `dpiX` and element `n` of `dpiY` belong together (e.g. `600` and `600` for 600x600 dpi). Both arrays are resized by the command; element `0` is not used. If nothing is found, both arrays are empty.

**On macOS**, the command looks up the printer with `NSPrinter`, reads the list of `Resolution` options from its PPD, and parses the display text of each option, which has the form `<x>x<y>dpi` (e.g. `720x720dpi`). An option whose text does not contain an `x` (e.g. a PPD that writes `600dpi`) is skipped, so a printer that declares its resolutions only in that short form gives empty arrays.

**On Windows**, the command calls `DeviceCapabilities` with `DC_ENUMRESOLUTIONS` for the printer and port. If that reports no resolutions, it retries with the default printer (same port). The pairs come back in the order the driver lists them.

### Example

```4d
ARRAY REAL($dpiX;0)
ARRAY REAL($dpiY;0)

PRINTER DPI LIST("";$dpiX;$dpiY)  // default printer

C_LONGINT($i)
C_TEXT($list)
For ($i;1;Size of array($dpiX))
	$list:=$list+String($dpiX{$i})+" x "+String($dpiY{$i})+" dpi"+Char(Carriage return)
End for
ALERT($list)
```

Query a named printer, and pick the highest supported horizontal resolution:

```4d
ARRAY REAL($dpiX;0)
ARRAY REAL($dpiY;0)

PRINTER DPI LIST("EPSON EW-056A Series";$dpiX;$dpiY)

C_REAL($best)
C_LONGINT($i)
For ($i;1;Size of array($dpiX))
	If ($dpiX{$i}>$best)
		$best:=$dpiX{$i}
	End if
End for
```

---

## GET PRINTER DPI

### Syntax

```
GET PRINTER DPI ( printerName ; dpiX ; dpiY )
```

| Parameter | Type | Description |
|---|---|---|
| `printerName` | Text | Printer name. `""` or an unknown name = default printer |
| `dpiX` | Real | Receives the default horizontal resolution |
| `dpiY` | Real | Receives the default vertical resolution |
| (4th parameter) | Text | Declared by the plugin but **ignored on both platforms**. Omit it |
| Result | | None. The results are written into `dpiX` and `dpiY` |

### Description

[GET PRINTER DPI](#get-printer-dpi) returns the resolution the printer uses by default.

**On macOS**, the value is the PPD's `DefaultResolution`, parsed the same way as in [PRINTER DPI LIST](#printer-dpi-list): `600x600dpi` gives `600` and `600`. If the PPD has no `DefaultResolution`, or writes it without an `x` (e.g. `600dpi`), both values are `0`.

**On Windows**, the command opens a device context for the printer (`CreateDC` with `"WINSPOOL"`) and reads `LOGPIXELSX` and `LOGPIXELSY`. If the printer cannot be opened, it uses the default printer. If that fails too, both values are `0`.

### Example

```4d
C_REAL($dpiX;$dpiY)

GET PRINTER DPI("";$dpiX;$dpiY)  // default printer

If ($dpiX=0)
	ALERT("The printer did not report a default resolution.")
Else
	ALERT(String($dpiX)+" x "+String($dpiY)+" dpi")
End if
```

---

## Error handling & troubleshooting

- **Wrong printer answered.** A misspelled or unavailable printer name silently falls back to the default printer on both platforms. Check the name against the system's printer list before relying on the result.
- **Empty arrays on macOS.** The printer's PPD declares no `Resolution` option (common for driverless AirPrint/IPP printers), or its options are not written as `<x>x<y>dpi`. [GET PRINTER DPI](#get-printer-dpi) may still return a value.
- **`0` from [GET PRINTER DPI](#get-printer-dpi).** On macOS the PPD has no `DefaultResolution` in `<x>x<y>dpi` form; on Windows neither the named nor the default printer could be opened.
- **Empty arrays on Windows.** Neither the named printer nor the default printer reported resolutions for the given port. Try passing the printer's actual port as `portName`.
- **No 4D error, no `OK`.** Test the results (array size, `0`) instead of `OK` or an error handler.

---

## Quick reference

```4d
ARRAY REAL($dpiX;0)
ARRAY REAL($dpiY;0)
PRINTER DPI LIST("";$dpiX;$dpiY)                     // all resolutions, default printer
PRINTER DPI LIST("My Printer";$dpiX;$dpiY;"USB001")  // Windows: explicit port

C_REAL($x;$y)
GET PRINTER DPI("";$x;$y)                            // default resolution, default printer
```
