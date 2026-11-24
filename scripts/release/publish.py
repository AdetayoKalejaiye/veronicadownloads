"""Publish checked Veronica desktop installers as release assets of this public repository.

Started by a `repository_dispatch` (`publish-checked-desktop`) from the private build repository. The payload
carries, for each platform, two short-lived read-only download grants (about ten minutes): one for the installer
artifact and one for its metadata. No token for the private repository is ever sent here. Every grant is masked
before any work and the event file is deleted; all three packages are downloaded first, while the grants are
valid, then checked against their build receipts and uploaded.

Run by hand (`workflow_dispatch`), it only makes sure the release holds the library sources.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from source_bundle import build

REPO = os.environ.get("GITHUB_REPOSITORY", "AdetayoKalejaiye/veronicadownloads")
TAG = os.environ.get("RELEASE_TAG", "v0.1.0")
VERSION = TAG.lstrip("v").split("-")[0]
PLATFORMS = {"windows-x64": ".exe", "macos-arm64": ".zip", "macos-x64": ".zip"}
HOSTS = (".blob.core.windows.net", ".actions.githubusercontent.com")


def gh(*arguments, capture=False):
    result = subprocess.run(["gh", *arguments, "--repo", REPO], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(location: str, target: Path) -> None:
    url = urllib.parse.urlparse(location)
    if url.scheme != "https" or not (url.hostname or "").endswith(HOSTS):
        raise RuntimeError("Unrecognized read-only artifact host.")
    try:  # no GitHub token is sent to the artifact host
        with urllib.request.urlopen(location, timeout=300) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Artifact transfer expired or failed. Send a fresh grant.") from None


def upload(release_id: int, folder: Path, name: str, path: Path) -> str:
    """Attach a file once and check GitHub's own SHA256 of it; an existing asset must be identical."""
    digest, size = sha256(path), path.stat().st_size
    assets = json.loads(subprocess.check_output(["gh", "api", f"repos/{REPO}/releases/{release_id}/assets?per_page=100"], text=True))
    existing = next((a for a in assets if a["name"] == name), None)
    if existing is None:
        staged = folder / name
        if staged != path:
            shutil.copyfile(path, staged)
        gh("release", "upload", TAG, str(staged))
        assets = json.loads(subprocess.check_output(["gh", "api", f"repos/{REPO}/releases/{release_id}/assets?per_page=100"], text=True))
        existing = next(a for a in assets if a["name"] == name)
    remote = json.loads(subprocess.check_output(["gh", "api", f"repos/{REPO}/releases/assets/{existing['id']}"], text=True))
    if remote["size"] != size or remote.get("digest") not in (None, "sha256:" + digest):
        raise RuntimeError(f"The release's {name} differs from the checked file.")
    print(f"Verified {name}: {size} bytes; SHA256 {digest}", flush=True)
    return remote["browser_download_url"]


def member(package: zipfile.ZipFile, name: str) -> str:
    return next(n for n in package.namelist() if Path(n).name == name)


def _find():
    releases = json.loads(subprocess.check_output(["gh", "api", f"repos/{REPO}/releases?per_page=100"], text=True))
    return next((r for r in releases if r["tag_name"] == TAG), None)


def release() -> dict:
    found = _find()
    if found is None:
        gh("release", "create", TAG, "--draft", "--title", f"Veronica {VERSION}", "--notes-file",
           str(Path(__file__).with_name("release-notes.md")))
        for _ in range(30):  # a new draft takes a moment to show up in the list
            found = _find()
            if found:
                break
            time.sleep(2)
        else:
            raise RuntimeError("The new draft release didn't appear.")
    return found


