# ==========================================
# Generate Secure Secrets for Production
# ==========================================

Write-Host ""
Write-Host "Generating Secure Secrets for Production" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Function to generate random string
function Generate-Secret {
    param([int]$Length = 32)
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    return [Convert]::ToBase64String($bytes) -replace '[+/=]', ''
}

# Generate secrets
$dbPassword = Generate-Secret -Length 32
$secretKey = Generate-Secret -Length 64
$jwtSecretKey = Generate-Secret -Length 64

Write-Host "Copy and save these secrets securely!" -ForegroundColor Yellow
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

Write-Host "DATABASE PASSWORD:" -ForegroundColor Green
Write-Host "DB_PASSWORD=$dbPassword" -ForegroundColor White
Write-Host ""

Write-Host "FLASK SECRET KEY:" -ForegroundColor Green
Write-Host "SECRET_KEY=$secretKey" -ForegroundColor White
Write-Host ""

Write-Host "JWT SECRET KEY:" -ForegroundColor Green
Write-Host "JWT_SECRET_KEY=$jwtSecretKey" -ForegroundColor White
Write-Host ""

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

# Save to file
$secretsFile = "secrets_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
$content = @"
# Production Secrets - Generated $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# KEEP THIS FILE SECURE! DO NOT COMMIT TO GIT!

DB_PASSWORD=$dbPassword
SECRET_KEY=$secretKey
JWT_SECRET_KEY=$jwtSecretKey

# Use these values in your .env.production file
"@

$content | Out-File -FilePath $secretsFile -Encoding UTF8

Write-Host "SUCCESS: Secrets saved to: $secretsFile" -ForegroundColor Green
Write-Host "WARNING: Keep this file secure and delete it after use!" -ForegroundColor Yellow
Write-Host ""

# Create .env.production template with secrets filled in
Write-Host "Creating .env.production file..." -ForegroundColor Cyan

$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$envContent = @"
# ==========================================
# PRODUCTION ENVIRONMENT CONFIGURATION
# ==========================================
# Generated: $timestamp

# ==========================================
# DATABASE CONFIGURATION
# ==========================================
DB_HOST=postgres
DB_PORT=5432
DB_NAME=stip_production
DB_USER=stip_user
DB_PASSWORD=$dbPassword

# ==========================================
# FLASK CONFIGURATION
# ==========================================
FLASK_ENV=production
FLASK_APP=app.py
SECRET_KEY=$secretKey
JWT_SECRET_KEY=$jwtSecretKey

# ==========================================
# REDIS CONFIGURATION
# ==========================================
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0

# ==========================================
# APPLICATION URLS
# ==========================================
# CHANGE THIS to your actual domain!
FRONTEND_URL=https://sarapps.com
BACKEND_URL=http://backend:5000
CORS_ORIGINS="https://sarapps.com,https://www.sarapps.com"

# ==========================================
# NEXT.JS CONFIGURATION
# ==========================================
NEXT_PUBLIC_API_URL=https://sarapps.com/api
REACT_APP_API_URL=https://sarapps.com/api

# ==========================================
# EMAIL CONFIGURATION
# ==========================================
# Optional - fill these if you want email notifications
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-specific-password
MAIL_DEFAULT_SENDER=noreply@sarapps.com

# ==========================================
# FILE UPLOAD CONFIGURATION
# ==========================================
MAX_CONTENT_LENGTH=52428800
UPLOAD_FOLDER=/app/uploads

# ==========================================
# FIREBASE CONFIGURATION
# ==========================================
FIREBASE_CREDENTIALS=/app/firebase-admin-key.json

# ==========================================
# SECURITY SETTINGS
# ==========================================
SESSION_TIMEOUT=30
RATELIMIT_ENABLED=true
RATELIMIT_STORAGE_URL=redis://redis:6379/1

# ==========================================
# WORKER CONFIGURATION
# ==========================================
WORKER_REPLICAS=2
"@

$envContent | Out-File -FilePath ".env.production" -Encoding UTF8

Write-Host "SUCCESS: Created .env.production file" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Edit .env.production and update the domain name (FRONTEND_URL, etc.)" -ForegroundColor White
Write-Host "2. Add your email credentials if you want notifications" -ForegroundColor White
Write-Host "3. Review all settings" -ForegroundColor White
Write-Host "4. Upload to server during deployment" -ForegroundColor White
Write-Host ""
Write-Host "Ready to deploy! Follow DEPLOY.md" -ForegroundColor Cyan
Write-Host ""

