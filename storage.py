import os
import re
import streamlit as st
from google.cloud import storage

_ALLOWED_FOLDERS = {"skus", "design_elements", "references", "generated", "brand", "platforms"}

# Deeper path segments (e.g. references/<category-slug>/) must be slug-safe.
_SAFE_SEGMENT = re.compile(r"[a-z0-9_]+")


def _bucket() -> storage.bucket.Bucket:
    secrets = st.secrets
    key_path = secrets.get("GCP_KEY_PATH")
    bucket_name = secrets.get("GCS_BUCKET_NAME")
    if not key_path or not bucket_name:
        raise RuntimeError(
            "GCP_KEY_PATH and GCS_BUCKET_NAME must be set in Streamlit secrets."
        )
    if not os.path.exists(key_path):
        raise RuntimeError(
            f"GCP key file not found at {key_path}. Make sure the path in secrets is correct."
        )
    client = storage.Client.from_service_account_json(key_path)
    return client.bucket(bucket_name)


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


def upload_image(folder: str, filename: str, data: bytes, content_type: str = "image/png") -> None:
    bucket = _bucket()
    blob = bucket.blob(_blob_name(folder, filename))
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


def delete_image(folder: str, filename: str) -> bool:
    bucket = _bucket()
    blob = bucket.blob(_blob_name(folder, filename))
    if not blob.exists():
        return False
    blob.delete()
    return True
