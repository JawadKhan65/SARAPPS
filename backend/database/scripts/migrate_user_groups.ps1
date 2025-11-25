# ============================================================================
# Add User Groups Migration Script
# ============================================================================
# This script adds user groups functionality WITHOUT dropping existing data
# Use this if you want to keep your existing users and images
# ============================================================================

Write-Host "🔄 Starting User Groups migration..." -ForegroundColor Cyan
Write-Host ""

# Configuration
$DB_NAME = "shoe_identifier"
$DB_USER = "postgres"
$DB_PASSWORD = "postgres"
$env:PGPASSWORD = $DB_PASSWORD

Write-Host "Database: $DB_NAME" -ForegroundColor Yellow
Write-Host "This will ADD user groups feature to existing database" -ForegroundColor Yellow
Write-Host "Existing data will NOT be deleted" -ForegroundColor Green
Write-Host ""

$confirmation = Read-Host "Continue with migration? (yes/no)"

if ($confirmation -ne "yes") {
    Write-Host "❌ Operation cancelled." -ForegroundColor Red
    exit 0
}

Write-Host ""
Write-Host "Running migration script..." -ForegroundColor Yellow

# Run migration
psql -U $DB_USER -d $DB_NAME -f "add_user_groups.sql"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Migration completed successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Migration failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Creating uploads directory..." -ForegroundColor Yellow

$uploadsDir = "uploads/group_images"
if (!(Test-Path $uploadsDir)) {
    New-Item -ItemType Directory -Path $uploadsDir -Force | Out-Null
    Write-Host "✅ Created $uploadsDir directory" -ForegroundColor Green
} else {
    Write-Host "✅ Uploads directory already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "🎉 User Groups feature added successfully!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now:" -ForegroundColor Cyan
Write-Host "  1. Restart your Flask backend" -ForegroundColor White
Write-Host "  2. Go to Admin Panel → Groups" -ForegroundColor White
Write-Host "  3. Create groups and upload images" -ForegroundColor White
Write-Host ""

$env:PGPASSWORD = $null
