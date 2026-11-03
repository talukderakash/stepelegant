# Step Elegant V3 — Render + Neon + Cloudinary

এই ভার্সনটি বর্তমান Flask স্টোরফ্রন্ট এবং অ্যাডমিন প্যানেল রেখেই PostgreSQL ও Cloudinary সমর্থন যোগ করেছে।

## Free service সতর্কতা
Render Free idle হলে sleep হয় এবং production-এর জন্য recommended নয়। Neon Free ও Cloudinary Free-তেও quota আছে। Payment integration নেই। বাস্তব অর্ডারের জন্য নিয়মিত PostgreSQL backup এবং Cloudinary export প্রয়োজন।

## 1. Account
- GitHub: https://github.com
- Neon Postgres: https://neon.tech (Create project > copy pooled connection URL with sslmode=require)
- Cloudinary: https://cloudinary.com (copy CLOUDINARY_URL credentials; do not commit keys)
- Render: https://render.com

## 2. GitHub upload
ZIP extract করে VS Code terminal থেকে:
```
git init
git add .
git commit -m "Step Elegant cloud version"
```
GitHub-এ PRIVATE empty repository তৈরি করে সেখানে push করুন (GitHub displayed commands অনুসরণ করুন)। `.env` বা database কখনো push করবেন না।

## 3. Render deployment
Render > New > Blueprint > GitHub repo select > render.yaml detected > deploy. Environment variables এ DATABASE_URL, CLOUDINARY_URL, ADMIN_EMAIL, ADMIN_PASSWORD set করুন। SECRET_KEY autogenerate হবে। Render service URL আসবে।

DATABASE_URL must be a Neon PostgreSQL URI, e.g. `postgresql://USER:PASS@HOST/DB?sslmode=require` (sample only). Cloudinary URL format: `cloudinary://API_KEY:API_SECRET@CLOUD_NAME` (sample only).

start.sh automatically runs init-db and creates admin *only if absent*. Do not use seed-demo for production.

Customer: `https://YOUR-RENDER-SERVICE.onrender.com/`
Admin: `https://YOUR-RENDER-SERVICE.onrender.com/admin`

## 4. Local run
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env secure values
python -m flask --app app init-db
python -m flask --app app create-admin
python app.py
```

## Notes
- New uploaded image/video links are persisted as secure Cloudinary URLs in Postgres.
- Existing local `uploads/` links do not magically migrate; export and re-upload old media before switching hosting.
- 1–5 images / 0–2 videos per product; sizes 5 MB/image and 40 MB/video.
- Third-party storage charges/quotas can change; videos can exhaust free credits quickly.
- Admin credentials can be created on first deploy, changing ADMIN_PASSWORD later does not reset existing user password.
- Do not expose .env in Git. Server secrets are set in Render environment settings.
- Production hardening still needed: reliable backups, monitoring, rate limiting, transactional stock locking, privacy/returns policies, customer notifications, email configuration and full functional testing.
