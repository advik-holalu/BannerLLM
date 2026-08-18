import os
import re
import streamlit as st
from google.cloud import storage
from google.oauth2 import service_account

_ALLOWED_FOLDERS = {"skus", "design_elements", "references", "generated", "brand", "platforms"}

# Deeper path segments (e.g. references/<category-slug>/) must be slug-safe.
_SAFE_SEGMENT = re.compile(r"[a-z0-9_]+")


def _service_account_info() -> dict | None:
    """Return the inline [gcp_service_account] secret as a dict, or None.

    Uses the documented `"key" in st.secrets` / `st.secrets["key"]` access,
    which reliably descends into a [section] on Streamlit Cloud (unlike
    Secrets.get(), which can return None for a section).
    """
    try:
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:
        pass
    return None


def _storage_client() -> storage.Client:
    """Build a GCS client from credentials that work in both environments.

    Prefers an inline [gcp_service_account] secret section (used on Streamlit
    Cloud, where there is no local key file), and falls back to the
    GCP_KEY_PATH JSON key file for local development.
    """
    # Preferred: inline service-account credentials (Streamlit Cloud).
    # When present, build the client and RETURN immediately — the local
    # key-file check below is NEVER reached in this branch.
    service_account_info = _service_account_info()
    if service_account_info:
        creds = service_account.Credentials.from_service_account_info(
            service_account_info
        )
        return storage.Client(credentials=creds, project=creds.project_id)

    # Fallback: service-account JSON key file on disk (local dev). Only reached
    # when there is NO gcp_service_account secret.
    key_path = st.secrets.get("GCP_KEY_PATH")
    if not key_path:
        raise RuntimeError(
            "Set either a [gcp_service_account] section or GCP_KEY_PATH in "
            "Streamlit secrets."
        )
    if not os.path.exists(key_path):
        raise RuntimeError(
            f"GCP key file not found at {key_path}. Make sure the path in secrets is correct."
        )
    return storage.Client.from_service_account_json(key_path)


def _bucket() -> storage.bucket.Bucket:
    bucket_name = st.secrets.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError("GCS_BUCKET_NAME must be set in Streamlit secrets.")
    return _storage_client().bucket(bucket_name)


def _normalize_folder(folder: str) -> str:
    folder = folder.strip().strip("/")
    segments = [s for s in folder.split("/") if s]
    if not segments or segments[0] not in _ALLOWED_FOLDERS:
        raise ValueError(
            f"Invalid folder '{folder}'. Valid top-level folders: {sorted(_ALLOWED_FOLDERS)}"
        )
    # The top-level folder is whitelisted; any deeper segments (e.g. a category
    # slug under references/) must be slug-safe to avoid traversal/odd keys.
    for seg in segments[1:]:
        if not _SAFE_SEGMENT.fullmatch(seg):
            raise ValueError(f"Invalid path segment '{seg}' in folder '{folder}'")
    return "/".join(segments) + "/"


def _normalize_filename(filename: str) -> str:
    cleaned = filename.strip().lstrip("/\n\r")
    if "/" in cleaned or "\\" in cleaned:
        raise ValueError("filename must not contain path separators")
    return cleaned


def _blob_name(folder: str, filename: str) -> str:
    return _normalize_folder(folder) + _normalize_filename(filename)


def upload_image(folder: str, filename: str, data: bytes, content_type: str = "image/png", metadata: dict | None = None) -> None:
    bucket = _bucket()
    blob = bucket.blob(_blob_name(folder, filename))
    if metadata:
        # Custom object metadata values must be strings.
        blob.metadata = {str(k): str(v) for k, v in metadata.items() if v not in (None, "")}
    blob.upload_from_string(data, content_type=content_type)


def get_image(folder: str, filename: str) -> bytes | None:
    bucket = _bucket()
    blob = bucket.blob(_blob_name(folder, filename))
    if not blob.exists():
        return None
    return blob.download_as_bytes()


def list_images(folder: str) -> list[str]:
    bucket = _bucket()
    prefix = _normalize_folder(folder)
    blobs = bucket.list_blobs(prefix=prefix)
    names = []
    for blob in blobs:
        if blob.name.endswith("/"):
            continue
        name = blob.name[len(prefix) :]
        if name:
            names.append(name)
    return sorted(names)


def list_blobs_meta(folder: str) -> list[dict]:
    """List blobs under a folder with lightweight metadata in a SINGLE GCS call.

    Returns [{"name": <path relative to folder>, "updated": <epoch float>,
    "size": <int>, "metadata": <dict>}]. `name` may contain a sub-path (e.g.
    "blinkit/x.png"). Updated/size/custom-metadata come back with the listing —
    no per-blob fetch.
    """
    bucket = _bucket()
    prefix = _normalize_folder(folder)
    out = []
    for blob in bucket.list_blobs(prefix=prefix):
        if blob.name.endswith("/"):
            continue
        name = blob.name[len(prefix):]
        if not name:
            continue
        updated = getattr(blob, "updated", None)
        out.append({
            "name": name,
            "updated": updated.timestamp() if updated else 0.0,
            "size": blob.size or 0,
            "metadata": dict(blob.metadata or {}),
        })
    return out


def delete_image(folder: str, filename: str) -> bool:
    bucket = _bucket()
    blob = bucket.blob(_blob_name(folder, filename))
    if not blob.exists():
        return False
    blob.delete()
    return True
