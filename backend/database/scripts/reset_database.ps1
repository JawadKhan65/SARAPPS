# ============================================================================
# Database Reset Script with User Groups Support
# ============================================================================
# This script drops and recreates the database with all tables including
# the new user_groups table
# ============================================================================

Write-Host "🔄 Starting database reset..." -ForegroundColor Cyan
Write-Host ""

# Configuration
$DB_NAME = "shoe_identifier"
$DB_USER = "postgres"
$DB_PASSWORD = "postgres"
$PGPASSWORD = $DB_PASSWORD

# Set environment variable for password
$env:PGPASSWORD = $PGPASSWORD

Write-Host "⚠️  WARNING: This will DELETE ALL DATA in the database!" -ForegroundColor Yellow
Write-Host "Database: $DB_NAME" -ForegroundColor Yellow
Write-Host ""
$confirmation = Read-Host "Are you sure you want to continue? (yes/no)"

if ($confirmation -ne "yes") {
    Write-Host "❌ Operation cancelled." -ForegroundColor Red
    exit 0
}

Write-Host ""
Write-Host "Step 1: Dropping existing database..." -ForegroundColor Yellow

# Terminate existing connections
psql -U $DB_USER -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" 2>$null

# Drop database
psql -U $DB_USER -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Database dropped successfully" -ForegroundColor Green
} else {
    Write-Host "⚠️  Database may not exist or already dropped" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Step 2: Creating new database..." -ForegroundColor Yellow

# Create database
psql -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME WITH ENCODING='UTF8' LC_COLLATE='en_US.UTF-8' LC_CTYPE='en_US.UTF-8' TEMPLATE=template0;"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Database created successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to create database" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 3: Initializing schema from init_db.sql..." -ForegroundColor Yellow

# Run init script
psql -U $DB_USER -d $DB_NAME -f "init_db.sql"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Schema initialized successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to initialize schema" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 4: Verifying tables..." -ForegroundColor Yellow

# Verify tables
$tables = psql -U $DB_USER -d $DB_NAME -t -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"

Write-Host "📋 Created tables:" -ForegroundColor Cyan
$tables -split "`n" | Where-Object { $_.Trim() -ne "" } | ForEach-Object {
    Write-Host "   - $($_.Trim())" -ForegroundColor White
}

Write-Host ""
Write-Host "Step 5: Checking user_groups table..." -ForegroundColor Yellow

$groupsCheck = psql -U $DB_USER -d $DB_NAME -t -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'user_groups' ORDER BY ordinal_position;"

if ($groupsCheck) {
    Write-Host "✅ user_groups table exists with columns:" -ForegroundColor Green
    $groupsCheck -split "`n" | Where-Object { $_.Trim() -ne "" } | ForEach-Object {
        Write-Host "   - $($_.Trim())" -ForegroundColor White
    }
} else {
    Write-Host "❌ user_groups table not found!" -ForegroundColor Red
}

Write-Host ""
Write-Host "Step 6: Checking users.group_id column..." -ForegroundColor Yellow

$groupIdCheck = psql -U $DB_USER -d $DB_NAME -t -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'group_id';"

if ($groupIdCheck) {
    Write-Host "✅ users.group_id column exists: $($groupIdCheck.Trim())" -ForegroundColor Green
} else {
    Write-Host "❌ users.group_id column not found!" -ForegroundColor Red
}

Write-Host ""
Write-Host "Step 7: Creating uploads directory..." -ForegroundColor Yellow

$uploadsDir = "uploads/group_images"
if (!(Test-Path $uploadsDir)) {
    New-Item -ItemType Directory -Path $uploadsDir -Force | Out-Null
    Write-Host "✅ Created $uploadsDir directory" -ForegroundColor Green
} else {
    Write-Host "✅ Uploads directory already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "🎉 Database reset completed successfully!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Default admin credentials:" -ForegroundColor Yellow
Write-Host "  Email: admin@shoeidentifier.local" -ForegroundColor White
Write-Host "  Password: admin123" -ForegroundColor White
Write-Host ""
Write-Host "You can now start the Flask backend:" -ForegroundColor Cyan
Write-Host "  python app.py" -ForegroundColor White
Write-Host ""

# Clean up environment variable
$env:PGPASSWORD = $null
