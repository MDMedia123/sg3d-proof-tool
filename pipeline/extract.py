"""
Artwork extraction from customer-supplied packaging PDFs.

Two source types show up in practice:

1. "Flat" PDFs — one or more pages containing rendered artwork panels
   (sometimes a clean version plus a dieline/registration-mark version).
   We render each page to a raster image and slice out the distinct
   printed panels on it.

2. "U3D" PDFs — an Esko-style 3D proof with an embedded U3D model
   (Type/3D annotation). The real print artwork is usually baked into
   the model's textures at high resolution, so we pull those bitmaps
   straight out of the raw U3D stream instead of trying to re-render
   the 3D view.

Both paths return a flat list of `Candidate` images for a human to look
at and assign to template slots in the review screen — this module
does NOT try to guess the final layout with 100% confidence. Packaging
dielines vary too much for that to be honest automation; it proposes,
a person confirms.
"""
import io
import re
import subprocess
import tempfile
import os
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from PIL import Image
import pikepdf


@dataclass
class Candidate:
    image: Image.Image
    label: str                 # short human-readable description
    source: str                 # "flat" or "u3d"
    page: Optional[int] = None
    is_guide: bool = False      # looks like a dieline/registration-mark version
    shape_guess: str = "panel"  # "circular", "wide-panel", "panel"
    score: float = 0.0          # rough "likely useful" ranking, higher = better


def detect_pdf_kind(pdf_path: str) -> str:
    """Returns 'u3d' if the PDF has an embedded 3D model, else 'flat'."""
    try:
        with pikepdf.open(pdf_path) as pdf:
            for obj in pdf.objects:
                try:
                    if obj.get("/Subtype") == pikepdf.Name("/U3D"):
                        return "u3d"
                except Exception:
                    continue
    except Exception:
        pass
    return "flat"


# ---------------------------------------------------------------------------
# Flat-PDF extraction
# ---------------------------------------------------------------------------

def render_pdf_pages(pdf_path: str, dpi: int = 200) -> List[Image.Image]:
    """Rasterises every page of the PDF using poppler's pdftoppm."""
    with tempfile.TemporaryDirectory() as tmp:
        prefix = os.path.join(tmp, "page")
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), pdf_path, prefix],
            check=True, capture_output=True,
        )
        files = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        return [Image.open(os.path.join(tmp, f)).convert("RGB").copy() for f in files]


def _content_rows(mask: np.ndarray, min_frac: float = 0.004):
    """Finds contiguous row-ranges that contain non-background content."""
    density = mask.mean(axis=1)
    active = density > min_frac
    regions = []
    start = None
    for y, on in enumerate(active):
        if on and start is None:
            start = y
        elif not on and start is not None:
            regions.append((start, y))
            start = None
    if start is not None:
        regions.append((start, len(active)))
    # merge regions that are very close together (small gaps/anti-aliasing)
    merged = []
    for r in regions:
        if merged and r[0] - merged[-1][1] < 15:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(list(r))
    return [tuple(r) for r in merged if r[1] - r[0] > 40]


def _looks_like_guide(region_arr: np.ndarray) -> bool:
    """
    Best-effort hint only. Packaging artwork legitimately uses red/blue too
    (foil edges, brand colours), so this is deliberately NOT used to hide or
    down-rank anything — it's just a soft label to help a human scan faster.
    A dense grid of many short, evenly-spaced pure-colour segments (typical
    of registration/fold-guide rulers) is a much stronger signal than "some
    red exists", but still not reliable enough to act on automatically.
    """
    r, g, b = region_arr[:, :, 0].astype(int), region_arr[:, :, 1].astype(int), region_arr[:, :, 2].astype(int)
    pure_red = (r > 200) & (g < 60) & (b < 60)
    pure_blue = (b > 200) & (r < 60) & (g < 60)
    frac = (pure_red | pure_blue).mean()
    return bool(frac > 0.02)  # only flag when red/blue is a substantial share of the image


def _looks_circular(region_arr: np.ndarray, mask: np.ndarray) -> bool:
    h, w = mask.shape
    if abs(h - w) / max(h, w) > 0.2:
        return False
    corner = 6
    corners_empty = (
        mask[:corner, :corner].mean() < 0.15 and
        mask[:corner, -corner:].mean() < 0.15 and
        mask[-corner:, :corner].mean() < 0.15 and
        mask[-corner:, -corner:].mean() < 0.15
    )
    return bool(corners_empty)


