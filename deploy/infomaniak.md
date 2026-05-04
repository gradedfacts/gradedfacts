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
| `DATABASE_URL` | `postgresql://gradedfacts:<password>@<pg-host>:5432/gradedfacts` (see section 9) |
| `ANTHROPIC_API_KEY` | your live key from console.anthropic.com |
| `MISTRAL_API_KEY` | your live key from console.mistral.ai |
| `BRAVE_API_KEY` | your live key from brave.com/search/api |
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

## 9. PostgreSQL database

GradedFacts uses PostgreSQL in production. The Jelastic topology should include
a dedicated **PostgreSQL** node alongside the Python application node.

### A. Add the PostgreSQL node

1. Jelastic dashboard → your environment → **Change topology**
2. Under **SQL**, add **PostgreSQL 16** (or latest available)
3. Set the node resources (256 MB RAM / 1 cloudlet is sufficient for initial load)
4. Click **Apply** — Jelastic provisions the node and prints the root credentials

### B. Create the application database and user

SSH into the PostgreSQL node (Jelastic → PostgreSQL node → **Web SSH**), then:

```sql
psql -U webadmin postgres

CREATE DATABASE gradedfacts;
CREATE USER gradedfacts WITH PASSWORD 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON DATABASE gradedfacts TO gradedfacts;
-- PostgreSQL 15+ also requires:
\c gradedfacts
GRANT ALL ON SCHEMA public TO gradedfacts;
\q
```

### C. Get the connection string

The PostgreSQL node's internal hostname is shown in the Jelastic dashboard under
the node tile (e.g. `node12345-env-name.jelastic.infomaniak.com`). Use the
**internal hostname** (not the public one) so traffic stays within the Jelastic
private network:

```
postgresql://gradedfacts:<password>@<internal-pg-host>:5432/gradedfacts
```

Set this as the `DATABASE_URL` environment variable (see section 4).

Both `postgres://` and `postgresql://` schemes are accepted — the application
normalises `postgres://` to `postgresql://` automatically.

### D. Initialise the schema

On the Python application node, run the Alembic migration to create the tables:

```bash
cd /var/www/webroot/ROOT
alembic upgrade head
```

This is a one-time step on a fresh database. Re-deployments are safe to run
`alembic upgrade head` again — it is idempotent.

### E. Verify the connection

```bash
python -c "from backend.db.session import engine; print(engine.url)"
# Should print: postgresql://gradedfacts:***@<host>:5432/gradedfacts
```

---

## 10. Logs

```bash
# SSH into the Python node:
tail -f /var/log/run.log

# Or stream via Jelastic dashboard → Log → run.log
```
