#!/bin/bash

# ==========================================
# Single Server Deployment Script
# ==========================================
# This script deploys all services on a single server

set -e  # Exit on error

echo "🚀 Starting Single Server Deployment..."
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on the server
if [ ! -d "/opt/sarapps" ]; then
    echo -e "${RED}❌ Error: This script should be run on the production server${NC}"
    echo "Please SSH to your server first: ssh keyadmin@95.142.102.147"
    exit 1
fi

# Navigate to app directory
cd /opt/sarapps

# Check if .env.production exists
if [ ! -f ".env.production" ]; then
    echo -e "${RED}❌ Error: .env.production not found${NC}"
    echo "Please create it from the template:"
    echo "  cp env.production.template .env.production"
    echo "  nano .env.production"
    exit 1
fi

# Check if Firebase credentials exist
if [ ! -f "backend/firebase-admin-key.json" ]; then
    echo -e "${YELLOW}⚠️  Warning: Firebase credentials not found${NC}"
    echo "Make sure to upload backend/firebase-admin-key.json"
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed${NC}"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Error: Docker Compose is not installed${NC}"
    exit 1
fi

# Load environment variables
source .env.production

echo ""
echo "Step 1: Generating SSL certificates (if needed)"
echo "================================================"

if [ ! -f "ssl/cert.pem" ] || [ ! -f "ssl/key.pem" ]; then
    echo -e "${YELLOW}SSL certificates not found. Setting up Let's Encrypt...${NC}"
    
    # Check if domain is configured
    read -p "Enter your domain name (e.g., sarapps.com): " DOMAIN
    read -p "Enter your email for SSL certificate: " EMAIL
    
    # Install certbot if not installed
    if ! command -v certbot &> /dev/null; then
        echo "Installing certbot..."
        sudo apt update
        sudo apt install -y certbot
    fi
    
    # Stop any service on port 80
    echo "Stopping services on port 80..."
    sudo systemctl stop nginx 2>/dev/null || true
    docker-compose down 2>/dev/null || true
    
    # Get certificate
    echo "Obtaining SSL certificate..."
    sudo certbot certonly --standalone \
        -d $DOMAIN \
        -d www.$DOMAIN \
        --agree-tos \
        --email $EMAIL \
        --non-interactive
    
    # Copy certificates
    sudo mkdir -p ssl
    sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem ssl/cert.pem
    sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem ssl/key.pem
    sudo chown -R $USER:$USER ssl
    
    echo -e "${GREEN}✅ SSL certificates generated${NC}"
else
    echo -e "${GREEN}✅ SSL certificates found${NC}"
fi

echo ""
echo "Step 2: Building Docker images"
echo "======================================"

# Build all images
docker-compose build --no-cache

echo -e "${GREEN}✅ Docker images built${NC}"

echo ""
echo "Step 3: Starting services"
echo "======================================"

# Start all services
docker-compose up -d

echo -e "${GREEN}✅ Services started${NC}"

echo ""
echo "Step 4: Waiting for services to be healthy..."
echo "======================================"

# Wait for services to be ready
sleep 10

# Check if services are running
if ! docker ps | grep -q stip_backend; then
    echo -e "${RED}❌ Backend container is not running${NC}"
    docker-compose logs backend
    exit 1
fi

echo -e "${GREEN}✅ All services are running${NC}"

echo ""
echo "Step 5: Initializing database"
echo "======================================"

# Wait a bit more for database to be fully ready
sleep 5

# Initialize database
if docker exec -it stip_backend python scripts/init_db.py; then
    echo -e "${GREEN}✅ Database initialized${NC}"
else
    echo -e "${YELLOW}⚠️  Database initialization failed or already initialized${NC}"
fi

echo ""
echo "Step 6: Verification"
echo "======================================"

# Check backend health
if curl -f http://localhost:5000/api/database/health &>/dev/null; then
    echo -e "${GREEN}✅ Backend API: OK${NC}"
else
    echo -e "${RED}❌ Backend API: FAILED${NC}"
fi

# Check frontend
if curl -f http://localhost:3000 &>/dev/null; then
    echo -e "${GREEN}✅ Frontend: OK${NC}"
else
    echo -e "${RED}❌ Frontend: FAILED${NC}"
fi

# Check admin
if curl -f http://localhost:3001 &>/dev/null; then
    echo -e "${GREEN}✅ Admin Panel: OK${NC}"
else
    echo -e "${RED}❌ Admin Panel: FAILED${NC}"
fi

# Check external access (if domain is configured)
if [ ! -z "$FRONTEND_URL" ]; then
    DOMAIN_CHECK=$(echo $FRONTEND_URL | sed 's/https\?:\/\///')
    echo ""
    echo -e "${YELLOW}Testing external access to $DOMAIN_CHECK...${NC}"
    
    if curl -k -f $FRONTEND_URL/health &>/dev/null; then
        echo -e "${GREEN}✅ External access: OK${NC}"
    else
        echo -e "${YELLOW}⚠️  External access: Not accessible yet${NC}"
        echo "Make sure your domain DNS is configured correctly"
    fi
fi

echo ""
echo "======================================"
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo "======================================"
echo ""
echo "Services are running at:"
echo "  - Frontend: https://$(hostname -I | awk '{print $1}')"
echo "  - Admin: https://$(hostname -I | awk '{print $1}')/admin"
echo "  - API: https://$(hostname -I | awk '{print $1}')/api"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f"
echo ""
echo "To stop services:"
echo "  docker-compose down"
echo ""
echo "To restart services:"
echo "  docker-compose restart"
echo ""

# Show running containers
echo "Running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

