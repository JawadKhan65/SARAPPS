# ==========================================
# Local Testing Script (PowerShell)
# ==========================================
# Test the application locally on Windows before deploying

Write-Host "🧪 Testing Application Locally..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not running" -ForegroundColor Red
    Write-Host "Please start Docker Desktop first" -ForegroundColor Yellow
    exit 1
}

# Check required files
Write-Host "`nChecking required files..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

$requiredFiles = @(
    "backend\Dockerfile",
    "backend\app.py",
    "backend\requirements.txt",
    "frontend\Dockerfile",
    "frontend\package.json",
    "admin\Dockerfile",
    "admin\package.json",
    "docker-compose.yml",
    "nginx.conf"
)

$allFilesExist = $true
foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "✅ $file" -ForegroundColor Green
    } else {
        Write-Host "❌ $file (missing)" -ForegroundColor Red
        $allFilesExist = $false
    }
}

if (-not $allFilesExist) {
    Write-Host "`n❌ Some required files are missing" -ForegroundColor Red
    exit 1
}

# Check Firebase credentials
if (-not (Test-Path "backend\firebase-admin-key.json")) {
    Write-Host "⚠️  Warning: backend\firebase-admin-key.json not found" -ForegroundColor Yellow
    Write-Host "Firebase authentication may not work without this file" -ForegroundColor Yellow
}

# Create local environment file
if (-not (Test-Path ".env.local")) {
    Write-Host "`nCreating .env.local file..." -ForegroundColor Cyan
    
    $envContent = @"
# Local Testing Environment
FLASK_ENV=development
DB_PASSWORD=test_password_123
SECRET_KEY=dev_secret_key_not_for_production
JWT_SECRET_KEY=dev_jwt_secret_key_not_for_production
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost,http://localhost:443
NEXT_PUBLIC_API_URL=http://localhost/api
REACT_APP_API_URL=http://localhost/api
FRONTEND_URL=http://localhost
"@
    
    $envContent | Out-File -FilePath ".env.local" -Encoding UTF8
    Write-Host "✅ Created .env.local" -ForegroundColor Green
}

# Create SSL directory and self-signed certificates
if (-not (Test-Path "ssl\cert.pem") -or -not (Test-Path "ssl\key.pem")) {
    Write-Host "`nCreating self-signed SSL certificates..." -ForegroundColor Cyan
    
    if (-not (Test-Path "ssl")) {
        New-Item -ItemType Directory -Path "ssl" | Out-Null
    }
    
    # Check if OpenSSL is available
    try {
        openssl version | Out-Null
        
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 `
            -keyout ssl\key.pem `
            -out ssl\cert.pem `
            -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost" 2>$null
        
        Write-Host "✅ SSL certificates created" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  OpenSSL not found - skipping SSL certificate generation" -ForegroundColor Yellow
        Write-Host "You can install OpenSSL or manually create certificates later" -ForegroundColor Yellow
        
        # Create dummy files so docker-compose doesn't fail
        "DUMMY CERT" | Out-File -FilePath "ssl\cert.pem" -Encoding ASCII
        "DUMMY KEY" | Out-File -FilePath "ssl\key.pem" -Encoding ASCII
    }
}

# Stop existing containers
Write-Host "`nStopping existing containers..." -ForegroundColor Cyan
docker-compose down 2>$null

# Build images
Write-Host "`nBuilding Docker images..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "⏳ This may take 5-10 minutes on first run..." -ForegroundColor Yellow

$buildResult = docker-compose build 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Images built successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Build failed" -ForegroundColor Red
    Write-Host $buildResult
    exit 1
}

# Start services
Write-Host "`nStarting services..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

$startResult = docker-compose up -d 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Services started" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to start services" -ForegroundColor Red
    Write-Host $startResult
    docker-compose logs
    exit 1
}

Write-Host "`nWaiting for services to be ready..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Start-Sleep -Seconds 20

