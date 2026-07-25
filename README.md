# S&G 3D Proof Tool (MVP)

Internal tool: a staff member uploads a customer brief + high-res packaging
PDF, the system auto-extracts the print artwork, staff do a quick review
(assign artwork to the packaging's faces, nudge a couple of placement
controls, preview it live), then publish — which produces a link like:

```
https://your-domain.com/proofs/in2-food-large-sandwich-wedge-i2f-135
```

That link is a single self-contained HTML page (drag to rotate, a lighting
tool, matte paper-like material) — the customer just opens it in a browser.
No plugins, no Acrobat, nothing to install on their end.

This was built and tested against real files: a cylindrical tub (Purina Pro
Plan), a die-cut triangular sandwich wedge with an embedded 3D proof
(Esko/ArtiosCAD U3D), and a rectangular folding carton. All three are
supported "shape templates" out of the box.

**On messy/rotated dielines:** real bureau sheets vary a lot — some print the
die shape rotated on the page, or as one connected ink block across every
panel/flap rather than neatly separated rectangles. When automatic panel
detection can't make sense of a layout like that, every extraction always
includes the untouched full page as a fallback candidate — pick that and use
the Rotate/Trim controls on the review screen to manually straighten and crop
out the panel you need. It's slower than automatic detection but it always
works, whatever the layout.

## What's genuinely automatic vs. what needs a human

Being upfront about this because it matters for how you use the tool day to
day:

- **Automatic:** rendering the PDF, finding distinct artwork panels on the
  page (or pulling the embedded textures straight out of a U3D 3D proof),
  and assembling the final interactive 3D file once you've told it which
  image goes where.
- **Needs a person (the "review" step):** picking *which* extracted image is
  the clean front panel vs. a dieline/registration-mark version, whether
  anything needs rotating, and where a die-cut window sits. Packaging
  artwork varies too much between customers and dielines for a program to
  guess this with full confidence — a human doing it takes about 30 seconds
  per product once you're used to the screen, and it's far more reliable
  than false automation would be.

## Running it locally

```bash
cd sg3d
pip install -r requirements.txt
sudo apt-get install poppler-utils   # provides pdftoppm, used to render PDF pages

export SG_ADMIN_PASSWORD="pick-something"
export SG_SECRET_KEY="pick-a-random-string"
python app.py
```

Open `http://localhost:5000`, log in with `SG_ADMIN_PASSWORD`.

## Deploying on S&G's server

This is a normal Flask app — any of these work:

1. **Simplest:** `gunicorn -w 2 -b 0.0.0.0:8000 app:app` behind your existing
   nginx/Apache reverse proxy, with `SG_ADMIN_PASSWORD` / `SG_SECRET_KEY`
   set as real environment variables (not the dev defaults).
2. Put it behind your existing login/VPN if you'd rather not expose even
   the login page publicly — only the `/proofs/<slug>` routes need to be
   reachable by customers.
3. `generated/<slug>/index.html` is a completely static file per product.
   If you'd rather not run Flask in production at all, you could instead
   run this tool only on a staff laptop/internal server, and have it drop
   the published files into whatever already serves your public site
   (S3 bucket, existing CMS, etc.) — the `publish()` function in `app.py`
   is the one place that would need a few lines changed to copy the file
   somewhere else instead of `generated/`.

### Data & files

- `data/products.json` — every product record (JSON file, no database
  server needed). Fine for the volumes this kind of tool sees; swap for
  SQLite later if it ever needs to (the whole read/write surface is in
  `pipeline/store.py`).
- `uploads/<product-id>/` — the original PDF + extracted candidate images.
  Keep or prune periodically; not customer-facing.
- `generated/<slug>/index.html` — the published, customer-facing mockup.
  This is the only folder that needs to be reachable by customers.

**Before going live:** `data/products.json` is already reset to
`{"products": {}}`, but `uploads/` and `generated/` still have a handful of
orphaned test files left over from building/testing this (they won't show
up anywhere in the UI since the dashboard only reads `products.json` —
they're just disk clutter). Feel free to `rm -rf` the contents of both
folders before your first real upload.

## How a product moves through the tool

1. **New Product** — brief (customer, product, die ref, notes) + PDF +
   pick a packaging shape template.
2. The PDF is auto-detected as either a **flat artwork PDF** (renders pages,
   slices out the distinct panels) or a **U3D 3D-proof PDF** (Esko-style —
   pulls the real print textures straight out of the embedded 3D model,
   which is usually much higher quality than re-rendering the 3D view).
3. **Review** — every extracted image shows up as a thumbnail. For each
   face the shape needs (e.g. "wraparound label" + "lid" for a tub), pick
   the right thumbnail, rotate if needed, trim off anything you don't want
   (like a dieline's registration marks, or an unrelated corner of a texture
   atlas). Shape-specific controls (wrap seam position, window placement,
   etc.) are also here.
4. **Generate Preview** — builds the actual interactive 3D file and shows it
   live in an iframe right there. Repeat step 3/4 until it looks right.
5. **Publish** — copies that file to a permanent slugged URL and shows it on
   the dashboard.

## Adding a new packaging shape template

Everything for a shape lives in `pipeline/shapes.py`:

1. Add an entry to `SHAPE_TEMPLATES` with a `label` and the `slots` (which
   artwork panels a person needs to supply — keep this to 2-3 for a good
   review-screen experience).
2. Write a `_build_<shape>(slot_images, brief)` function that returns a
   complete HTML string. Easiest path: copy the `_build_wedge` /
   `_build_cylinder` function and its `_HTML` template as a starting point
   and change the Three.js geometry — the lighting tool, drag-to-rotate,
   paper material and loading screen are all copy-paste reusable.
3. Nothing else needs to change — the review screen, upload form, and
   publish flow all read `SHAPE_TEMPLATES` generically.

Reasonable next candidates: a rectangular carton/box (6 faces), a pouch
(front + back, roughly flat), a bottle (wrap label + a separate cap).

## Known limitations (v1)

- Crop controls in the review screen are simple % trims from each edge, not
  a drag-corner visual tool. Works fine in testing but a proper interactive
  crop (drag handles on the thumbnail) would be a nice v2.
- Auto-extraction is a good starting point, not a guarantee — always look
  at the live preview before publishing.
- Single shared staff password, no per-user accounts/audit log. Fine for a
  small team; worth adding real auth (or piggybacking on existing company
  SSO) if more people start using it.
- Tested against 2 real S&G PDFs end-to-end (both packaging shapes covered
  above). Odd/unusual dielines will probably need small tweaks to the
  extraction heuristics in `pipeline/extract.py` the first time they show
  up — that file has comments explaining each heuristic and why it's
  intentionally conservative.
