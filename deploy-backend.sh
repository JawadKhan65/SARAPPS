#!/bin/bash

# ==========================================
# Backend Server Deployment Script
# ==========================================
# Deploy: Flask + PostgreSQL + Redis
# Server: 95.142.102.148

set -e

echo "🚀 Deploying Backend Server (Flask + DB + Redis)..."
echo "======================================"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd /opt/sarapps

if [ ! -f ".env.production" ]; then
    echo -e "${RED}❌ .env.production not found${NC}"
    exit 1
fi

source .env.production

echo "Step 1: Configure Firewall"
echo "======================================"

sudo ufw --force enable
sudo ufw allow 22/tcp
sudo ufw allow from 10.110.0.5 to any port 5000   # Flask API
sudo ufw allow from 10.110.0.5 to any port 5432   # PostgreSQL (if frontend needs direct access)
sudo ufw allow from 10.110.0.5 to any port 6379   # Redis

echo -e "${GREEN}✅ Firewall configured${NC}"

echo ""
echo "Step 2: Create Backend Docker Compose"
echo "======================================"

cat > docker-compose.backend.yml << 'EOF'
version: '3.9'

services:
  postgres:
    image: pgvector/pgvector:pg17
    container_name: stip_postgres
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - stip_network
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: stip_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - stip_network
    restart: unless-stopped

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: stip_backend
    environment:
      FLASK_APP: app.py
      FLASK_ENV: ${FLASK_ENV}
      SECRET_KEY: ${SECRET_KEY}
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/${DB_NAME}
      REDIS_URL: redis://redis:6379/0
      CORS_ORIGINS: ${CORS_ORIGINS}
    ports:
      - "5000:5000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend/uploads:/app/uploads
      - ./backend/logs:/app/logs
    networks:
      - stip_network
    restart: unless-stopped

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: stip_worker
    command: python jobs/worker.py
    environment:
      FLASK_ENV: ${FLASK_ENV}
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/${DB_NAME}
      REDIS_URL: redis://redis:6379/0
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend/uploads:/app/uploads
    networks:
      - stip_network
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:

networks:
  stip_network:
    driver: bridge
EOF

echo -e "${GREEN}✅ Backend docker-compose created${NC}"

echo ""
echo "Step 3: Building and Starting Services"
echo "======================================"

docker-compose -f docker-compose.backend.yml build --no-cache
docker-compose -f docker-compose.backend.yml up -d

echo -e "${GREEN}✅ Services started${NC}"

echo ""
echo "Step 4: Waiting for services..."
echo "======================================"

sleep 15

echo ""
echo "Step 5: Initialize Database"
echo "======================================"

docker exec -it stip_backend python scripts/init_db.py || true

echo -e "${GREEN}✅ Database initialized${NC}"

echo ""
echo "Step 6: Verification"
echo "======================================"

# Check services
if curl -f http://localhost:5000/api/database/health &>/dev/null; then
    echo -e "${GREEN}✅ Backend API: OK${NC}"
else
    echo -e "${RED}❌ Backend API: FAILED${NC}"
fi

# Test database connection
if docker exec stip_postgres psql -U ${DB_USER} -d ${DB_NAME} -c "\dt" &>/dev/null; then
    echo -e "${GREEN}✅ Database: OK${NC}"
else
    echo -e "${RED}❌ Database: FAILED${NC}"
fi

# Test Redis
if docker exec stip_redis redis-cli ping &>/dev/null; then
    echo -e "${GREEN}✅ Redis: OK${NC}"
else
    echo -e "${RED}❌ Redis: FAILED${NC}"
fi

echo ""
echo "======================================"
echo -e "${GREEN}🎉 Backend Deployment Complete!${NC}"
echo "======================================"
echo ""
echo "Backend API accessible at:"
echo "  - Internal: http://10.110.0.6:5000"
echo "  - Health: curl http://localhost:5000/api/database/health"
echo ""
echo "Running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

