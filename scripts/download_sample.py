"""Explicit, size-limited download of the CC BY 3.0 Sintel trailer; never runs on startup."""

import hashlib
import tempfile
import urllib.request
from pathlib import Path

URL = "https://media.w3.org/2010/05/sintel/trailer.mp4"
SHA256 = "b670602fa00934ca27c4351bb0efe7ea7a07fae57284e44226025eeed7c51254"
target = Path(__file__).resolve().parents[1] / "projects/demo/media/sintel-trailer.mp4"
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists():
    if hashlib.sha256(target.read_bytes()).hexdigest() != SHA256:
        raise SystemExit("Existing file differs from the sample; move it aside before downloading.")
    print(f"Sample already verified: {target}")
else:
    temporary = None
    try:
        with urllib.request.urlopen(URL, timeout=30) as response:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                temporary = Path(output.name)
                digest = hashlib.sha256()
                total = 0
                while chunk := response.read(128 * 1024):
                    total += len(chunk)
                    if total > 15_000_000:
                        raise ValueError("Sample exceeds download size limit")
                    output.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != SHA256:
                raise ValueError("Sample checksum changed; review its source before accepting it")
        temporary.replace(target)
        print(f"Downloaded {total:,} bytes: {target}")
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
print("Sintel © Blender Foundation · https://www.sintel.org · CC BY 3.0")
print("Open Media in the control UI, stop the show, scan, then add the sample or Play now.")
