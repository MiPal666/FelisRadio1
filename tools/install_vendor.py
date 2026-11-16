#!/usr/bin/env python3
"""Install the prepared payload file by file inside RPM buildroot (no network)."""

from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile


def install(archive, destination):
    destination = Path(destination)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                raise ValueError("Unsafe vendor archive path")
            if item.is_dir():
                continue
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if str(path) == "bin/deno" else 0o644)


if __name__ == "__main__":
    install(*sys.argv[1:])