def main():
    event_path = Path(os.environ["GITHUB_EVENT_PATH"])
    event = json.loads(event_path.read_text())
    dispatched = os.environ.get("GITHUB_EVENT_NAME") == "repository_dispatch"
    transfer = event.get("client_payload") if dispatched else None
    if dispatched:
        # The payload is never interpolated into shell or env blocks, printed, cached or uploaded.
        for entry in (transfer or {}).get("builds", {}).values():
            for key in ("url", "metadata_url"):
                if entry.get(key):
                    print("::add-mask::" + entry[key], flush=True)
        event_path.unlink()

    with tempfile.TemporaryDirectory(prefix="veronica-release-") as directory:
        folder = Path(directory)
        packages = {}
        if dispatched:
            if not transfer or transfer.get("schema") != 2 or len(transfer.get("commit", "")) != 40:
                raise RuntimeError("Invalid native transfer provenance.")
            if set(transfer["builds"]) != set(PLATFORMS):
                raise RuntimeError("A release needs all three checked platforms.")
            # Download everything first, while the grants are still valid.
            for platform, item in transfer["builds"].items():
                fetch(item["metadata_url"], folder / f"{platform}-metadata.zip")
                fetch(item["url"], folder / f"{platform}-package.zip")
                print(f"Downloaded {platform}", flush=True)
            for platform in PLATFORMS:
                with zipfile.ZipFile(folder / f"{platform}-metadata.zip") as small:
                    metadata = json.loads(small.read(member(small, f"{platform}.json")))
                if metadata["commit"] != transfer["commit"] or metadata["runtimeChecked"] is not True or metadata["platform"] != platform:
                    raise RuntimeError(f"{platform}: package provenance doesn't match the checked build.")
                packages[platform] = metadata

        current = release()
        if not any(a["name"] == "Veronica-library-sources.zip" for a in current["assets"]):
            sources = folder / "Veronica-library-sources.zip"
            sources.write_bytes(build().getbuffer())
            upload(current["id"], folder, sources.name, sources)
        if not dispatched:
            return

        # An earlier run attached one shared relocation script; each platform's differs, so each is its own asset.
        if any(a["name"] == "native-library-relocation.py" for a in current["assets"]):
            gh("release", "delete-asset", TAG, "native-library-relocation.py", "--yes")

        downloads = {"schema": 1, "version": VERSION, "tag": TAG, "sourceCommit": transfer["commit"], "builds": {}}
        for platform, suffix in PLATFORMS.items():
            metadata = packages[platform]
            installer = next((a for a in metadata["artifacts"] if a["file"].endswith(suffix)), None)
            if installer is None:
                raise RuntimeError(f"{platform}: no {suffix} installer in the checked build.")
            with zipfile.ZipFile(folder / f"{platform}-package.zip") as package:
                manifest = json.loads(package.read(member(package, "runtime-manifest.json")))
                check = json.loads(package.read(member(package, "runtime-check.json")))
                linkage = package.read(member(package, "native-link-check.json"))
                relocation = package.read(member(package, "native-library-relocation.py"))
                if manifest["commit"] != transfer["commit"] or manifest["dependencies"].get("netgen-mesher") != "6.2.2608" or "gmsh" in manifest["dependencies"]:
                    raise RuntimeError(f"{platform}: unexpected native runtime library provenance.")
                if not all(check.get(name) is True for name in ("cad", "contact", "structural", "constraints")):
                    raise RuntimeError(f"{platform}: packaged engineering smoke checks failed.")
                link_check = json.loads(linkage)
                if platform.startswith("macos") and (link_check.get("check") != "dylib_and_rpath_locations" or link_check.get("externalNativeLinks") != []):
                    raise RuntimeError(f"{platform}: Mac library-location audit did not pass.")
                binary = folder / f"Veronica-{platform}{suffix}"
                with package.open(member(package, installer["file"])) as source, binary.open("wb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            (folder / f"{platform}-package.zip").unlink()
            if binary.stat().st_size != installer["bytes"] or sha256(binary) != installer["sha256"]:
                raise RuntimeError(f"{platform}: installer differs from its build receipt.")
            for name, data in ((f"{platform}-linkage.json", linkage), (f"{platform}-native-library-relocation.py", relocation),
                               (f"{platform}-runtime.json", json.dumps(manifest, indent=2).encode())):
                (folder / name).write_bytes(data)
                upload(current["id"], folder, name, folder / name)
            url = upload(current["id"], folder, binary.name, binary)
            binary.unlink()
            downloads["builds"][platform] = {"status": "available", "version": VERSION, "url": url,
                                             "bytes": installer["bytes"], "sha256": installer["sha256"], "runtimeChecked": True,
                                             "redistributionCleared": True, "signing": metadata["signing"],
                                             "sourceCommit": transfer["commit"]}
        (folder / "downloads.json").write_text(json.dumps(downloads, indent=2) + "\n")
        upload(current["id"], folder, "downloads.json", folder / "downloads.json")
        gh("release", "edit", TAG, "--draft=false", "--latest")
        print(json.dumps(downloads, indent=2))
        print("Published the checked desktop installers and their library sources.")


if __name__ == "__main__":
    main()
