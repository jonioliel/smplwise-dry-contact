"""Create a dependency-free manual-install ZIP."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    component = ROOT / "custom_components" / "ebyte_m31"
    manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
    target = ROOT / "dist" / f"smplwise-dry-contact-{manifest['version']}.zip"
    target.parent.mkdir(exist_ok=True)
    files = sorted(
        path
        for path in component.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in [
            *files,
            ROOT / "README.md",
            ROOT / "LICENSE",
            ROOT / "PUBLISHING.md",
        ]:
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(target)
    source = ROOT / "dist" / "smplwise-dry-contact-source.zip"
    source_files = []
    for folder in ("custom_components", "tools", "tests", ".github"):
        source_files.extend(
            path
            for path in (ROOT / folder).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    source_files.extend(
        ROOT / name
        for name in (
            "README.md",
            "PUBLISHING.md",
            "LICENSE",
            "hacs.json",
            "requirements-dev.txt",
            "pyproject.toml",
            ".gitignore",
            ".gitattributes",
        )
    )
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        for path in sorted(source_files):
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(source)


if __name__ == "__main__":
    main()
