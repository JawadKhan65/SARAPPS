#!/bin/bash

# ==========================================
# Frontend Server Deployment Script
# ==========================================
# Deploy: Next.js Frontend + Next.js Admin + Nginx
# Server: 95.142.102.147

set -e

echo "🚀 Deploying Frontend Server (Frontend + Admin + Nginx)..."
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
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

echo -e "${GREEN}✅ Firewall configured${NC}"

echo ""
echo "Step 2: SSL Certificates"
echo "======================================"

if [ ! -f "ssl/cert.pem" ] || [ ! -f "ssl/key.pem" ]; then
    echo -e "${YELLOW}Setting up SSL certificates...${NC}"
    
    read -p "Enter your domain name (e.g., sarapps.com): " DOMAIN
    read -p "Enter your email: " EMAIL
    
    # Install certbot
    if ! command -v certbot &> /dev/null; then
        sudo apt update
        sudo apt install -y certbot
    fi
    
    # Stop services on port 80
    docker-compose down 2>/dev/null || true
    
    # Get certificate
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
    
    echo -e "${GREEN}✅ SSL certificates obtained${NC}"
else
    echo -e "${GREEN}✅ SSL certificates found${NC}"
fi

echo ""
echo "Step 3: Update nginx.conf for two-server setup"
echo "======================================"

# Update nginx to use backend server IP
sed -i 's/server backend:5000;/server 10.110.0.6:5000;/g' nginx.conf

echo -e "${GREEN}✅ Nginx configuration updated${NC}"

echo ""
echo "Step 4: Create Frontend Docker Compose"
echo "======================================"

cat > docker-compose.frontend.yml << 'EOF'
version: '3.9'

services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
    container_name: stip_frontend
    environment:
      NODE_ENV: production
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
    ports:
      - "3000:3000"
    networks:
      - stip_network
    restart: unless-stopped

  admin:
    build:
      context: ./admin
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
    container_name: stip_admin
    environment:
      NODE_ENV: production
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
      PORT: 3001
    ports:
      - "3001:3001"
    networks:
      - stip_network
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    container_name: stip_nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - frontend
      - admin
    networks:
      - stip_network
    restart: unless-stopped

networks:
  stip_network:
    driver: bridge
EOF

echo -e "${GREEN}✅ Frontend docker-compose created${NC}"

echo ""
echo "Step 5: Building and Starting Services"
echo "======================================"

docker-compose -f docker-compose.frontend.yml build --no-cache
docker-compose -f docker-compose.frontend.yml up -d

echo -e "${GREEN}✅ Services started${NC}"

echo ""
echo "Step 6: Waiting for services..."
echo "======================================"

sleep 15

echo ""
echo "Step 7: Verification"
echo "======================================"

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

# Test backend connectivity
if curl -f http://10.110.0.6:5000/api/database/health &>/dev/null; then
    echo -e "${GREEN}✅ Backend Connection: OK${NC}"
else
    echo -e "${RED}❌ Backend Connection: FAILED${NC}"
    echo "Make sure backend server is running and firewall allows access"
fi

# Test external HTTPS
if [ ! -z "$FRONTEND_URL" ]; then
    if curl -k -f $FRONTEND_URL/health &>/dev/null; then
        echo -e "${GREEN}✅ HTTPS Access: OK${NC}"
    else
        echo -e "${YELLOW}⚠️  HTTPS Access: Not accessible yet${NC}"
    fi
fi

echo ""
echo "======================================"
echo -e "${GREEN}🎉 Frontend Deployment Complete!${NC}"
echo "======================================"
echo ""
echo "Access your application:"
echo "  - Frontend: https://sarapps.com"
echo "  - Admin: https://sarapps.com/admin"
echo "  - API: https://sarapps.com/api"
echo ""
echo "Running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

