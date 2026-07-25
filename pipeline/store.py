"""
Minimal JSON-file datastore for products.

This is intentionally simple for an MVP — one JSON file, no migrations.
If usage grows past a handful of staff / dozens of products a month,
swap this for SQLite (the read/write surface here is tiny, so that's a
same-day change) without touching app.py's call sites.
"""
import json
import os
import re
import threading
import time
import uuid

_LOCK = threading.Lock()


def _data_path(base_dir: str) -> str:
    return os.path.join(base_dir, "data", "products.json")


def _load(base_dir: str) -> dict:
    path = _data_path(base_dir)
    if not os.path.exists(path):
        return {"products": {}}
    with open(path, "r") as f:
        return json.load(f)


def _save(base_dir: str, data: dict):
    path = _data_path(base_dir)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return text or "product"


def create_product(base_dir: str, brief: dict, shape: str) -> dict:
    with _LOCK:
        data = _load(base_dir)
        pid = uuid.uuid4().hex[:10]
        record = {
            "id": pid,
            "status": "review",
            "shape": shape,
            "brief": brief,
            "created_at": time.time(),
            "slug": None,
            "published_at": None,
        }
        data["products"][pid] = record
        _save(base_dir, data)
        return record


def get_product(base_dir: str, pid: str) -> dict:
    data = _load(base_dir)
    return data["products"].get(pid)


def list_products(base_dir: str) -> list:
    data = _load(base_dir)
    return sorted(data["products"].values(), key=lambda r: r["created_at"], reverse=True)


def update_product(base_dir: str, pid: str, **fields):
    with _LOCK:
        data = _load(base_dir)
        if pid not in data["products"]:
            raise KeyError(pid)
        data["products"][pid].update(fields)
        _save(base_dir, data)
        return data["products"][pid]


def unique_slug(base_dir: str, desired: str) -> str:
    data = _load(base_dir)
    existing = {r["slug"] for r in data["products"].values() if r.get("slug")}
    slug = desired
    n = 2
    while slug in existing:
        slug = f"{desired}-{n}"
        n += 1
    return slug