# Test services
Write-Host "`nTesting services..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

$servicesOk = $true

# Check PostgreSQL
try {
    docker exec stip_postgres pg_isready -U stip_user 2>$null | Out-Null
    Write-Host "✅ PostgreSQL" -ForegroundColor Green
} catch {
    Write-Host "❌ PostgreSQL" -ForegroundColor Red
    $servicesOk = $false
}

# Check Redis
try {
    docker exec stip_redis redis-cli ping 2>$null | Out-Null
    Write-Host "✅ Redis" -ForegroundColor Green
} catch {
    Write-Host "❌ Redis" -ForegroundColor Red
    $servicesOk = $false
}

# Check Backend
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/api/database/health" -TimeoutSec 5 -UseBasicParsing
    Write-Host "✅ Backend API (http://localhost:5000)" -ForegroundColor Green
} catch {
    Write-Host "❌ Backend API" -ForegroundColor Red
    $servicesOk = $false
}

# Check Frontend
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 5 -UseBasicParsing
    Write-Host "✅ Frontend (http://localhost:3000)" -ForegroundColor Green
} catch {
    Write-Host "❌ Frontend" -ForegroundColor Red
    $servicesOk = $false
}

# Check Admin
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3001" -TimeoutSec 5 -UseBasicParsing
    Write-Host "✅ Admin Panel (http://localhost:3001)" -ForegroundColor Green
} catch {
    Write-Host "❌ Admin Panel" -ForegroundColor Red
    $servicesOk = $false
}

# Check Nginx
try {
    $response = Invoke-WebRequest -Uri "https://localhost/health" -SkipCertificateCheck -TimeoutSec 5 -UseBasicParsing
    Write-Host "✅ Nginx (https://localhost)" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Nginx (https://localhost) - may take a moment" -ForegroundColor Yellow
}

Write-Host "`n======================================" -ForegroundColor Cyan

if ($servicesOk) {
    Write-Host "🎉 All services are running!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Access your application:" -ForegroundColor Cyan
    Write-Host "  - Frontend:    http://localhost:3000" -ForegroundColor White
    Write-Host "  - Admin Panel: http://localhost:3001" -ForegroundColor White
    Write-Host "  - Backend API: http://localhost:5000" -ForegroundColor White
    Write-Host "  - Via Nginx:   https://localhost (⚠️  ignore SSL warning)" -ForegroundColor White
    Write-Host ""
    Write-Host "Useful commands:" -ForegroundColor Cyan
    Write-Host "  - View logs:        docker-compose logs -f" -ForegroundColor White
    Write-Host "  - Stop services:    docker-compose down" -ForegroundColor White
    Write-Host "  - Restart services: docker-compose restart" -ForegroundColor White
    Write-Host ""
    Write-Host "Running containers:" -ForegroundColor Cyan
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
} else {
    Write-Host "❌ Some services failed to start" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check logs with:" -ForegroundColor Yellow
    Write-Host "  docker-compose logs"
    Write-Host ""
    Write-Host "Or for specific service:" -ForegroundColor Yellow
    Write-Host "  docker logs stip_backend"
    Write-Host "  docker logs stip_frontend"
    Write-Host "  docker logs stip_admin"
    exit 1
}

# Initialize database
Write-Host "`nInitializing database..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

Start-Sleep -Seconds 5

try {
    docker exec -it stip_backend python scripts/init_db.py 2>$null
    Write-Host "✅ Database initialized" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Database initialization skipped or already done" -ForegroundColor Yellow
}

Write-Host "`n======================================" -ForegroundColor Cyan
Write-Host "✨ Local testing environment is ready!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Open http://localhost:3000 in your browser"
Write-Host "2. Test the application functionality"
Write-Host "3. If everything works, proceed with production deployment"
Write-Host ""
Write-Host "To view real-time logs:" -ForegroundColor Cyan
Write-Host "  docker-compose logs -f"
Write-Host ""

