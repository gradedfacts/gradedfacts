# Deploying GradedFacts on Infomaniak

Infomaniak Cloud hosting (Jelastic) runs containerised Python apps. These steps
assume a **Python + Nginx** topology in the Jelastic dashboard.

---

## 1. Python version

GradedFacts requires **Python 3.12**.

In the Jelastic environment wizard, choose:
- Application server: **Python 3.12** (Apache + mod_wsgi or Nginx + Gunicorn node)
- Or use a **Docker** container with `python:3.12-slim` if you prefer full control.

---

## 2. Upload the application

```bash
# From your local machine, zip the repo (excluding venv and local DB)
git archive --format=zip HEAD -o gradedfacts.zip

# Upload via the Jelastic file manager, or deploy via Git:
# Dashboard → Deployment Manager → Add Repo → paste your Git URL
```

---

## 3. Install dependencies

In the Jelastic SSH terminal for the Python node:

```bash
cd /var/www/webroot/ROOT   # default app root in Jelastic
pip install -r requirements.txt
```

---

## 4. Set environment variables

In the Jelastic dashboard: **your environment → Settings → Variables**

| Variable | Value |
|---|---|
| `DATABASE_URL` | `sqlite:///./gradedfacts.db` |
| `ANTHROPIC_API_KEY` | your live key from console.anthropic.com |
| `RATE_LIMIT_ENABLED` | `true` |
| `ENVIRONMENT` | `production` |
| `PORT` | `8000` (set automatically by Jelastic; override only if needed) |

Variables are injected at runtime — never commit secrets to the repository.

---

## 5. Configure the process

Jelastic reads the `Procfile` at the application root:

```
web: uvicorn backend.api:app --host 0.0.0.0 --port $PORT
```

If your Jelastic topology uses a **startup script** instead of Procfile, create
`/var/www/webroot/ROOT/start.sh`:

```bash
#!/bin/bash
exec uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-8000}
```

```bash
chmod +x start.sh
```

Then point the Jelastic "entry point" field to `start.sh`.

---

## 6. Point gradedfacts.com to the server

### A. Get the Jelastic public IP

Dashboard → your environment → **Public IP** → copy the IPv4 address.

(Public IPs are available on paid Jelastic plans; enable it under the load
balancer or application node settings.)

### B. DNS records at your domain registrar

Add the following records for **gradedfacts.com**:

| Type | Name | Value | TTL |
|---|---|---|---|
| `A` | `@` | `<Jelastic public IP>` | 300 |
| `A` | `www` | `<Jelastic public IP>` | 300 |
| `CNAME` | `www` | `gradedfacts.com.` | 300 |

Use only one of the `A` or `CNAME` for `www`, not both.

Infomaniak also offers **domain + DNS management** in their panel
(manager.infomaniak.com → Domaines). If gradedfacts.com is registered through
Infomaniak, set the DNS zone there directly.

Propagation typically takes 5–30 minutes.

---

## 7. SSL / HTTPS

### Option A — Jelastic built-in Let's Encrypt (recommended)

1. Dashboard → your environment → **Add-ons** → search **Let's Encrypt**
2. Install → enter `gradedfacts.com` and `www.gradedfacts.com`
3. Jelastic handles certificate issuance and automatic renewal.

### Option B — Infomaniak SSL certificate

If you purchased an Infomaniak SSL certificate:

1. manager.infomaniak.com → SSL/TLS → download the certificate bundle (`.crt`
   + intermediate + `.key`)
2. Jelastic → your environment → SSL → **Custom SSL** → upload the files.

### Force HTTPS

Add to the Nginx configuration (Jelastic → your Nginx node → conf → nginx.conf):

```nginx
server {
    listen 80;
    server_name gradedfacts.com www.gradedfacts.com;
    return 301 https://$host$request_uri;
}
```

---

## 8. Verify the deployment

```bash
curl -I https://gradedfacts.com/
# Expect: HTTP/2 200

curl https://gradedfacts.com/docs
# Expect: FastAPI OpenAPI UI
```

---

## 9. Persistent database

SQLite writes to the local filesystem. In Jelastic, the app node filesystem is
persistent across restarts **within the same environment**, but not across
redeployments that reset the root.

For a zero-data-loss setup before switching to PostgreSQL:

- Mount a **Jelastic Shared Storage** volume at `/var/www/webroot/ROOT/data/`
- Set `DATABASE_URL=sqlite:////var/www/webroot/ROOT/data/gradedfacts.db`

PostgreSQL migration is planned for Phase 2.

---

## 10. Logs

```bash
# SSH into the Python node:
tail -f /var/log/run.log

# Or stream via Jelastic dashboard → Log → run.log
```