def extract_flat_candidates(pdf_path: str, dpi: int = 160) -> List[Candidate]:
    pages = render_pdf_pages(pdf_path, dpi=dpi)
    candidates = []
    for page_idx, page in enumerate(pages):
        # Always offer the untouched full page as a candidate. Auto-segmentation
        # below assumes artwork sits in separate axis-aligned rectangular blocks
        # with white space between them — real dielines routinely break that
        # assumption (rotated die shapes, artwork that's one connected blob
        # across every panel/flap, etc). When that happens the full page is
        # still here so a person can pick it and use the rotate/crop controls
        # in the review screen to manually pull out the panel they need.
        try:
            candidates.append(Candidate(
                image=page,
                label=f"Page {page_idx+1} — full page (manual crop)",
                source="flat",
                page=page_idx + 1,
                is_guide=False,
                shape_guess="panel",
                score=page.size[0] * page.size[1] * 0.5,  # visible, but auto-segmented panels can outrank it
            ))
        except Exception:
            pass

        try:
            arr = np.array(page)
            gray = arr.mean(axis=2)
            mask = gray < 250
            if mask.mean() < 0.002:
                continue
            row_regions = _content_rows(mask)
            for (y0, y1) in row_regions:
                band_mask = mask[y0:y1, :]
                col_density = band_mask.mean(axis=0)
                active = col_density > 0.004
                x_regions = []
                start = None
                for x, on in enumerate(active):
                    if on and start is None:
                        start = x
                    elif not on and start is not None:
                        x_regions.append((start, x))
                        start = None
                if start is not None:
                    x_regions.append((start, len(active)))
                x_regions = [r for r in x_regions if r[1] - r[0] > 60]
                # merge close x-regions
                merged = []
                for r in x_regions:
                    if merged and r[0] - merged[-1][1] < 20:
                        merged[-1] = (merged[-1][0], r[1])
                    else:
                        merged.append(list(r))
                for (x0, x1) in merged:
                    try:
                        pad = 4
                        x0p, x1p = max(0, x0 - pad), min(arr.shape[1], x1 + pad)
                        y0p, y1p = max(0, y0 - pad), min(arr.shape[0], y1 + pad)
                        crop = page.crop((x0p, y0p, x1p, y1p))
                        crop_arr = np.array(crop)
                        crop_mask = mask[y0p:y1p, x0p:x1p]
                        is_guide = _looks_like_guide(crop_arr)
                        shape_guess = "circular" if _looks_circular(crop_arr, crop_mask) else (
                            "wide-panel" if (x1p - x0p) / max(1, (y1p - y0p)) > 2.2 else "panel"
                        )
                        area = (x1p - x0p) * (y1p - y0p)
                        candidates.append(Candidate(
                            image=crop,
                            label=f"Page {page_idx+1} — {shape_guess}{' (may include guide marks)' if is_guide else ''}",
                            source="flat",
                            page=page_idx + 1,
                            is_guide=is_guide,
                            shape_guess=shape_guess,
                            # Ranked by area only — larger panels are more likely to be
                            # the primary artwork. Whether a page is a "clean" or
                            # "dieline" version is left entirely to the reviewer: it's
                            # obvious at a glance and not reliable to guess in code.
                            score=area,
                        ))
                    except Exception:
                        # One odd region (e.g. an unusual shape the heuristics
                        # weren't built for) shouldn't take down the whole
                        # extraction — skip it, the full-page fallback above
                        # still covers this case.
                        continue
        except Exception:
            # Segmentation failed for this page entirely — the full-page
            # fallback candidate added above still lets a person work with it.
            continue
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# U3D extraction
# ---------------------------------------------------------------------------

def _find_u3d_stream(pdf_path: str) -> Optional[bytes]:
    with pikepdf.open(pdf_path) as pdf:
        for obj in pdf.objects:
            try:
                if obj.get("/Subtype") == pikepdf.Name("/U3D"):
                    return obj.read_bytes()
            except Exception:
                continue
    return None


def extract_u3d_candidates(pdf_path: str, min_side: int = 200) -> List[Candidate]:
    data = _find_u3d_stream(pdf_path)
    if not data:
        return []

    candidates = []

    # JPEG blocks: SOI (FFD8FF) .. EOI (FFD9)
    for m in re.finditer(rb"\xff\xd8\xff", data):
        start = m.start()
        end = data.find(b"\xff\xd9", start)
        if end == -1:
            continue
        end += 2
        chunk = data[start:end]
        try:
            im = Image.open(io.BytesIO(chunk))
            im.load()
            im = im.convert("RGB")
        except Exception:
            continue
        if min(im.size) < min_side:
            continue
        candidates.append(Candidate(
            image=im, label=f"Embedded texture {im.size[0]}x{im.size[1]}",
            source="u3d", score=im.size[0] * im.size[1],
        ))

    # PNG blocks: signature .. IEND
    sig = b"\x89PNG\r\n\x1a\n"
    iend = b"IEND\xaeB`\x82"
    for m in re.finditer(re.escape(sig), data):
        start = m.start()
        end = data.find(iend, start)
        if end == -1:
            continue
        end += len(iend)
        chunk = data[start:end]
        try:
            im = Image.open(io.BytesIO(chunk))
            im.load()
            im = im.convert("RGBA")
        except Exception:
            continue
        if min(im.size) < min_side:
            continue
        candidates.append(Candidate(
            image=im, label=f"Embedded texture {im.size[0]}x{im.size[1]} (png)",
            source="u3d", score=im.size[0] * im.size[1],
        ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    # de-duplicate near-identical sizes/byte content isn't attempted here —
    # the review screen shows thumbnails so duplicates are obvious and easy
    # for a person to skip in a couple of seconds.
    return candidates[:8]


def extract_candidates(pdf_path: str) -> (str, List[Candidate]):
    kind = detect_pdf_kind(pdf_path)
    if kind == "u3d":
        return kind, extract_u3d_candidates(pdf_path)
    return kind, extract_flat_candidates(pdf_path)
