#!/usr/bin/env python
"""Zip a staged PPS offline lab package with stable relative paths."""

from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path


def _filesystem_path(path: Path) -> Path:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return Path(resolved)
    if resolved.startswith("\\\\"):
        return Path(f"\\\\?\\UNC\\{resolved[2:]}")
    return Path(f"\\\\?\\{resolved}")


def create_zip(source_dir: Path, output: Path) -> Path:
    source_dir = source_dir.resolve()
    output = output.resolve()
    if not source_dir.is_dir():
        raise NotADirectoryError(source_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    filesystem_source = _filesystem_path(source_dir)
    files = sorted(path for path in filesystem_source.rglob("*") if path.is_file())
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in files:
            archive.write(path, path.relative_to(filesystem_source).as_posix())
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = create_zip(args.source_dir, args.output)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

