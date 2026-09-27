"""Compare an already assembled canonical Pages artifact with its public site."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[4]
MAIN_ROUTES = ("/", "/documentation", "/download", "/experiment-runner/")


def audit(pages: Path, base_url: str) -> dict:
    pages = pages.resolve(strict=True)
    files = sorted(path for path in pages.rglob("*") if path.is_file())
    if not files or not (pages / "app/index.html").is_file():
        raise ValueError("Assemble canonical Pages before running the public byte audit.")
    base_url = base_url.rstrip("/")

    def compare(path: Path) -> dict:
        route = "/" + path.relative_to(pages).as_posix()
        local = path.read_bytes()
        try:
            with urlopen(base_url + quote(route, safe="/"), timeout=20) as response:
                # A changed or invalid remote body cannot allocate without bound.
                public = response.read(len(local) + 1)
                return {"route": route, "status": response.status,
                        "bytes_identical": local == public,
                        "sha256": hashlib.sha256(local).hexdigest()}
        except Exception as error:
            return {"route": route, "bytes_identical": False, "error": str(error)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(compare, files))
    routes = []
    for route in MAIN_ROUTES:
        try:
            with urlopen(base_url + route, timeout=20) as response:
                routes.append({"route": route, "status": response.status})
        except Exception as error:
            routes.append({"route": route, "error": str(error)})
    passed = all(item["bytes_identical"] for item in results) and all(
        item.get("status") == 200 for item in routes
    )
    return {"passed": passed, "checked_files": len(results), "files": results, "routes": routes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, default=REPO_ROOT / "dist/pages")
    parser.add_argument("--url", default="https://ppskit.qzz.io")
    parser.add_argument("--report", type=Path,
                        default=REPO_ROOT / "artifacts/validation_runs/public-pages-byte-audit.json")
    args = parser.parse_args()
    result = audit(args.pages, args.url)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    failed = [item for item in result["files"] if not item["bytes_identical"]]
    print(json.dumps({"passed": result["passed"], "checked_files": result["checked_files"],
                      "failed_files": failed, "routes": result["routes"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
