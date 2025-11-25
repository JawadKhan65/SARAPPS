# Backend Project Structure

## Overview
The backend has been reorganized following professional Python project practices for better maintainability, scalability, and clarity.

## Directory Structure

```
backend/
├── app.py                      # Main Flask application entry point
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
├── .env / .env.example        # Environment configuration
│
├── core/                       # Core application modules
│   ├── models.py              # SQLAlchemy database models
│   ├── extensions.py          # Flask extensions (DB, JWT, Mail)
│   └── config/
│       ├── config.py          # App configuration classes
│       └── firebase_config.py # Firebase Admin SDK setup
│
├── routes/                     # API route handlers
│   ├── auth.py                # Authentication & authorization
│   ├── admin.py               # Admin panel operations
│   ├── user.py                # User profile & operations
│   ├── crawlers.py            # Crawler management (background jobs)
│   ├── matches.py             # Shoe matching results
│   ├── images.py              # Image upload & management
│   └── database.py            # Database operations
│
├── services/                   # Business logic layer
│   ├── scraper_service.py     # Scraping operations
│   ├── scraper_manager.py     # Crawler orchestration
│   └── crawler_scheduler.py  # Scheduled crawler tasks
│
├── jobs/                       # Background job processing
│   ├── tasks.py               # RQ task definitions
│   └── worker.py              # RQ worker process
│
├── scrapers/                   # Website scraper modules
│   └── [individual scrapers]
│
├── ml_models/                  # Machine learning components
│   ├── clip_model.py          # CLIP model integration
│   ├── prediction.py          # ML prediction logic
│   └── *.pth                  # Model weights
│
├── utils/                      # Utility functions
│   └── [helper modules]
│
├── line_tracing_utils/         # Shoe sole line tracing
│   └── line_tracing.py
│
├── database/                   # Database management
│   ├── migrations/            # Schema migrations
│   │   ├── add_otp_columns.py
│   │   ├── add_reset_token_fields.py
│   │   └── [other migrations]
│   ├── scripts/               # DB utility scripts
│   │   ├── init_db.py         # Initialize database
│   │   ├── verify_installation.py
│   │   └── reset_database.ps1
│   └── sql_schemas/           # SQL schema definitions
│
├── templates/                  # Jinja2 email templates
│   ├── otp_email.html
│   └── password_reset_otp.html
│
├── static/                     # Static assets (logos, etc.)
├── assets/                     # App assets (base64 logos)
├── data/                       # Scraped shoe data
├── uploads/                    # User-uploaded images
├── backups/                    # Database backups
├── logs/                       # Application logs
│
├── scripts/                    # Standalone utility scripts
│   ├── main.py                # Legacy matching script
│   └── trace_footprints.py    # Footprint tracing utility
│
└── docs/                       # Documentation
    ├── README.md              # This file
    ├── FOLDER_STRUCTURE.md    # Detailed structure guide
    └── BACKGROUND_JOBS_SETUP.md
```

## Import Changes

All imports have been updated to reflect the new structure:

### Before:
```python
from config import config
from extensions import db, jwt
from models import User, AdminUser
import firebase_config
```

### After:
```python
from core.config.config import config
from core.extensions import db, jwt
from core.models import User, AdminUser
import core.config.firebase_config
```

## Running the Application

### Development
```bash
python app.py
```

### With Worker (Background Jobs)
```bash
# Terminal 1: Run Flask app
python app.py

# Terminal 2: Run RQ worker
python jobs/worker.py
```

### Initialize Database
```bash
python database/scripts/init_db.py
```

### Run Migrations
```bash
python database/migrations/add_reset_token_fields.py
```

## Key Benefits

1. **Separation of Concerns**: Clear boundaries between layers (routes, services, jobs)
2. **Easier Navigation**: Related files are grouped together
3. **Better Testing**: Easier to write unit tests for each module
4. **Scalability**: Simple to add new features without cluttering root
5. **Professional**: Follows Flask/Python best practices
6. **Maintainability**: Easier for new developers to understand

## Module Descriptions

### `core/`
Contains the foundational components of the application:
- **models.py**: SQLAlchemy models for all database tables
- **extensions.py**: Initialized Flask extensions (SQLAlchemy, JWT, Flask-Mail)
- **config/**: Configuration classes for different environments

### `routes/`
HTTP endpoint handlers organized by resource:
- Each file defines a Flask Blueprint
- Handles request validation and response formatting
- Calls service layer for business logic

### `services/`
Business logic layer:
- Encapsulates complex operations
- Can be reused across routes
- Easier to unit test

### `jobs/`
Background task processing:
- **tasks.py**: Defines async jobs (crawlers, email sending)
- **worker.py**: RQ worker that processes jobs

### `database/`
Database management:
- **migrations/**: Schema changes and data migrations
- **scripts/**: Utility scripts for DB operations
- **sql_schemas/**: Raw SQL schema files

## Notes

- All files have been moved and imports updated automatically
- The application structure is now production-ready
- Follow this structure when adding new features
