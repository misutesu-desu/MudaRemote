"""Publish a verified manifest for the current GitHub stable release."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mudae_core.versioning import _align_manifest_to_ref, is_prerelease, release_identity_matches


def prepare_manifest(release, read_ref):
    tag = release["tag_name"]
    if release.get("draft") or release.get("prerelease") or is_prerelease(tag):
        raise ValueError("Expected a published stable release")
    manifest = json.loads(read_ref(tag, "version.json"))
    if not release_identity_matches(tag, manifest["version"]):
        raise ValueError("Stable tag and manifest version disagree")
    _align_manifest_to_ref(manifest, tag)
    for entry in manifest["source_files"]:
        if hashlib.sha256(read_ref(tag, entry["path"])).hexdigest() != entry["sha256"]:
            raise ValueError("Stable source checksum mismatch: " + entry["path"])
    assets = [asset for asset in release["assets"] if asset["name"] == "MudaRemote.exe"]
    if len(assets) != 1 or assets[0].get("digest") != "sha256:" + manifest["exe_sha256"]:
        raise ValueError("Stable executable checksum does not match GitHub's asset digest")
    return manifest


def main():
    release = json.loads(subprocess.check_output([
        "gh", "api", "repos/misutesu-desu/MudaRemote/releases/latest",
    ]))
    manifest = prepare_manifest(release, lambda tag, path: subprocess.check_output(["git", "show", tag + ":" + path]))
    output = Path("stable-manifest/version.json")
    output.parent.mkdir(exist_ok=True)
    output.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if "--publish" in sys.argv:
        subprocess.run(["gh", "release", "upload", release["tag_name"], str(output), "--clobber"], check=True)
    print("Verified stable update manifest for " + release["tag_name"])


if __name__ == "__main__":
    main()
