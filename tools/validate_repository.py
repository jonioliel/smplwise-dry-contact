"""Validate the local structure and metadata needed for HACS publishing."""

import argparse
import json
import struct
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def validate(root: Path = ROOT, allow_unconfigured: bool = False) -> list[str]:
    problems = []
    components = [
        path
        for path in (root / "custom_components").iterdir()
        if path.is_dir() and not path.name.startswith("_")
    ]
    if len(components) != 1:
        return ["Exactly one custom component is required"]
    component = components[0]
    manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
    required = {
        "domain",
        "name",
        "version",
        "documentation",
        "issue_tracker",
        "codeowners",
    }
    if allow_unconfigured:
        required.remove("issue_tracker")
    for key in sorted(required - manifest.keys()):
        problems.append(f"manifest.json: missing {key}")
    if manifest.get("domain") != component.name:
        problems.append("The manifest domain must match the custom component directory")
    if not allow_unconfigured:
        if not manifest.get("codeowners"):
            problems.append(
                "Configure the GitHub maintainer with tools/configure_repository.py"
            )
        for key in ("documentation", "issue_tracker"):
            value = manifest.get(key, "")
            parsed = urlsplit(value)
            parts = parsed.path.strip("/").split("/")
            if parsed.netloc != "github.com" or len(parts) < 2 or "OWNER" in parts:
                problems.append(f"manifest.json: configure the real GitHub {key} URL")
    hacs = json.loads((root / "hacs.json").read_text(encoding="utf-8"))
    if hacs.get("name") != manifest.get("name"):
        problems.append("HACS and integration display names must match")
    if hacs.get("content_in_root") or hacs.get("zip_release"):
        problems.append("This repository uses custom_components/<domain> directly")
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        icon = component / "brand" / name
        if not icon.is_file():
            problems.append(f"Missing brand/{name}")
            continue
        raw = icon.read_bytes()
        if raw[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", raw[16:24]) != (
            size,
            size,
        ):
            problems.append(f"brand/{name} must be a {size}x{size} PNG")
    for relative in ("README.md", "LICENSE", "PUBLISHING.md", "hacs.json"):
        if not (root / relative).is_file():
            problems.append(f"Missing {relative}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-unconfigured", action="store_true")
    args = parser.parse_args()
    problems = validate(allow_unconfigured=args.allow_unconfigured)
    if problems:
        raise SystemExit("\n".join(problems))
    print(
        "Repository checks passed"
        + (" (GitHub owner not validated)" if args.allow_unconfigured else "")
    )


if __name__ == "__main__":
    main()
