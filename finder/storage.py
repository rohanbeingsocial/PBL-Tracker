"""Where uploaded reports and presentations are kept.

With SUPABASE_URL and SUPABASE_SECRET_KEY set, files go to a private Supabase
Storage bucket (SUPABASE_BUCKET, default 'project-files'). Without them, for a
laptop demo, they go to the uploads/ folder next to the code. Either way the
database only stores the path; the bytes never go into Postgres.
"""
from pathlib import Path

import httpx

from finder.config import optional

LOCAL_DIR = Path(__file__).resolve().parent.parent / "uploads"


def _supabase() -> tuple[str, str, str] | None:
    url, key = optional("SUPABASE_URL").rstrip("/"), optional("SUPABASE_SECRET_KEY")
    if not (url and key):
        return None
    return url, key, optional("SUPABASE_BUCKET") or "project-files"


def _headers(key: str) -> dict[str, str]:
    headers = {"apikey": key}
    # Older service_role keys are JWTs and also go in Authorization. The newer
    # sb_secret_ keys are not JWTs and only go in apikey.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def where() -> str:
    return "Supabase Storage" if _supabase() else "the uploads folder"


def save(path: str, data: bytes, content_type: str) -> None:
    remote = _supabase()
    if remote is None:
        target = LOCAL_DIR / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return
    url, key, bucket = remote
    response = httpx.post(f"{url}/storage/v1/object/{bucket}/{path}", content=data, timeout=60,
                          headers={**_headers(key), "Content-Type": content_type, "x-upsert": "false"})
    response.raise_for_status()


def load(path: str) -> bytes:
    remote = _supabase()
    if remote is None:
        return (LOCAL_DIR / path).read_bytes()
    url, key, bucket = remote
    response = httpx.get(f"{url}/storage/v1/object/{bucket}/{path}", headers=_headers(key), timeout=60)
    response.raise_for_status()
    return response.content


def delete(path: str) -> None:
    remote = _supabase()
    if remote is None:
        (LOCAL_DIR / path).unlink(missing_ok=True)
        return
    url, key, bucket = remote
    response = httpx.request("DELETE", f"{url}/storage/v1/object/{bucket}", headers=_headers(key),
                             json={"prefixes": [path]}, timeout=60)
    response.raise_for_status()
