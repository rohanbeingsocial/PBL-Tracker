"""Where uploaded reports and presentations are kept.

With B2_ENDPOINT, B2_KEY_ID, B2_APPLICATION_KEY and B2_BUCKET set, files go to a
private Backblaze B2 bucket through its S3-compatible API. Without them, for a laptop
demo, they go to the uploads/ folder next to the code. Either way the database only
stores the path; the bytes never go into Postgres.
"""
from functools import cache
from pathlib import Path

from finder.config import optional

LOCAL_DIR = Path(__file__).resolve().parent.parent / "uploads"


def _bucket() -> str | None:
    if all(optional(name) for name in ("B2_ENDPOINT", "B2_KEY_ID", "B2_APPLICATION_KEY", "B2_BUCKET")):
        return optional("B2_BUCKET")
    return None


@cache
def _client():
    import boto3     # only needed when a bucket is set up
    from botocore.config import Config

    endpoint = optional("B2_ENDPOINT")
    return boto3.client("s3", endpoint_url=endpoint if endpoint.startswith("https://") else f"https://{endpoint}",
                        aws_access_key_id=optional("B2_KEY_ID"),
                        aws_secret_access_key=optional("B2_APPLICATION_KEY"),
                        # Newer boto3 adds extra checksum headers by default that not every
                        # S3-compatible service accepts; only send them when required.
                        config=Config(request_checksum_calculation="when_required",
                                      response_checksum_validation="when_required"))


def save(path: str, data: bytes, content_type: str) -> None:
    bucket = _bucket()
    if bucket is None:
        target = LOCAL_DIR / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return
    _client().put_object(Bucket=bucket, Key=path, Body=data, ContentType=content_type)


def load(path: str) -> bytes:
    bucket = _bucket()
    if bucket is None:
        return (LOCAL_DIR / path).read_bytes()
    return _client().get_object(Bucket=bucket, Key=path)["Body"].read()


def delete(path: str) -> None:
    bucket = _bucket()
    if bucket is None:
        (LOCAL_DIR / path).unlink(missing_ok=True)
        return
    # B2 keeps old versions of a file, and a plain delete only hides it (the bytes
    # still count against the free 10 GB). Deleting every version removes it for good.
    listing = _client().list_object_versions(Bucket=bucket, Prefix=path)
    for version in listing.get("Versions", []) + listing.get("DeleteMarkers", []):
        if version["Key"] == path:
            _client().delete_object(Bucket=bucket, Key=path, VersionId=version["VersionId"])
