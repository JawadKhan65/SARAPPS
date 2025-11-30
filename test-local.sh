#!/bin/bash

# ==========================================
# Local Testing Script
# ==========================================
# Test the application locally before deploying

set -e

echo "🧪 Testing Application Locally..."
echo "======================================"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running${NC}"
    echo "Please start Docker Desktop first"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"

# Check if required files exist
echo ""
echo "Checking required files..."
echo "======================================"

required_files=(
    "backend/Dockerfile"
    "backend/app.py"
    "backend/requirements.txt"
    "frontend/Dockerfile"
    "frontend/package.json"
    "admin/Dockerfile"
    "admin/package.json"
    "docker-compose.yml"
    "nginx.conf"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅${NC} $file"
    else
        echo -e "${RED}❌${NC} $file (missing)"
        exit 1
    fi
done

# Check if Firebase credentials exist
if [ ! -f "backend/firebase-admin-key.json" ]; then
    echo -e "${YELLOW}⚠️  Warning: backend/firebase-admin-key.json not found${NC}"
    echo "Firebase authentication may not work without this file"
fi

# Create local environment file if it doesn't exist
if [ ! -f ".env.local" ]; then
    echo ""
    echo "Creating .env.local file..."
    cat > .env.local << 'EOF'
# Local Testing Environment
FLASK_ENV=development
DB_PASSWORD=test_password_123
SECRET_KEY=dev_secret_key_not_for_production
JWT_SECRET_KEY=dev_jwt_secret_key_not_for_production
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost,http://localhost:443
NEXT_PUBLIC_API_URL=http://localhost/api
REACT_APP_API_URL=http://localhost/api
FRONTEND_URL=http://localhost
EOF
    echo -e "${GREEN}✅ Created .env.local${NC}"
fi

# Create self-signed SSL certificates for local testing
if [ ! -f "ssl/cert.pem" ] || [ ! -f "ssl/key.pem" ]; then
    echo ""
    echo "Creating self-signed SSL certificates for local testing..."
    mkdir -p ssl
    
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout ssl/key.pem \
        -out ssl/cert.pem \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost" \
        2>/dev/null
    
    echo -e "${GREEN}✅ SSL certificates created${NC}"
fi

# Stop any existing containers
echo ""
echo "Stopping existing containers..."
docker-compose down 2>/dev/null || true

# Build and start services
echo ""
echo "Building Docker images..."
echo "======================================"
echo -e "${YELLOW}This may take 5-10 minutes on first run...${NC}"

if docker-compose build; then
    echo -e "${GREEN}✅ Images built successfully${NC}"
else
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

echo ""
echo "Starting services..."
echo "======================================"

# Use .env.local for environment
export $(cat .env.local | grep -v '^#' | xargs)

if docker-compose up -d; then
    echo -e "${GREEN}✅ Services started${NC}"
else
    echo -e "${RED}❌ Failed to start services${NC}"
    docker-compose logs
    exit 1
fi

echo ""
echo "Waiting for services to be ready..."
echo "======================================"

# Wait for services
sleep 20

# Check each service
services_ok=true

echo ""
echo "Testing services..."
echo "======================================"

# Check PostgreSQL
if docker exec stip_postgres pg_isready -U stip_user > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} PostgreSQL"
else
    echo -e "${RED}❌${NC} PostgreSQL"
    services_ok=false
fi

# Check Redis
if docker exec stip_redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Redis"
else
    echo -e "${RED}❌${NC} Redis"
    services_ok=false
fi

# Check Backend
if curl -f http://localhost:5000/api/database/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Backend API (http://localhost:5000)"
else
    echo -e "${RED}❌${NC} Backend API"
    services_ok=false
fi

# Check Frontend
if curl -f http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Frontend (http://localhost:3000)"
else
    echo -e "${RED}❌${NC} Frontend"
    services_ok=false
fi

# Check Admin
if curl -f http://localhost:3001 > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Admin Panel (http://localhost:3001)"
else
    echo -e "${RED}❌${NC} Admin Panel"
    services_ok=false
fi

# Check Nginx
if curl -k -f https://localhost/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Nginx (https://localhost)"
else
    echo -e "${YELLOW}⚠️${NC}  Nginx (https://localhost) - may take a moment"
fi

echo ""
echo "======================================"

if [ "$services_ok" = true ]; then
    echo -e "${GREEN}🎉 All services are running!${NC}"
    echo ""
    echo "Access your application:"
    echo "  - Frontend:    http://localhost:3000"
    echo "  - Admin Panel: http://localhost:3001"
    echo "  - Backend API: http://localhost:5000"
    echo "  - Via Nginx:   https://localhost (⚠️  ignore SSL warning)"
    echo ""
    echo "Useful commands:"
    echo "  - View logs:        docker-compose logs -f"
    echo "  - Stop services:    docker-compose down"
    echo "  - Restart services: docker-compose restart"
    echo ""
    echo "Running containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
else
    echo -e "${RED}❌ Some services failed to start${NC}"
    echo ""
    echo "Check logs with:"
    echo "  docker-compose logs"
    echo ""
    echo "Or for specific service:"
    echo "  docker logs stip_backend"
    echo "  docker logs stip_frontend"
    echo "  docker logs stip_admin"
    exit 1
fi

# Initialize database
echo ""
echo "Initializing database..."
echo "======================================"

sleep 5  # Wait a bit more for backend to be fully ready

if docker exec -it stip_backend python scripts/init_db.py 2>/dev/null; then
    echo -e "${GREEN}✅ Database initialized${NC}"
else
    echo -e "${YELLOW}⚠️  Database initialization skipped or already done${NC}"
fi

echo ""
echo "======================================"
echo -e "${GREEN}✨ Local testing environment is ready!${NC}"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Open http://localhost:3000 in your browser"
echo "2. Test the application functionality"
echo "3. If everything works, proceed with production deployment"
echo ""
echo "To view real-time logs:"
echo "  docker-compose logs -f"
echo ""

