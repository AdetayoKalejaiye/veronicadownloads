# Veronica downloads

Desktop installers for [Veronica](https://getveronica.me). Get the latest from **[Releases](https://github.com/AdetayoKalejaiye/veronicadownloads/releases/latest)**:

- **Windows (64-bit):** `Veronica-windows-x64.exe`
- **Mac, Apple silicon:** `Veronica-macos-arm64.zip`
- **Mac, Intel:** `Veronica-macos-x64.zip`

Not sure which Mac you have? Open the Apple menu and choose **About This Mac**. "Chip: Apple M…" means Apple silicon; "Processor: Intel" means Intel.

The builds aren't signed by a paid certificate yet. On Windows, click **More info → Run anyway**. On a Mac, if it won't open, go to **System Settings → Privacy & Security** and click **Open Anyway**.

This repository holds only the release workflow and the installers. Each release also carries `downloads.json` (sizes and SHA-256 of every installer) and `Veronica-library-sources.zip`, the unmodified sources of the open-source libraries the app ships.

## How a release is made

The private build repository builds and checks each installer on Windows and macOS, then sends this repository a `publish-checked-desktop` dispatch with short-lived, read-only download links for those builds. `scripts/release/publish.py` downloads them, checks each installer's size and SHA-256 against its build receipt and its packaged runtime checks, uploads them to the release and publishes it.
