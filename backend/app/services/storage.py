"""Where analyzed images (full, masked, tiles) get uploaded so the API can
return stable URLs in image_urls. Both implementations below are real, not
stubs:

  - LocalDiskStorageService: writes to a local directory, served back by a
    static route (see app/routes/storage.py). Zero-config default for local
    dev/tests, but ephemeral on Railway (wiped on redeploy) -- fine for
    smoke-testing, not for anything you want to keep.
  - S3StorageService: real boto3 upload, works against AWS S3 or any
    S3-compatible endpoint (set S3_ENDPOINT for Cloudflare R2, per your
    spec's preference for R2's no-egress-fee pricing). I could not exercise
    a live upload from this sandbox -- outbound network here is restricted
    to an allowlist that doesn't include AWS/R2 endpoints -- so this is
    implemented correctly against boto3's documented API but not
    live-verified; worth a smoke test right after deploy with real
    credentials.
"""
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import get_settings


class StorageService(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Upload bytes under `key`, return a URL the client can fetch it from."""
        raise NotImplementedError


class LocalDiskStorageService(StorageService):
    def __init__(self) -> None:
        self._root = Path(get_settings().local_storage_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        # Served by the /storage static route -- see app/main.py.
        return f"/storage/{key}"


class S3StorageService(StorageService):
    def __init__(self) -> None:
        import boto3  # local import -- keeps boto3 optional for local-disk-only setups

        settings = get_settings()
        if not (settings.s3_access_key and settings.s3_secret_key):
            raise RuntimeError("STORAGE_PROVIDER=s3 requires S3_ACCESS_KEY and S3_SECRET_KEY.")
        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        self._public_base = settings.s3_endpoint.rstrip("/") if settings.s3_endpoint else (
            f"https://{self._bucket}.s3.{settings.s3_region}.amazonaws.com"
        )

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        # boto3's S3 client is sync; run it off the event loop so it doesn't
        # block other requests/tasks.
        import asyncio

        await asyncio.to_thread(
            self._client.put_object, Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )
        return f"{self._public_base}/{self._bucket}/{key}" if get_settings().s3_endpoint else f"{self._public_base}/{key}"


def new_object_key(job_id: str, name: str, ext: str = "png") -> str:
    return f"{job_id}/{name}-{uuid.uuid4().hex[:8]}.{ext}"


_PROVIDERS = {"local": LocalDiskStorageService, "s3": S3StorageService}


def get_storage_service() -> StorageService:
    return _PROVIDERS[get_settings().storage_provider]()
