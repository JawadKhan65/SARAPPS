# Test Backend Connectivity
Write-Host "🧪 Testing Backend Connection..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# Test if backend is running
Write-Host "`nChecking if backend is accessible..." -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/api/database/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "✅ Backend is running!" -ForegroundColor Green
    Write-Host "Status: $($response.StatusCode)" -ForegroundColor White
    Write-Host "Response: $($response.Content)" -ForegroundColor White
} catch {
    Write-Host "❌ Backend is NOT running or not accessible" -ForegroundColor Red
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "`nPlease start the backend:" -ForegroundColor Yellow
    Write-Host "  cd backend" -ForegroundColor White
    Write-Host "  python app.py" -ForegroundColor White
    exit 1
}

# Test CORS for admin login endpoint
Write-Host "`nTesting CORS for admin login endpoint..." -ForegroundColor Yellow

try {
    # Make an OPTIONS request (preflight)
    $headers = @{
        "Origin" = "http://localhost:3001"
        "Access-Control-Request-Method" = "POST"
        "Access-Control-Request-Headers" = "Content-Type"
    }
    
    $response = Invoke-WebRequest `
        -Uri "http://localhost:5000/api/auth/admin/login" `
        -Method OPTIONS `
        -Headers $headers `
        -UseBasicParsing `
        -TimeoutSec 5
    
    Write-Host "✅ CORS preflight successful!" -ForegroundColor Green
    Write-Host "Status: $($response.StatusCode)" -ForegroundColor White
    
    # Check CORS headers
    if ($response.Headers["Access-Control-Allow-Origin"]) {
        Write-Host "✅ Access-Control-Allow-Origin: $($response.Headers['Access-Control-Allow-Origin'])" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Warning: No Access-Control-Allow-Origin header found" -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "⚠️  CORS preflight test failed" -ForegroundColor Yellow
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}

# Test admin login with dummy credentials
Write-Host "`nTesting admin login endpoint..." -ForegroundColor Yellow

try {
    $body = @{
        email = "test@example.com"
        password = "test"
    } | ConvertTo-Json
    
    $headers = @{
        "Content-Type" = "application/json"
        "Origin" = "http://localhost:3001"
    }
    
    $response = Invoke-WebRequest `
        -Uri "http://localhost:5000/api/auth/admin/login" `
        -Method POST `
        -Headers $headers `
        -Body $body `
        -UseBasicParsing `
        -TimeoutSec 5 `
        -ErrorAction Stop
    
    Write-Host "Response Status: $($response.StatusCode)" -ForegroundColor White
    
} catch {
    # Expected to fail with 401 for invalid credentials
    if ($_.Exception.Response.StatusCode -eq 401) {
        Write-Host "✅ Endpoint is accessible (401 Unauthorized - expected for bad credentials)" -ForegroundColor Green
    } elseif ($_.Exception.Response.StatusCode -eq 404) {
        Write-Host "❌ Endpoint not found (404)" -ForegroundColor Red
    } else {
        Write-Host "Response Status: $($_.Exception.Response.StatusCode)" -ForegroundColor Yellow
    }
}

Write-Host "`n======================================" -ForegroundColor Cyan
Write-Host "Backend connectivity test complete!" -ForegroundColor Cyan
Write-Host ""
Write-Host "If you see CORS errors, restart the backend:" -ForegroundColor Yellow
Write-Host "  1. Stop the backend (Ctrl+C)" -ForegroundColor White
Write-Host "  2. cd backend" -ForegroundColor White
Write-Host "  3. python app.py" -ForegroundColor White
Write-Host ""

