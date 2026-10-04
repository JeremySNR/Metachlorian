"""S3-compatible object storage sources (AWS S3, MinIO, Backblaze B2, Wasabi, R2...).

Objects are downloaded to a local cache for analysis (ffmpeg needs random
access); the proxy and analysis outputs are kept, and the cached original is
removed after processing unless ``keep_originals`` is set. Credentials come
from the standard AWS environment/config chain; an endpoint for non-AWS
services can be given as ``s3://bucket/prefix?endpoint=https://host``.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qs, urlparse

from .scan import SKIP_SUFFIXES, VIDEO_EXTS


def parse_s3_uri(uri: str) -> tuple[str, str, dict[str, str]]:
    u = urlparse(uri)
    opts = {k: v[0] for k, v in parse_qs(u.query).items()}
    return u.netloc, u.path.lstrip("/"), opts


def client(opts: dict[str, str]):
    try:
        import boto3
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("S3 sources need the optional dependency: pip install 'metachlorian[s3]'") from e
    endpoint = opts.get("endpoint") or os.environ.get("METACHLORIAN_S3_ENDPOINT") or None
    return boto3.client("s3", endpoint_url=endpoint, region_name=opts.get("region") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1")


def iter_s3_videos(uri: str, cache_dir: Path) -> Iterator[tuple[str, Path]]:
    bucket, prefix, opts = parse_s3_uri(uri)
    s3 = client(opts)
    paginator = s3.get_paginator("list_objects_v2")
    cache_dir.mkdir(parents=True, exist_ok=True)
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            ext = os.path.splitext(key)[1].lower()
            if ext not in VIDEO_EXTS or ext in SKIP_SUFFIXES:
                continue
            canonical = f"s3://{bucket}/{key}"
            etag = obj.get("ETag", "").strip('"')
            local = cache_dir / (hashlib.sha1(canonical.encode()).hexdigest()[:16] + "-" + etag[:12] + ext)
            if not local.exists() or local.stat().st_size != obj["Size"]:
                tmp = local.with_suffix(ext + ".part")
                s3.download_file(bucket, key, str(tmp))
                tmp.replace(local)
                mtime = obj["LastModified"].timestamp()
                os.utime(local, (mtime, mtime))
            yield canonical, local
