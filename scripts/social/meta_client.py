#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in local scripts
    load_dotenv = None

if load_dotenv:
    PROJECT_DIR = Path(__file__).resolve().parents[2]
    load_dotenv(PROJECT_DIR / "backend" / ".env")

META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v23.0")
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
META_PAGE_ACCESS_TOKEN = os.environ.get("META_PAGE_ACCESS_TOKEN")
META_PAGE_ID = os.environ.get("META_PAGE_ID")
META_INSTAGRAM_BUSINESS_ID = os.environ.get("META_INSTAGRAM_BUSINESS_ID")


class MetaConfigError(RuntimeError):
    pass


class MetaApiError(RuntimeError):
    pass


def validate_meta_config(require_instagram=True, require_facebook=True):
    missing = []
    if not META_ACCESS_TOKEN:
        missing.append("META_ACCESS_TOKEN")
    if require_facebook and not META_PAGE_ID:
        missing.append("META_PAGE_ID")
    if require_instagram and not META_INSTAGRAM_BUSINESS_ID:
        missing.append("META_INSTAGRAM_BUSINESS_ID")

    if missing:
        raise MetaConfigError("Faltan variables Meta: " + ", ".join(missing))


def graph_post(path, data, access_token=None):
    payload = {**data, "access_token": access_token or META_ACCESS_TOKEN}
    response = requests.post(f"{META_GRAPH_BASE}/{path.lstrip('/')}", data=payload, timeout=60)
    body = response.json() if response.content else {}
    if response.status_code >= 400 or "error" in body:
        error = body.get("error") or body
        raise MetaApiError(f"{path}: {error}")
    return body


def graph_post_files(path, data, files, access_token=None):
    payload = {**data, "access_token": access_token or META_ACCESS_TOKEN}
    response = requests.post(f"{META_GRAPH_BASE}/{path.lstrip('/')}", data=payload, files=files, timeout=120)
    body = response.json() if response.content else {}
    if response.status_code >= 400 or "error" in body:
        error = body.get("error") or body
        raise MetaApiError(f"{path}: {error}")
    return body


def publish_instagram_carousel(image_urls, caption):
    validate_meta_config(require_instagram=True, require_facebook=False)

    children = []
    for url in image_urls:
        created = graph_post(
            f"{META_INSTAGRAM_BUSINESS_ID}/media",
            {
                "image_url": url,
                "is_carousel_item": "true",
            },
        )
        children.append(created["id"])

    carousel = graph_post(
        f"{META_INSTAGRAM_BUSINESS_ID}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
        },
    )

    # Meta procesa containers async. Una espera corta evita publicar demasiado rápido.
    time.sleep(5)
    published = graph_post(
        f"{META_INSTAGRAM_BUSINESS_ID}/media_publish",
        {"creation_id": carousel["id"]},
    )
    return {"container_id": carousel["id"], "media_id": published.get("id"), "children": children}


def publish_facebook_carousel(image_urls, caption):
    validate_meta_config(require_instagram=False, require_facebook=True)
    page_access_token = META_PAGE_ACCESS_TOKEN or META_ACCESS_TOKEN

    attached_media = []
    for url in image_urls:
        photo = graph_post(
            f"{META_PAGE_ID}/photos",
            {
                "url": url,
                "published": "false",
            },
            access_token=page_access_token,
        )
        attached_media.append({"media_fbid": photo["id"]})

    post_data = {"message": caption}
    for index, media in enumerate(attached_media):
        post_data[f"attached_media[{index}]"] = json.dumps(media)

    post = graph_post(f"{META_PAGE_ID}/feed", post_data, access_token=page_access_token)
    return {"post_id": post.get("id"), "photos": attached_media}


def publish_facebook_carousel_from_files(image_paths, caption):
    validate_meta_config(require_instagram=False, require_facebook=True)
    page_access_token = META_PAGE_ACCESS_TOKEN or META_ACCESS_TOKEN

    attached_media = []
    for image_path in image_paths:
        with Path(image_path).open("rb") as image_file:
            photo = graph_post_files(
                f"{META_PAGE_ID}/photos",
                {"published": "false"},
                {"source": image_file},
                access_token=page_access_token,
            )
        attached_media.append({"media_fbid": photo["id"]})

    post_data = {"message": caption}
    for index, media in enumerate(attached_media):
        post_data[f"attached_media[{index}]"] = json.dumps(media)

    post = graph_post(f"{META_PAGE_ID}/feed", post_data, access_token=page_access_token)
    return {"post_id": post.get("id"), "photos": attached_media}
