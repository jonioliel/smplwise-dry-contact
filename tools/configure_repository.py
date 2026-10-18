"""Set the real GitHub owner/repository in HACS integration metadata."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components" / "ebyte_m31" / "manifest.json"


def configure(url: str, maintainer: str | None = None) -> None:
    parsed = urlsplit(url)
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.query
        or parsed.fragment
        or len(parts) != 2
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", parts[0])
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", parts[1])
    ):
        raise ValueError(
            "Use a repository URL such as https://github.com/OWNER/smplwise-dry-contact"
        )
    owner, repository = parts
    maintainer = (maintainer or owner).removeprefix("@")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", maintainer):
        raise ValueError("Maintainer must be a GitHub username")
    base = f"https://github.com/{owner}/{repository}"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["codeowners"] = [f"@{maintainer}"]
    manifest["documentation"] = base
    manifest["issue_tracker"] = f"{base}/issues"
    # Home Assistant expects a predictable manifest key order.
    order = [
        "domain",
        "name",
        "codeowners",
        "config_flow",
        "documentation",
        "integration_type",
        "iot_class",
        "issue_tracker",
        "requirements",
        "version",
    ]
    manifest = {key: manifest[key] for key in order if key in manifest}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = re.sub(
        r"<!-- repository-links:start -->.*?<!-- repository-links:end -->",
        "<!-- repository-links:start -->\n"
        f"[GitHub repository]({base}) · [Report an issue]({base}/issues)\n"
        "<!-- repository-links:end -->",
        text,
        flags=re.DOTALL,
    )
    readme.write_text(text, encoding="utf-8")
    print(f"Configured {owner}/{repository}; maintainer @{maintainer}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="https://github.com/OWNER/smplwise-dry-contact")
    parser.add_argument(
        "--maintainer",
        help="GitHub username, if the repository owner is an organization",
    )
    args = parser.parse_args()
    try:
        configure(args.url, args.maintainer)
    except ValueError as err:
        parser.error(str(err))


if __name__ == "__main__":
    main()
