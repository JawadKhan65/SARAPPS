# Backend Folder Structure Reorganization

## New Structure

```
backend/
├── app.py                      # Main application entry point
├── main.py                     # Alternative entry point
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
├── .env                        # Environment variables
├── .env.example               # Example environment variables
│
├── core/                       # Core application modules
│   ├── __init__.py
│   ├── models.py              # Database models
│   ├── extensions.py          # Flask extensions
│   └── config/
│       ├── __init__.py
│       ├── config.py          # Configuration classes
│       └── firebase_config.py # Firebase configuration
│
├── routes/                     # API endpoints
│   ├── __init__.py
│   ├── auth.py                # Authentication routes
│   ├── admin.py               # Admin routes
│   ├── user.py                # User routes
│   ├── crawlers.py            # Crawler management
│   ├── matches.py             # Match results
│   ├── images.py              # Image management
│   └── database.py            # Database operations
│
├── services/                   # Business logic
│   ├── __init__.py
│   ├── scraper_service.py     # Scraper operations
│   ├── scraper_manager.py     # Scraper orchestration
│   └── crawler_scheduler.py  # Crawler scheduling
│
├── jobs/                       # Background jobs
│   ├── __init__.py
│   ├── tasks.py               # Job definitions
│   └── worker.py              # Job worker
│
├── scrapers/                   # Website scrapers
│   ├── __init__.py
│   └── [scraper modules]
│
├── ml_models/                  # Machine learning models
│   ├── __init__.py
│   ├── clip_model.py
│   ├── prediction.py
│   └── shoe_sole_classifier_full.pth
│
├── utils/                      # Utility functions
│   ├── __init__.py
│   └── [utility modules]
│
├── line_tracing_utils/         # Line tracing utilities
│   ├── __init__.py
│   └── line_tracing.py
│
├── database/                   # Database management
│   ├── __init__.py
│   ├── migrations/            # Database migrations
│   │   ├── add_otp_columns.py
│   │   ├── add_user_groups.sql
│   │   ├── add_reset_token_fields.py
│   │   ├── migrate_add_groups.py
│   │   ├── migrate_binary_images.py
│   │   └── migrate_binary_images.sql
│   ├── scripts/               # Database scripts
│   │   ├── init_db.py
│   │   ├── init_db.sql
│   │   ├── verify_installation.py
│   │   ├── reset_database.ps1
│   │   ├── reset_sole_images.sql
│   │   └── migrate_user_groups.ps1
│   └── sql_schemas/           # SQL schema files
│       └── schema.sql
│
├── templates/                  # Email templates
│   ├── otp_email.html
│   └── password_reset_otp.html
│
├── static/                     # Static files
│   └── [static assets]
│
├── assets/                     # Application assets
│   ├── logo_base64.txt
│   ├── logo_base64_small.txt
│   └── logo_img_tag.txt
│
├── data/                       # Scraped data
│   ├── images/
│   └── [json files]
│
├── uploads/                    # User uploads
│
├── backups/                    # Database backups
│
├── docs/                       # Documentation
│   ├── README.md
│   └── BACKGROUND_JOBS_SETUP.md
│
├── logs/                       # Application logs
│
└── scripts/                    # Utility scripts
    └── trace_footprints.py
```

## Import Path Changes

### Before:
```python
from config import config
from extensions import db, jwt, mail
from models import User, AdminUser
import firebase_config
```

### After:
```python
from core.config.config import config
from core.extensions import db, jwt, mail
from core.models import User, AdminUser
import core.config.firebase_config
```

## Updated Files

### app.py
- Updated imports to use new `core.*` paths
- All other functionality remains the same

### Routes (routes/*.py)
- Update: `from extensions import` → `from core.extensions import`
- Update: `from models import` → `from core.models import`
- Update: `from firebase_config import` → `from core.config.firebase_config import`

### Services (services/*.py)
- Update: `from extensions import` → `from core.extensions import`
- Update: `from models import` → `from core.models import`

### Jobs (jobs/*.py)
- Update: `from extensions import` → `from core.extensions import`
- Update: `from models import` → `from core.models import`

## Benefits

1. **Better Organization**: Clear separation of concerns
2. **Professional Structure**: Follows Python project best practices
3. **Scalability**: Easier to add new modules
4. **Maintainability**: Easier to locate and update code
5. **Testing**: Better structure for unit tests
6. **Documentation**: Clearer project structure

## Migration Steps Completed

1. ✅ Created new folder structure
2. ✅ Moved core files to `core/` directory
3. ✅ Moved configuration files to `core/config/`
4. ✅ Moved job files to `jobs/` directory
5. ✅ Moved database files to `database/` directory
6. ✅ Moved documentation to `docs/` directory
7. ✅ Moved assets to `assets/` directory
8. ✅ Created `__init__.py` files for packages
9. ✅ Updated `app.py` imports

## Next Steps

Run this command to update all import statements in routes, services, and jobs:

```powershell
# Update routes
Get-ChildItem "routes/*.py" | ForEach-Object {
    (Get-Content $_.FullName) -replace 'from extensions import', 'from core.extensions import' `
                               -replace 'from models import', 'from core.models import' `
                               -replace 'from firebase_config import', 'from core.config.firebase_config import' `
    | Set-Content $_.FullName
}

# Update services
Get-ChildItem "services/*.py" | ForEach-Object {
    (Get-Content $_.FullName) -replace 'from extensions import', 'from core.extensions import' `
                               -replace 'from models import', 'from core.models import' `
    | Set-Content $_.FullName
}

# Update jobs
Get-ChildItem "jobs/*.py" | ForEach-Object {
    (Get-Content $_.FullName) -replace 'from extensions import', 'from core.extensions import' `
                               -replace 'from models import', 'from core.models import' `
    | Set-Content $_.FullName
}
```
