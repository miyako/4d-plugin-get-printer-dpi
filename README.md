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
