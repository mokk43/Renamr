# Packaging Renamr as a macOS App

This guide covers building `Renamr.app` (and an optional `.dmg`) on macOS 15 (Sequoia) from the PySide6 source tree. PyInstaller is the recommended tool because it handles PySide6 Qt plugins on Apple Silicon better than `py2app`.

## 1. Install build tools

Run inside the project venv:

```bash
source ~/workspace/buildingai/bin/activate
pip install pyinstaller
# optional, for a nicer installer disk image:
brew install create-dmg
```

## 2. Build the `.app`

From the repo root:

```bash
pyinstaller \
  --name Renamr \
  --windowed \
  --noconfirm \
  --clean \
  --icon resources/Renamr.icns \
  --osx-bundle-identifier dev.renamr.app \
  --collect-submodules PySide6 \
  --collect-data ebooklib \
  txt_process/main.py
```

Key flags:
- `--windowed` — produces a `.app` bundle with no Terminal window.
- `--icon` — expects a `.icns` (convert from PNG with `iconutil` or `sips`).
- `--collect-submodules PySide6` — bundles Qt plugins (platforms, imageformats). Without this, startup fails with `could not find or load the Qt platform plugin cocoa`.
- `--collect-data ebooklib` — bundles ebooklib's template resources.
- `--osx-bundle-identifier` — required for proper Launch Services / notification integration.

Output: `dist/Renamr.app`. Test it:

```bash
open dist/Renamr.app
# or to see stdout/stderr:
./dist/Renamr.app/Contents/MacOS/Renamr
```

## 3. Reproducible builds via spec file

After the first run, commit the generated `Renamr.spec` and rebuild with:

```bash
pyinstaller --noconfirm --clean Renamr.spec
```

Add hidden imports to the spec when runtime errors expose missing modules. Common ones for this project:

```python
hiddenimports=[
    'keyring.backends.macOS',
    'lxml.etree',
    'lxml._elementpath',
]
```

## 4. Universal2 (Intel + Apple Silicon)

To produce a single binary for both architectures, use a universal2 Python (python.org installer) and pass:

```bash
pyinstaller --target-arch universal2 --noconfirm --clean Renamr.spec
```

Every wheel in the venv (PySide6, lxml, etc.) must also be universal2. Otherwise, build arch-specific bundles on each machine.

## 5. Codesign & notarize (required for distribution)

macOS 15 Sequoia tightened Gatekeeper. Unsigned apps shared with other users are blocked unless they're manually allowlisted via System Settings → Privacy & Security.

### With a Developer ID certificate

```bash
# 1. Sign (hardened runtime required for notarization)
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  --entitlements entitlements.plist \
  dist/Renamr.app

# 2. Zip for notarization
ditto -c -k --keepParent dist/Renamr.app Renamr.zip

# 3. Submit to Apple
xcrun notarytool submit Renamr.zip \
  --apple-id you@example.com \
  --team-id TEAMID \
  --password "$APP_SPECIFIC_PASSWORD" \
  --wait

# 4. Staple the ticket so it works offline
xcrun stapler staple dist/Renamr.app
```

Minimal `entitlements.plist` for a PyInstaller + PySide6 bundle:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
    <key>com.apple.security.cs.disable-library-validation</key><true/>
</dict>
</plist>
```

### Without a Developer account (personal / local use)

Ad-hoc sign the bundle and clear quarantine:

```bash
codesign --deep --force --sign - dist/Renamr.app
xattr -cr dist/Renamr.app
```

## 6. Package as a `.dmg`

```bash
create-dmg \
  --volname "Renamr" \
  --window-size 500 300 \
  --icon-size 100 \
  --icon "Renamr.app" 120 120 \
  --app-drop-link 380 120 \
  Renamr.dmg \
  dist/Renamr.app
```

## Common gotchas

- **`qt.qpa.plugin: Could not find the Qt platform plugin 'cocoa'`** — missing `--collect-submodules PySide6`.
- **App opens then instantly closes** — run the inner binary from Terminal (`./dist/Renamr.app/Contents/MacOS/Renamr`) to see the real traceback.
- **`lxml` ImportError at runtime** — add `lxml.etree` and `lxml._elementpath` to `hiddenimports`.
- **keyring cannot write to the login keychain** — add `keyring.backends.macOS` to `hiddenimports`; unsigned bundles access the keychain unreliably on Sequoia, so sign (ad-hoc is fine) before testing keyring.
- **`ebooklib` fails on some EPUBs** — missing `--collect-data ebooklib`.
- **First-run Gatekeeper block** — for personal builds, `xattr -cr dist/Renamr.app` strips the quarantine attribute; for anything shared, notarize instead.

## Quick recipes

Personal/local build (no distribution):

```bash
pyinstaller --noconfirm --clean Renamr.spec
codesign --deep --force --sign - dist/Renamr.app
open dist/Renamr.app
```

Distributable signed + notarized `.dmg`:

```bash
pyinstaller --noconfirm --clean Renamr.spec
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  --entitlements entitlements.plist dist/Renamr.app
ditto -c -k --keepParent dist/Renamr.app Renamr.zip
xcrun notarytool submit Renamr.zip --apple-id you@example.com \
  --team-id TEAMID --password "$APP_SPECIFIC_PASSWORD" --wait
xcrun stapler staple dist/Renamr.app
create-dmg --volname "Renamr" --app-drop-link 380 120 \
  Renamr.dmg dist/Renamr.app
```
