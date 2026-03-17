# Single Domain Deployment Guide

## Architecture Overview

Your application now deploys on **one domain** with path-based routing:

```
https://yourdomain.com/           → User Frontend (Next.js on port 3000)
https://yourdomain.com/admin      → Admin Panel (Next.js on port 3001)
https://yourdomain.com/api        → Backend API (Flask on port 5000)
```

## What Changed

### 1. **nginx.conf** - Single Port (443) Configuration
- ✅ Removed separate port 8443 server block
- ✅ Added `/admin` location routing to admin container
- ✅ Added URL rewriting: `/admin/path` → `/path` for admin app
- ✅ Static file caching for `/_next/static/` assets

### 2. **Hardcoded URLs Fixed**
All `http://localhost:5000` replaced with relative paths:

**Frontend:**
- `frontend/lib/api.js`: API_BASE_URL now `/api` 
- `frontend/components/Header.jsx`: Image URLs use `/api`

**Admin:**
- `admin/lib/api.js`: API_BASE_URL now `/api`
- `admin/lib/store.js`: Auth URLs use `/api`
- `admin/app/users/page.jsx`: Image paths relative
- `admin/app/groups/page.jsx`: Image paths relative

### 3. **Environment Variables**
Created `.env.production` template for deployment settings

## Deployment Steps

### Local Testing

1. **Update Docker Compose** (if using containers):
```bash
# Ensure ports are exposed correctly
docker-compose up --build
```

2. **Test Routes:**
```bash
# User frontend
curl http://localhost/

# Admin panel
curl http://localhost/admin

# API
curl http://localhost/api/health
```

### Production Deployment

1. **Copy environment template:**
```bash
cp .env.production .env.local
```

2. **Update `.env.local` with real values:**
- Change `DB_PASSWORD` 
- Set `SECRET_KEY` and `JWT_SECRET_KEY`
- Update `FRONTEND_URL` to your domain
- Set `CORS_ORIGINS` to your domain

3. **Build production images:**
```bash
# Backend
cd backend
docker build -t stip-backend:prod .

# Frontend
cd ../frontend
npm run build

# Admin
cd ../admin
npm run build
```

4. **Deploy with Docker Compose:**
```bash
docker-compose -f docker-compose.yml up -d
```

5. **Verify SSL certificates** in `/etc/nginx/ssl/`:
```bash
# Check certificate
openssl x509 -in /etc/nginx/ssl/cert.pem -text -noout

# Ensure private key matches
openssl rsa -in /etc/nginx/ssl/key.pem -check
```

## DNS Configuration

Point your domain to your server:

```
A Record: yourdomain.com → Your_Server_IP
```

**No subdomains needed!** Everything is on one domain.

## Routing Logic

### Nginx Path Priority (Order Matters)

1. **`/api/auth/`** → Backend (strict rate limit: 5 req/min)
2. **`/api/`** → Backend (normal rate limit: 200 req/burst)
3. **`/admin/_next/static/`** → Admin static assets (cached 1 year)
4. **`/admin`** → Admin panel (rewritten to `/` for admin container)
5. **`/`** → User frontend (default fallback)

### How Rewriting Works

```
User Request: https://yourdomain.com/admin/users
     ↓
Nginx matches: location /admin { rewrite ^/admin(/.*)$ $1 break; }
     ↓
Proxy passes to: http://admin:3001/users
     ↓
Admin Next.js serves: /users route
```

## Important Notes

### Current Limitations

⚠️ **Admin routing works with nginx rewrite**, but Next.js doesn't know it's under `/admin`. This means:

- Links like `<Link href="/users">` in admin will navigate to `yourdomain.com/users` (frontend)
- Should be `<Link href="/admin/users">` 

### Solution Options

**Option A: Keep Current Setup (Simpler)**
- Update all `<Link>` components in admin to include `/admin` prefix
- Example: `<Link href="/admin/crawlers">`, `<Link href="/admin/users">`

**Option B: Use Next.js basePath (Better)**
1. Create `admin/next.config.js`:
```javascript
module.exports = {
  basePath: '/admin',
  assetPrefix: '/admin',
}
```

2. Update nginx to remove rewrite:
```nginx
location /admin {
    proxy_pass http://admin;  # No rewrite needed
}
```

3. No link changes needed - Next.js handles paths automatically

**Recommendation:** Use **Option B** if you have many internal links in admin.

## Security Checklist Before Production

- [ ] Change `SECRET_KEY` in backend config
- [ ] Change `JWT_SECRET_KEY` 
- [ ] Set `CORS_ORIGINS` to your domain (not `*`)
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Set strong `DB_PASSWORD`
- [ ] Review and enable rate limiting
- [ ] Set up firewall rules (close unnecessary ports)
- [ ] Enable logging and monitoring

## Troubleshooting

### Admin Panel Shows 404
- Check nginx logs: `docker logs nginx`
- Verify admin container is running: `docker ps`
- Test direct access: `curl http://admin:3001/` (inside Docker network)

### API Calls Fail
- Check backend logs: `docker logs stip_backend`
- Verify CORS settings in `backend/core/config/config.py`
- Test API directly: `curl http://localhost/api/health`

### Static Assets Not Loading
- Check browser console for 404s
- Verify paths in Network tab (should start with `/_next/`)
- Clear browser cache: Ctrl+Shift+Delete

### Login Redirects to Wrong Page
- Admin links should use `/admin/login`, not `/login`
- Check redirect URLs in auth logic
- Update `redirect_uri` in OAuth flows if applicable

## Performance Optimization

After deployment, implement the **pgvector solution** from `PRODUCTION_READINESS_REPORT.md`:

```bash
# Run migrations to add vector columns
psql -U stip_user -d stip_production -f database/migrations/add_vector_columns.sql

# Backfill existing data
python backend/database/scripts/backfill_vectors.py

# Monitor performance
# Before: 30-60s for 1000 images
# After: 200-500ms for 10,000 images
```

## Next Steps

1. ✅ nginx configured for single domain
2. ✅ Hardcoded URLs fixed
3. ⏳ **Choose routing approach** (rewrite vs basePath)
4. ⏳ Update admin links if using rewrite approach
5. ⏳ Test locally with docker-compose
6. ⏳ Deploy to production server
7. ⏳ Implement pgvector for performance

## Support

Refer to:
- `PRODUCTION_READINESS_REPORT.md` - Performance optimization
- `QUICK_START_GUIDE.md` - Development setup
- nginx logs: `/var/log/nginx/access.log` and `error.log`
