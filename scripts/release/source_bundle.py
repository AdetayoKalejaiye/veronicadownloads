"""Collect unmodified LGPL library sources in memory, without private app files."""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import urllib.request
import zipfile

# Immutable upstream commits, verified against the named release tags. The two
# submodule snapshots are necessary to rebuild the bindings from source archives.
SOURCES = [
    ("netgen-6.2.2608", "NGSolve/netgen", "96e5682f6ea43ba77ba3bb2ae4bb4bd1791f506e", "v6.2.2608"),
    ("netgen-pybind11", "ngsolve/pybind11", "98e50b702d9ab784ec918399aaa20adcfd1af9a9", "Netgen external_dependencies/pybind11"),
    ("occt-7.8.1", "Open-Cascade-SAS/OCCT", "bd2a789f15235755ce4d1a3b07379a2e062fdc2e", "V7_8_1"),
    ("ocp-7.8.1.1", "CadQuery/OCP", "d3fe8a125c5911a5d1cecd17007218f390d6fbae", "7.8.1.1"),
    ("ocp-pywrap", "CadQuery/pywrap", "9c9ca5b8aa0d9a6687394897815a682b8c319fb0", "OCP pywrap submodule"),
    ("nlopt-2.11.0", "stevengj/nlopt", "88c424d4f458412787df96fcc95218acbca224fd", "v2.11.0"),
    ("nlopt-2.9.1", "stevengj/nlopt", "7b6d103c3de34efb767d5738abf97787386fcad5", "v2.9.1"),
    ("nlopt-python-2.11.0", "DanielBok/nlopt-python", "b4d2871ff46e31b18aa0d45ad861fdfcd43202c3", "2.11.0"),
    ("nlopt-python-2.9.1", "DanielBok/nlopt-python", "6c48ba164d72b503073b459c5805d8775ad7446d", "2.9.1"),
    ("casadi-3.8.2", "casadi/casadi", "a5852c23b2100296cee23b81227fcaa3bef43f04", "3.8.2"),
]


def build():
    archive = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for name, repo, commit, release in SOURCES:
            url = f"https://codeload.github.com/{repo}/tar.gz/{commit}"
            request = urllib.request.Request(url, headers={"User-Agent": "Veronica-source-release"})
            # Deliberately anonymous: no credential is ever sent to codeload.
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as source:
                members = source.getnames()
                if not members or not any("license" in path.lower() or "copying" in path.lower() for path in members):
                    raise RuntimeError(f"Source archive lacks its upstream license: {name}")
            filename = f"{name}.tar.gz"
            bundle.writestr(filename, data)
            manifest.append({"file": filename, "repository": repo, "commit": commit,
                             "release": release, "url": url, "bytes": len(data),
                             "sha256": hashlib.sha256(data).hexdigest()})
            print(f"Collected {name}: {len(data)} bytes", flush=True)
        bundle.writestr("SOURCES.json", json.dumps(manifest, indent=2) + "\n")
        bundle.writestr("README.txt", """Corresponding unmodified library sources for Veronica desktop 0.1.0.

The original upstream archives include their licenses, build systems and build
instructions. SOURCES.json records immutable commits, release tags and hashes.
Netgen's pybind11 snapshot belongs at external_dependencies/pybind11; OCP's
pywrap snapshot belongs at pywrap. These paths are submodules excluded from
GitHub's generated tar archives. Both NLopt versions are supplied because the
Intel Mac compatibility profile uses 2.9.1 and other platforms use 2.11.0.
Netgen and OCP each use OCCT 7.8.1. The OCP post1 wheel is a packaging revision
of the 7.8.1.1 binding. CasADi is supplied at its installed 3.8.2 release.

Runtime manifests and installed distribution metadata identify the libraries
actually installed for each platform. ENGINE-LIBRARIES.md in the app explains
replacement, relinking and debugging. The application uses dynamically loaded
libraries and does not prevent use/debugging of modified LGPL libraries.
No private Veronica source repository or research documents are in this bundle.
""")
    archive.seek(0)
    return archive


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()
    data = build()
    with open(args.output, "wb") as output:
        output.write(data.getbuffer())
