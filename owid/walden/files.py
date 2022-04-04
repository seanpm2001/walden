#
#  files.py
#
#  Helpers for downloading and dealing with files.
#

import tempfile
import hashlib
import json

import math
from os import path, walk
from shutil import move  # noqa; re-exported for convenience
from typing import Iterator, Optional, Tuple, IO
from rich.progress import track

import requests

from .ui import log


def _stream_to_file(
    r: requests.Response,
    file: IO[bytes],
    chunk_size: int = 2**14,
    progress_bar_min_bytes: int = 2**30,
) -> str:
    """Stream the response to the file, returning the checksum.
    :param progress_bar_min_bytes: Minimum number of bytes to display a progress bar for. Default is 1GB
    """
    # check header to get content length, in bytes
    total_length = int(r.headers.get("content-length", 0))

    md5 = hashlib.md5()

    streamer = r.iter_content(chunk_size=chunk_size)

    if total_length > progress_bar_min_bytes:
        streamer = track(  # type: ignore
            streamer,
            description="Downloading",
            total=math.ceil(total_length / chunk_size),
        )

    for chunk in streamer:  # 16k
        file.write(chunk)
        md5.update(chunk)

    return md5.hexdigest()


def download(
    url: str, filename: str, expected_md5: Optional[str] = None, quiet: bool = False
) -> None:
    "Download the file at the URL to the given local filename."
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as temp, requests.get(
        url, stream=True
    ) as r:
        r.raise_for_status()

        md5 = _stream_to_file(r, temp)

        if expected_md5 and md5 != expected_md5:
            raise ChecksumDoesNotMatch(f"for file downloaded from {url}")
        move(temp.name, filename)
    if not quiet:
        log("DOWNLOADED", f"{url} -> {filename}")


def checksum(local_path: str) -> str:
    md5 = hashlib.md5()
    chunk_size = 2**20  # 1MB
    with open(local_path, "rb") as f:
        chunk = f.read(chunk_size)
        while chunk:
            md5.update(chunk)
            chunk = f.read(chunk_size)

    return md5.hexdigest()


def iter_docs(folder) -> Iterator[Tuple[str, dict]]:
    "Iterate over the JSON documents in the catalog."
    for filename in sorted(iter_json(folder)):
        try:
            with open(filename) as istream:
                yield filename, json.load(istream)

        except json.decoder.JSONDecodeError:
            raise RecordWithInvalidJSON(filename)


def iter_json(base_dir: str) -> Iterator[str]:
    for dirname, _, filenames in walk(base_dir):
        for filename in filenames:
            if filename.endswith(".json"):
                yield path.join(dirname, filename)


def verify_md5(filename: str, expected_md5: str) -> None:
    "Throw an exception if the filename does not match the checksum."
    md5 = checksum(filename)
    if md5 != expected_md5:
        raise ChecksumDoesNotMatch(filename)


class RecordWithInvalidJSON(Exception):
    pass


class ChecksumDoesNotMatch(Exception):
    pass
