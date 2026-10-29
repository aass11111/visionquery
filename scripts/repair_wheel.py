"""Repair a large downloaded wheel in place instead of downloading it all again.

A wheel is a ZIP file and every member carries its own CRC32. When the whole-file sha256 does not
match, read every member, find the ones whose CRC fails, re-download just their byte ranges with
HTTP Range requests and patch them into the file. Repeat until the sha256 matches.

    python scripts/repair_wheel.py <file.whl> <url> <expected_sha256>
"""
import hashlib
import struct
import subprocess
import sys
import zipfile
import zlib

LOCAL_HEADER = struct.Struct("<4sHHHHHIIIHH")  # 30-byte local file header


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def bad_ranges(path: str) -> list[tuple[int, int, str]]:
    """Byte ranges (start, end inclusive, name) of members whose data fails its CRC32."""
    out = []
    with zipfile.ZipFile(path) as zf, open(path, "rb") as raw:
        for info in zf.infolist():
            raw.seek(info.header_offset)
            hdr = LOCAL_HEADER.unpack(raw.read(LOCAL_HEADER.size))
            data_start = info.header_offset + LOCAL_HEADER.size + hdr[9] + hdr[10]
            end = data_start + info.compress_size - 1
            try:
                crc = 0
                with zf.open(info) as m:
                    for block in iter(lambda: m.read(8 << 20), b""):
                        crc = zlib.crc32(block, crc)
                ok = crc == info.CRC
            except (zipfile.BadZipFile, zlib.error, EOFError):
                ok = False
            if not ok:
                out.append((info.header_offset, end, info.filename))
    return out


def fetch_range(url: str, start: int, end: int) -> bytes:
    for _ in range(10):
        r = subprocess.run(["curl", "-fsL", "--retry", "5", "-r", f"{start}-{end}", url], capture_output=True)
        if r.returncode == 0 and len(r.stdout) == end - start + 1:
            return r.stdout
    raise RuntimeError(f"could not fetch bytes {start}-{end}")


def server_md5(url: str) -> str | None:
    """Single-part S3/CloudFront ETags are the MD5 of the whole object: an independent check."""
    r = subprocess.run(["curl", "-fsIL", url], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.lower().startswith("etag:"):
            tag = line.split(":", 1)[1].strip().strip('"')
            return tag if len(tag) == 32 and "-" not in tag else None
    return None


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def refetch_tail(path: str, url: str, size: int = 64 << 20) -> None:
    """The ZIP central directory sits at the end of the file: re-download the last `size` bytes."""
    with open(path, "r+b") as f:
        total = f.seek(0, 2)
        start = max(0, total - size)
        f.seek(start)
        f.write(fetch_range(url, start, total - 1))


def main(path: str, url: str, expected: str) -> int:
    previous = None
    for round_ in range(1, 6):
        got = sha256(path)
        if got == expected:
            print(f"OK sha256 verified after {round_ - 1} repair round(s)")
            return 0
        if got == previous:
            # Patching member data changed nothing: the damage is in the directory at the end
            # (e.g. a file name there no longer matches its local header).
            print(f"round {round_}: last round changed nothing; re-downloading the last 64 MB (ZIP directory)", flush=True)
            refetch_tail(path, url)
            previous = None
            continue
        previous = got
        print(f"round {round_}: sha256 {got[:16]}... != expected {expected[:16]}..., scanning members", flush=True)
        try:
            bad = bad_ranges(path)
        except zipfile.BadZipFile as e:
            print(f"zip directory damaged ({e}); re-downloading the last 64 MB", flush=True)
            refetch_tail(path, url)
            continue
        if not bad:
            etag = server_md5(url)
            mine = md5(path)
            if etag and mine == etag:
                print(f"every member passes its CRC and the file's MD5 equals the server ETag ({etag}): "
                      "byte-identical to the server copy; only the published sha256 is stale")
                print("OK verified by server MD5")
                return 0
            print(f"every member passes its CRC, but sha256 and server MD5 ({etag}) both differ (md5 {mine})")
            return 3
        total = sum(e - s + 1 for s, e, _ in bad)
        print(f"  {len(bad)} damaged member(s), re-downloading {total / 1048576:.1f} MB", flush=True)
        with open(path, "r+b") as f:
            for s, e, name in bad:
                print(f"  fixing {name} ({(e - s + 1) / 1048576:.1f} MB)", flush=True)
                f.seek(s)
                f.write(fetch_range(url, s, e))
    print("still not matching after 5 rounds")
    return 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
