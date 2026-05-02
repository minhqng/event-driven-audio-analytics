"""Shared claim-check storage helpers and backend abstraction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urlparse

from event_driven_audio_analytics.shared.checksum import sha256_bytes, sha256_file


LOGICAL_ARTIFACTS_ROOT = PurePosixPath("/artifacts")
DEFAULT_MINIO_BUCKET = "fma-small-artifacts"
SUPPORTED_STORAGE_BACKENDS = {"local", "minio"}


@dataclass(frozen=True, slots=True)
class StorageBackendSettings:
    """Settings for the claim-check artifact backend."""

    backend: str = "local"
    artifacts_root: Path = Path("/app/artifacts")
    bucket: str = DEFAULT_MINIO_BUCKET
    endpoint_url: str = "http://minio:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    region: str = "us-east-1"
    secure: bool = False
    create_bucket: bool = False

    def normalized_backend(self) -> str:
        backend = self.backend.strip().lower()
        if backend not in SUPPORTED_STORAGE_BACKENDS:
            raise ValueError(
                "STORAGE_BACKEND must be one of: "
                f"{', '.join(sorted(SUPPORTED_STORAGE_BACKENDS))}."
            )
        return backend


@dataclass(frozen=True, slots=True)
class ParsedArtifactUri:
    """Validated claim-check URI split into backend-specific parts."""

    scheme: str
    bucket: str | None
    key: str


class ClaimCheckStore(Protocol):
    """Storage backend used by claim-check artifact producers and consumers."""

    settings: StorageBackendSettings

    def segment_uri(self, run_id: str, track_id: int, segment_idx: int) -> str: ...

    def manifest_uri(self, run_id: str) -> str: ...

    def write_bytes(self, uri: str, payload: bytes, *, content_type: str) -> str: ...

    def read_bytes(self, uri: str) -> bytes: ...

    def exists(self, uri: str) -> bool: ...

    def checksum(self, uri: str) -> str: ...

    def read_parquet(self, uri: str): ...

    def write_parquet(self, uri: str, frame: object) -> None: ...

    def local_path(self, uri: str) -> Path | None: ...


def validate_run_id(run_id: str) -> str:
    """Validate a run id before using it in events, DB rows, or artifact paths."""

    normalized = run_id.strip()
    if normalized == "":
        raise ValueError("run_id must not be empty or whitespace.")
    if normalized in {".", ".."} or any(
        character in normalized for character in ("/", "\\", ":", ".")
    ) or any(
        character.isspace() for character in run_id
    ):
        raise ValueError(
            "run_id must be a single relative path segment without whitespace "
            "or reserved path characters."
        )
    return normalized


def _as_logical_uri(*parts: object) -> str:
    """Build a service-mount-independent claim-check URI."""

    return str(LOGICAL_ARTIFACTS_ROOT.joinpath(*(str(part) for part in parts)))


def _run_relative_key(run_id: str, *parts: object) -> str:
    """Build a normalized object key below one validated run namespace."""

    return str(PurePosixPath("runs", validate_run_id(run_id), *(str(part) for part in parts)))


def _reject_unsafe_key_parts(key: str) -> None:
    parts = PurePosixPath(key).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"artifact URI key is not safe: {key!r}.")


def _logical_relative_path(artifact_uri: str) -> Path | None:
    normalized_uri = artifact_uri.strip().replace("\\", "/")
    logical_root = str(LOGICAL_ARTIFACTS_ROOT)
    if normalized_uri == logical_root:
        raise ValueError("artifact_uri must point below /artifacts.")

    logical_prefix = f"{logical_root}/"
    if not normalized_uri.startswith(logical_prefix):
        return None

    logical_path = PurePosixPath(normalized_uri.removeprefix(logical_prefix))
    if any(part in {"", ".", ".."} for part in logical_path.parts):
        raise ValueError(f"artifact_uri '{artifact_uri}' escapes artifacts_root.")
    return Path(*logical_path.parts)


def run_root(artifacts_root: Path, run_id: str) -> Path:
    """Return the shared storage root for a run."""

    return artifacts_root / "runs" / validate_run_id(run_id)


def resolve_artifact_uri(artifacts_root: Path, artifact_uri: str) -> Path:
    """Resolve a claim-check URI while enforcing the configured artifacts boundary."""

    if not artifact_uri.strip():
        raise ValueError("artifact_uri must not be empty or whitespace.")

    root = artifacts_root.resolve()
    logical_relative = _logical_relative_path(artifact_uri)
    if logical_relative is not None:
        candidates = [root / logical_relative]
    else:
        candidate = Path(artifact_uri)
        candidates = [candidate] if candidate.is_absolute() else [candidate, root / candidate]

    resolved_candidates: list[Path] = []
    for candidate_path in candidates:
        resolved = candidate_path.resolve()
        resolved_candidates.append(resolved)
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved

    rendered_candidates = ", ".join(path.as_posix() for path in resolved_candidates)
    raise ValueError(
        "artifact_uri must resolve within the configured artifacts_root "
        f"root={root.as_posix()} candidates={rendered_candidates}."
    )


def parse_artifact_uri(uri: str, *, bucket: str = DEFAULT_MINIO_BUCKET) -> ParsedArtifactUri:
    """Parse a supported claim-check URI and reject unsupported schemes."""

    normalized_uri = uri.strip()
    if not normalized_uri:
        raise ValueError("artifact_uri must not be empty or whitespace.")

    parsed = urlparse(normalized_uri)
    if parsed.scheme == "s3":
        if parsed.netloc != bucket:
            raise ValueError(
                f"s3 artifact_uri bucket mismatch expected={bucket!r} actual={parsed.netloc!r}."
            )
        key = parsed.path.lstrip("/")
        _reject_unsafe_key_parts(key)
        return ParsedArtifactUri(scheme="s3", bucket=parsed.netloc, key=key)

    if parsed.scheme not in {"", "file"}:
        raise ValueError(f"unsupported artifact_uri scheme: {parsed.scheme}.")

    logical_relative = _logical_relative_path(normalized_uri)
    if logical_relative is None:
        raise ValueError(
            "local artifact_uri must use the logical /artifacts/ claim-check prefix."
        )
    key = PurePosixPath(*logical_relative.parts).as_posix()
    _reject_unsafe_key_parts(key)
    return ParsedArtifactUri(scheme="local", bucket=None, key=key)


def _looks_like_s3_uri(uri: str) -> bool:
    return urlparse(uri.strip()).scheme == "s3"


def validate_segment_artifact_uri(
    uri: str,
    *,
    run_id: str,
    track_id: int,
    segment_idx: int,
    bucket: str = DEFAULT_MINIO_BUCKET,
) -> ParsedArtifactUri:
    """Ensure an artifact URI points to exactly the expected logical segment."""

    parsed = parse_artifact_uri(uri, bucket=bucket)
    expected_key = _run_relative_key(run_id, "segments", track_id, f"{segment_idx}.wav")
    if parsed.key != expected_key:
        raise ValueError(
            "artifact_uri does not match the expected run-scoped segment key "
            f"expected={expected_key!r} actual={parsed.key!r}."
        )
    return parsed


def validate_manifest_artifact_uri(
    uri: str,
    *,
    run_id: str,
    bucket: str = DEFAULT_MINIO_BUCKET,
) -> ParsedArtifactUri:
    """Ensure a manifest URI points to exactly the expected run manifest."""

    parsed = parse_artifact_uri(uri, bucket=bucket)
    expected_key = _run_relative_key(run_id, "manifests", "segments.parquet")
    if parsed.key != expected_key:
        raise ValueError(
            "manifest_uri does not match the expected run-scoped manifest key "
            f"expected={expected_key!r} actual={parsed.key!r}."
        )
    return parsed


def segment_artifact_uri(
    artifacts_root: Path,
    run_id: str,
    track_id: int,
    segment_idx: int,
) -> str:
    """Build the canonical artifact URI for a segment."""

    validate_run_id(run_id)
    return _as_logical_uri("runs", run_id, "segments", track_id, f"{segment_idx}.wav")


def manifest_uri(artifacts_root: Path, run_id: str) -> str:
    """Build the canonical manifest URI for a run."""

    validate_run_id(run_id)
    return _as_logical_uri("runs", run_id, "manifests", "segments.parquet")


class LocalClaimCheckStore:
    """Filesystem-backed claim-check store preserving the existing local layout."""

    def __init__(self, settings: StorageBackendSettings) -> None:
        self.settings = settings

    def segment_uri(self, run_id: str, track_id: int, segment_idx: int) -> str:
        return segment_artifact_uri(self.settings.artifacts_root, run_id, track_id, segment_idx)

    def manifest_uri(self, run_id: str) -> str:
        return manifest_uri(self.settings.artifacts_root, run_id)

    def _path(self, uri: str) -> Path:
        parsed = urlparse(uri.strip())
        if parsed.scheme:
            raise ValueError(
                "local claim-check store cannot resolve artifact_uri schemes "
                f"scheme={parsed.scheme!r}."
            )
        return resolve_artifact_uri(self.settings.artifacts_root, uri)

    def write_bytes(self, uri: str, payload: bytes, *, content_type: str) -> str:
        path = self._path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return sha256_bytes(payload)

    def read_bytes(self, uri: str) -> bytes:
        path = self._path(uri)
        if not path.exists():
            raise FileNotFoundError(f"Artifact does not exist: {path.as_posix()}")
        return path.read_bytes()

    def exists(self, uri: str) -> bool:
        try:
            return self._path(uri).exists()
        except ValueError:
            return False

    def checksum(self, uri: str) -> str:
        return sha256_file(self._path(uri))

    def read_parquet(self, uri: str):
        import polars as pl

        path = self._path(uri)
        if not path.exists():
            raise FileNotFoundError(f"Artifact does not exist: {path.as_posix()}")
        return pl.read_parquet(path)

    def write_parquet(self, uri: str, frame: object) -> None:
        path = self._path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(path)

    def local_path(self, uri: str) -> Path | None:
        return self._path(uri)

    def probe(self, run_id: str) -> None:
        probe_uri = _as_logical_uri("runs", validate_run_id(run_id), "probes", "storage-probe")
        self.write_bytes(probe_uri, b"ok", content_type="application/octet-stream")
        if self.read_bytes(probe_uri) != b"ok":
            raise RuntimeError("Local claim-check storage probe readback failed.")
        self._path(probe_uri).unlink()


class S3ClaimCheckStore:
    """S3-compatible claim-check store for MinIO private-cloud runs."""

    def __init__(self, settings: StorageBackendSettings, client: object | None = None) -> None:
        self.settings = settings
        self._client = client or self._build_client(settings)

    @staticmethod
    def _build_client(settings: StorageBackendSettings) -> object:
        import boto3

        return boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            region_name=settings.region,
            use_ssl=settings.secure,
        )

    def _s3_uri(self, key: str) -> str:
        _reject_unsafe_key_parts(key)
        return f"s3://{self.settings.bucket}/{key}"

    def _key(self, uri: str) -> str:
        parsed = parse_artifact_uri(uri, bucket=self.settings.bucket)
        if parsed.scheme != "s3":
            raise ValueError("minio claim-check store requires s3:// artifact_uri values.")
        return parsed.key

    def segment_uri(self, run_id: str, track_id: int, segment_idx: int) -> str:
        return self._s3_uri(_run_relative_key(run_id, "segments", track_id, f"{segment_idx}.wav"))

    def manifest_uri(self, run_id: str) -> str:
        return self._s3_uri(_run_relative_key(run_id, "manifests", "segments.parquet"))

    def write_bytes(self, uri: str, payload: bytes, *, content_type: str) -> str:
        self._client.put_object(
            Bucket=self.settings.bucket,
            Key=self._key(uri),
            Body=payload,
            ContentType=content_type,
        )
        return sha256_bytes(payload)

    def read_bytes(self, uri: str) -> bytes:
        key = self._key(uri)
        try:
            response = self._client.get_object(Bucket=self.settings.bucket, Key=key)
        except Exception as exc:
            if _is_s3_not_found(exc):
                raise FileNotFoundError(f"S3 artifact does not exist: {uri}") from exc
            raise
        return response["Body"].read()

    def exists(self, uri: str) -> bool:
        try:
            self._client.head_object(Bucket=self.settings.bucket, Key=self._key(uri))
            return True
        except Exception as exc:
            if _is_s3_not_found(exc):
                return False
            raise

    def checksum(self, uri: str) -> str:
        return sha256_bytes(self.read_bytes(uri))

    def read_parquet(self, uri: str):
        import polars as pl

        return pl.read_parquet(BytesIO(self.read_bytes(uri)))

    def write_parquet(self, uri: str, frame: object) -> None:
        buffer = BytesIO()
        frame.write_parquet(buffer)
        self.write_bytes(
            uri,
            buffer.getvalue(),
            content_type="application/vnd.apache.parquet",
        )

    def local_path(self, uri: str) -> Path | None:
        self._key(uri)
        return None

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.settings.bucket)
            return
        except Exception as exc:
            if not _is_s3_not_found(exc) or not self.settings.create_bucket:
                raise
        self._client.create_bucket(Bucket=self.settings.bucket)

    def check_bucket(self) -> None:
        self._client.head_bucket(Bucket=self.settings.bucket)

    def probe(self, run_id: str) -> None:
        self.ensure_bucket()
        probe_uri = self._s3_uri(_run_relative_key(run_id, "probes", "storage-probe"))
        self.write_bytes(probe_uri, b"ok", content_type="application/octet-stream")
        if self.read_bytes(probe_uri) != b"ok":
            raise RuntimeError("S3 claim-check storage probe readback failed.")
        self._client.delete_object(Bucket=self.settings.bucket, Key=self._key(probe_uri))


def _is_s3_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = str(response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}
    return False


def build_claim_check_store(
    settings: StorageBackendSettings,
    *,
    s3_client: object | None = None,
) -> ClaimCheckStore:
    """Build a claim-check store for the configured backend."""

    backend = settings.normalized_backend()
    if backend == "local":
        return LocalClaimCheckStore(settings)
    return S3ClaimCheckStore(settings, client=s3_client)


def build_claim_check_store_for_uri(
    settings: StorageBackendSettings,
    uri: str,
    *,
    s3_client: object | None = None,
) -> ClaimCheckStore:
    """Build the backend that matches one persisted claim-check URI."""

    if _looks_like_s3_uri(uri):
        return S3ClaimCheckStore(replace(settings, backend="minio"), client=s3_client)
    return LocalClaimCheckStore(replace(settings, backend="local"))


def storage_settings_for_local(artifacts_root: Path) -> StorageBackendSettings:
    """Build local storage settings for compatibility call sites."""

    return StorageBackendSettings(backend="local", artifacts_root=artifacts_root)
