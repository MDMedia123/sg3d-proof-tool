"""
S&G 3D Proof Tool — MVP

Internal Flask app: staff log in, upload a customer brief + high-res
packaging PDF, review auto-extracted artwork, tweak a couple of
placement controls, preview the live 3D mockup, then publish it to a
public link (/proofs/<slug>) that gets sent to the customer.

Run locally:
    pip install -r requirements.txt
    export SG_ADMIN_PASSWORD=your-password-here
    export SG_SECRET_KEY=some-random-string
    python app.py
    -> http://localhost:5000

See README.md for deployment notes.
"""
import os
import functools
import io

from flask import (
    Flask, request, redirect, url_for, session, render_template,
    send_file, abort, jsonify, flash,
)
from PIL import Image

from pipeline import extract, shapes, store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SG_SECRET_KEY", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB, high-res PDFs can be large

ADMIN_PASSWORD = os.environ.get("SG_ADMIN_PASSWORD", "changeme")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Incorrect password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    products = store.list_products(BASE_DIR)
    return render_template("dashboard.html", products=products)


# ---------------------------------------------------------------------------
# New product: brief + PDF upload -> extraction -> review
# ---------------------------------------------------------------------------

@app.route("/new", methods=["GET", "POST"])
@login_required
def new_product():
    if request.method == "GET":
        return render_template("new_product.html", shapes=shapes.SHAPE_TEMPLATES)

    brief = {
        "customer": request.form.get("customer", "").strip(),
        "product": request.form.get("product", "").strip(),
        "die_ref": request.form.get("die_ref", "").strip(),
        "operator": request.form.get("operator", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    shape_key = request.form.get("shape")
    if shape_key not in shapes.SHAPE_TEMPLATES:
        flash("Please choose a valid packaging shape.")
        return redirect(url_for("new_product"))

    pdf_file = request.files.get("pdf")
    if not pdf_file or not pdf_file.filename.lower().endswith(".pdf"):
        flash("Please attach a PDF.")
        return redirect(url_for("new_product"))

    record = store.create_product(BASE_DIR, brief, shape_key)
    pid = record["id"]

    product_dir = os.path.join(UPLOAD_DIR, pid)
    os.makedirs(product_dir, exist_ok=True)
    pdf_path = os.path.join(product_dir, "source.pdf")
    pdf_file.save(pdf_path)

    try:
        kind, candidates = extract.extract_candidates(pdf_path)
    except Exception as e:
        # Never leave staff staring at a blank/stuck page — surface the
        # failure and let them retry instead of hitting an unhandled 500.
        flash(f"Couldn't process that PDF: {e}. The file may be corrupt, "
              f"password-protected, or an unusual format — try re-exporting "
              f"it and uploading again.")
        return redirect(url_for("new_product"))

    if not candidates:
        flash("No artwork panels were found automatically in that PDF. "
              "This can happen with unusual dieline layouts. Try again — "
              "you'll still get the full page(s) as a fallback to manually crop from.")

    cand_dir = os.path.join(product_dir, "candidates")
    os.makedirs(cand_dir, exist_ok=True)
    cand_meta = []
    for i, cand in enumerate(candidates):
        try:
            img = cand.image.convert("RGB")
            fname = f"cand_{i}.png"
            # Full resolution — this is what actually gets used to build the
            # final 3D mockup, so it's kept untouched.
            img.save(os.path.join(cand_dir, fname))

            # A separate, much smaller copy just for the review-screen grid.
            # Real high-res dielines (some of these PDFs run 20MB+) can render
            # candidate images that are many megapixels — serving those
            # directly as thumbnails is slow and can fail outright on a
            # memory/bandwidth-constrained host. The full-res original above
            # is what's actually used once a slot is picked.
            thumb = img.copy()
            thumb.thumbnail((640, 640), Image.LANCZOS)
            thumb_fname = f"cand_{i}_thumb.jpg"
            thumb.save(os.path.join(cand_dir, thumb_fname), format="JPEG", quality=78)

            cand_meta.append({
                "file": fname,
                "thumb": thumb_fname,
                "label": cand.label,
                "is_guide": cand.is_guide,
                "shape_guess": cand.shape_guess,
                "source": cand.source,
            })
        except Exception:
            # Skip a candidate that fails to save rather than losing the
            # whole batch over one bad image.
            continue

    # Auto-pick a best-guess candidate per slot and build the mockup right
    # away, so staff land on a working 3D preview instead of a blank form —
    # the thumbnail grid is there to swap a panel if the guess is wrong, but
    # picking one manually is no longer required just to see something.
    auto_pick = _auto_pick_files(shape_key, cand_meta)
    default_brief = dict(brief)
    default_brief.update({
        "wrap_offset": 0, "lid_rotation_deg": 90,
        "win_x0": 7, "win_x1": 90, "win_y0": 44, "win_y1": 90,
        "box_depth_ratio": 32,
    })
    try:
        slot_images = {}
        for key, fname in auto_pick.items():
            path = os.path.join(cand_dir, fname)
            slot_images[key] = Image.open(path).convert("RGB")
        if slot_images:
            html = shapes.build_html(shape_key, slot_images, default_brief)
            draft_dir = os.path.join(GENERATED_DIR, "_drafts")
            os.makedirs(draft_dir, exist_ok=True)
            with open(os.path.join(draft_dir, f"{pid}.html"), "w") as f:
                f.write(html)
    except Exception:
        # Auto-preview is a convenience, not a requirement — if it fails for
        # any reason, staff can still pick panels manually on the review
        # screen and generate a preview from there.
        pass

    store.update_product(BASE_DIR, pid, pdf_kind=kind, candidates=cand_meta, auto_pick=auto_pick)
    return redirect(url_for("review", pid=pid))


def _auto_pick_files(shape_key: str, cand_meta: list) -> dict:
    """Best-guess file per slot, using the fact that cand_meta is already
    ordered best-first (extraction sorts candidates by score). This is a
    starting point for the reviewer, not a claim of correctness — packaging
    layouts vary too much to always get this right automatically."""
    if not cand_meta:
        return {}
    files = [c["file"] for c in cand_meta]
    if shape_key == "cylinder":
        cap = next((c["file"] for c in cand_meta if c.get("shape_guess") == "circular"), None)
        wrap = next((c["file"] for c in cand_meta if c["file"] != cap), files[0])
        cap = cap or (files[1] if len(files) > 1 else files[0])
        return {"wrap": wrap, "cap": cap}
    if shape_key == "wedge":
        return {"front": files[0], "back": files[1] if len(files) > 1 else files[0]}
    if shape_key == "box":
        return {
            "front": files[0],
            "back": files[1] if len(files) > 1 else files[0],
            "side": files[2] if len(files) > 2 else files[-1],
        }
    return {}


# ---------------------------------------------------------------------------
# Review: assign candidates to slots, tweak, live preview, publish
# ---------------------------------------------------------------------------

@app.route("/review/<pid>")
@login_required
def review(pid):
    record = store.get_product(BASE_DIR, pid)
    if not record:
        abort(404)
    slots = shapes.SHAPE_TEMPLATES[record["shape"]]["slots"]
    has_draft = os.path.exists(os.path.join(GENERATED_DIR, "_drafts", f"{pid}.html"))
    return render_template(
        "review.html", record=record, slots=slots,
        candidates=record.get("candidates", []),
        auto_pick=record.get("auto_pick", {}),
        has_draft=has_draft,
    )


@app.route("/candidates/<pid>/<fname>")
@login_required
def candidate_image(pid, fname):
    path = os.path.join(UPLOAD_DIR, pid, "candidates", fname)
    if not os.path.exists(path):
        abort(404)
    return send_file(path)


def _apply_adjustments(img: Image.Image, rotate_deg: int, crop: dict) -> Image.Image:
    if rotate_deg:
        img = img.rotate(-rotate_deg, expand=True)
    w, h = img.size
    l = int(w * crop.get("left", 0) / 100)
    r = int(w * (1 - crop.get("right", 0) / 100))
    t = int(h * crop.get("top", 0) / 100)
    b = int(h * (1 - crop.get("bottom", 0) / 100))
    l, t = max(0, l), max(0, t)
    r, b = min(w, r), min(h, b)
    if r - l > 20 and b - t > 20:
        img = img.crop((l, t, r, b))
    return img


def _build_slot_images(record, form) -> dict:
    pid = record["id"]
    slots = shapes.SHAPE_TEMPLATES[record["shape"]]["slots"]
    slot_images = {}
    for slot in slots:
        key = slot["key"]
        fname = form.get(f"slot_{key}_file")
        if not fname:
            raise ValueError(f"No image chosen for slot '{slot['label']}'")
        path = os.path.join(UPLOAD_DIR, pid, "candidates", fname)
        img = Image.open(path).convert("RGB")
        rotate_deg = int(form.get(f"slot_{key}_rotate", 0) or 0)
        crop = {
            "left": float(form.get(f"slot_{key}_crop_left", 0) or 0),
            "right": float(form.get(f"slot_{key}_crop_right", 0) or 0),
            "top": float(form.get(f"slot_{key}_crop_top", 0) or 0),
            "bottom": float(form.get(f"slot_{key}_crop_bottom", 0) or 0),
        }
        slot_images[key] = _apply_adjustments(img, rotate_deg, crop)
    return slot_images


@app.route("/review/<pid>/preview", methods=["POST"])
@login_required
def review_preview(pid):
    record = store.get_product(BASE_DIR, pid)
    if not record:
        abort(404)
    try:
        slot_images = _build_slot_images(record, request.form)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    brief = dict(record["brief"])
    brief["wrap_offset"] = request.form.get("wrap_offset", 0)
    brief["lid_rotation_deg"] = request.form.get("lid_rotation_deg", 90)
    brief["win_x0"] = request.form.get("win_x0", 7)
    brief["win_x1"] = request.form.get("win_x1", 90)
    brief["win_y0"] = request.form.get("win_y0", 44)
    brief["win_y1"] = request.form.get("win_y1", 90)
    brief["box_depth_ratio"] = request.form.get("box_depth_ratio", 32)

    html = shapes.build_html(record["shape"], slot_images, brief)

    out_dir = os.path.join(GENERATED_DIR, "_drafts")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{pid}.html")
    with open(out_path, "w") as f:
        f.write(html)

    store.update_product(BASE_DIR, pid, last_preview_params=dict(request.form))
    return jsonify({"ok": True, "url": url_for("preview_draft", pid=pid)})


@app.route("/preview/<pid>")
@login_required
def preview_draft(pid):
    path = os.path.join(GENERATED_DIR, "_drafts", f"{pid}.html")
    if not os.path.exists(path):
        abort(404)
    return send_file(path)


@app.route("/review/<pid>/publish", methods=["POST"])
@login_required
def publish(pid):
    record = store.get_product(BASE_DIR, pid)
    if not record:
        abort(404)

    draft_path = os.path.join(GENERATED_DIR, "_drafts", f"{pid}.html")
    if not os.path.exists(draft_path):
        flash("Generate a preview before publishing.")
        return redirect(url_for("review", pid=pid))

    brief = record["brief"]
    desired = store.slugify(f"{brief.get('customer','')}-{brief.get('product','')}-{brief.get('die_ref','')}")
    slug = store.unique_slug(BASE_DIR, desired)

    dest_dir = os.path.join(GENERATED_DIR, slug)
    os.makedirs(dest_dir, exist_ok=True)
    with open(draft_path, "r") as f:
        html = f.read()
    with open(os.path.join(dest_dir, "index.html"), "w") as f:
        f.write(html)

    import time
    store.update_product(BASE_DIR, pid, status="published", slug=slug, published_at=time.time())
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Public route — no login. This is the link sent to customers.
# ---------------------------------------------------------------------------

@app.route("/proofs/<slug>")
def public_proof(slug):
    path = os.path.join(GENERATED_DIR, slug, "index.html")
    if not os.path.exists(path):
        abort(404)
    return send_file(path)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
