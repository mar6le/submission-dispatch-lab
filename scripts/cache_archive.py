"""Transfer a Docker archive using byte-identical layers from a pinned base image."""
import argparse
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive_members(raw):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        return {
            member.name: (member.offset_data, member.size)
            for member in archive
            if member.isfile() and member.name.startswith("blobs/sha256/") and member.size > 100_000
        }


def pack(base, image, output):
    base_members = archive_members(base)
    references = []
    edits = io.BytesIO()
    cursor = 0
    for name, (offset, size) in sorted(archive_members(image).items(), key=lambda row: row[1][0]):
        if name not in base_members:
            continue
        other, count = base_members[name]
        content = image[offset:offset + size]
        if count != size or content != base[other:other + count]:
            continue
        edits.write(image[cursor:offset])
        references.append([name, offset, size, digest(content)])
        cursor = offset + size
    edits.write(image[cursor:])
    (output / "archive-map.json").write_text(json.dumps({
        "tar_sha256": digest(image),
        "references": references,
    }, indent=2) + "\n")
    (output / "remainder.gz").write_bytes(gzip.compress(edits.getvalue(), compresslevel=1, mtime=0))


def unpack(base, bundle, output):
    plan = json.loads((bundle / "archive-map.json").read_text())
    members = archive_members(base)
    remainder = io.BytesIO(gzip.decompress((bundle / "remainder.gz").read_bytes()))
    checksum = hashlib.sha256()
    cursor = 0
    with output.open("wb") as result:
        def put(chunk):
            result.write(chunk)
            checksum.update(chunk)
        for name, offset, size, expected in plan["references"]:
            start, length = members[name]
            layer = base[start:start + length]
            if length != size or digest(layer) != expected:
                raise SystemExit(f"Base layer does not match: {name}")
            gap = remainder.read(offset - cursor)
            if len(gap) != offset - cursor:
                raise SystemExit("Incomplete transfer")
            put(gap)
            put(layer)
            cursor = offset + size
        put(remainder.read())
    if checksum.hexdigest() != plan["tar_sha256"]:
        raise SystemExit("Restored tar does not match CI")
    print("Verified archive tar SHA-256", checksum.hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["pack", "unpack"])
    parser.add_argument("base", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    base = args.base.read_bytes()
    if args.mode == "pack":
        pack(base, args.source.read_bytes(), args.destination)
    else:
        unpack(base, args.source, args.destination)


if __name__ == "__main__":
    main()
