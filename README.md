# STEP ELEGANT — Complete Shoe Store (Flask)

A responsive shoe-store starter with a customer storefront, SQLite backend, secure staff login, product inventory management, product photo uploads, shopping bag and an order-request checkout.

## Fresh install on Mac (delete the old project first)

**Warning:** Removing the old folder permanently removes its local database, orders, uploaded files and admin login. If you want any of those, keep a backup.

1. Stop the previous Flask server in the VS Code terminal using Ctrl+C.
2. Delete your previous project folder and extract this ZIP.
3. Open the extracted `step-elegant-complete` folder in VS Code, choose Terminal → New Terminal.
4. Run these commands:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

**Before continuing:** Open `.env` in VS Code and replace `SECRET_KEY` with a long random value, and `ADMIN_EMAIL` and `ADMIN_PASSWORD` with your own credentials (at least 12 characters for the password). Then run:

```bash
python -m flask --app app init-db
python -m flask --app app create-admin
python -m flask --app app seed-demo
python app.py
```

Storefront: http://127.0.0.1:5000/ — Admin: http://127.0.0.1:5000/admin

For subsequent starts, use `source .venv/bin/activate` followed by `python app.py`.

**Product media limits:** Each product needs 1–5 images and can have 0–2 videos, uploaded through the admin product form. Demo products start without real product photos: edit each product and upload at least one photo before expecting it to display a full product gallery.

## Features
- Landing page, category browsing, text search and price sorting
- Product detail pages, sizes, stock-aware shopping cart
- Customer contact / delivery checkout (orders recorded in SQLite)
- Protected `/admin` dashboard, product add/edit/delete, photo upload, stock counts, order detail/status
- CSRF-protected forms and hashed administrator passwords
- Lightweight design, mobile-friendly layout

**Important:** This is an order-request workflow; it does **not** accept online payments, calculate shipping/taxes, email notifications, or automatically refund/restock cancelled orders. Add those integrations before advertising full online payment services. Prices shown in USD are demonstration values.

## Windows PowerShell quick start
```powershell
cd step-elegant-complete
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# EDIT .env to choose a new SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
.\.venv\Scripts\python.exe -m flask --app app init-db
.\.venv\Scripts\python.exe -m flask --app app create-admin
.\.venv\Scripts\python.exe -m flask --app app seed-demo
.\.venv\Scripts\python.exe app.py
```
Then open `http://127.0.0.1:5000/` and the admin at `http://127.0.0.1:5000/admin`.

## macOS / Linux quick start
```bash
cd step-elegant-complete
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# EDIT .env before creating admin
.venv/bin/python -m flask --app app init-db
.venv/bin/python -m flask --app app create-admin
.venv/bin/python -m flask --app app seed-demo
.venv/bin/python app.py
```

## How to manage the store
1. Sign in at `/admin/login` with email and password configured in `.env`.
2. Use **Products → Add Product** to upload your shoe photos and enter available sizes, pricing, and stock.
3. Use **Orders** to view incoming customer requests and manage their progress.
4. Edit `templates/contact.html`, `templates/about.html`, and `templates/base.html` to add your real business details.
5. Hero and category images currently use Unsplash URLs, so replace these with licensed brand images before launch; the product placeholders are intentional until you upload your actual inventory.

## Free hosting and production notes
Many free hosts have **ephemeral filesystems**, meaning SQLite databases and uploaded images may disappear after a restart or deployment. For production, deploy with a persistent volume or managed database (such as PostgreSQL), move uploads to durable object storage, configure HTTPS and `COOKIE_SECURE=1`, set a long random `SECRET_KEY`, and run a production WSGI server (for example Gunicorn on Linux). Never deploy with Flask debug mode or the demo credentials.

Validation note: source files were syntax-checked, but a live Flask test could not run in the packaging environment because dependencies could not be downloaded.

This is a custom original layout **inspired by modern shoe-shop websites**, not a copyrighted source-code copy of another store.


## Gallery upgrade (v2): 1–5 images and 0–2 videos per product

Each new product requires 1–5 JPG/PNG/WebP images (5 MB maximum each), with optional 0–2 MP4/WebM videos (40 MB maximum each). The customer product page displays clickable thumbnails and plays videos using browser controls. Admin > Products > Add/Edit supports selecting multiple files and removing existing gallery files. Removed file records are deleted from the database; underlying uploads are retained to protect references and avoid unsafe deletions. The overall upload request limit is 110 MB. Upload files only from trusted staff.

**Updating an existing installation:** Replace the app.py, templates and static files with these versions. **Keep your existing `.env`, `step_elegant.db`, and `static/uploads` directory.** Back up your database first. Stop the server, then run `python -m flask --app app init-db` to create the new `product_media` table without clearing existing data. Restart with `python app.py`. The old single product images remain supported. For existing demo items without photos, upload at least one when editing them.

For production deployment, configure persistent media storage and a reverse proxy upload limit; the Flask development server is not production hosting.
