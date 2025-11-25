# Backend API - Shoe Type Identification System

## Overview

The backend is a Flask-based REST API that powers the Shoe Type Identification System, providing authentication, image processing, shoe matching, web scraping, and admin management capabilities.

## Quick Start

```powershell
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your database and JWT secret

# Initialize database
python init_db.py

# Run development server
python app.py

# Or use Waitress for production
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

**Access:** http://localhost:5000

**Test Admin Login:**
- Email: `admin@shoeidentifier.local`
- Password: `admin123`

## Project Structure

```
backend/
├── app.py                          # Flask app factory
├── config.py                       # Configuration management
├── extensions.py                   # Flask extensions (SQLAlchemy, JWT, CORS)
├── models.py                       # Database models
├── requirements.txt                # Python dependencies
├── init_db.py                      # Database initialization script
├── routes/
│   ├── auth.py                    # Authentication endpoints
│   ├── user.py                    # User management
│   ├── matches.py                 # Shoe matching & history
│   ├── crawlers.py                # Crawler management
│   ├── admin.py                   # Admin dashboard
│   └── database.py                # Database utilities
├── services/
│   ├── image_processor.py         # Image processing & feature extraction
│   ├── scraper_manager.py         # Web scraping orchestration
│   ├── crawler_scheduler.py       # APScheduler for crawler jobs
│   └── scraper_service.py         # Batch insertion with uniqueness
├── scrapers/
│   ├── base_scraper.py            # Base scraper class
│   ├── nike_scraper.py            # Nike.com scraper
│   ├── adidas_scraper.py          # Adidas.com scraper
│   ├── puma_scraper.py            # Puma.com scraper
│   └── ... (15+ brand scrapers)
├── ml_models/
│   ├── clip_model.py              # CLIP embeddings
│   ├── lbp_extractor.py           # Local Binary Patterns
│   ├── edge_extractor.py          # Edge detection
│   ├── color_extractor.py         # Color histograms
│   └── line_tracer.py             # Line tracing patterns
├── utils/
│   ├── validators.py              # Input validation
│   ├── helpers.py                 # Utility functions
│   └── logger.py                  # Logging configuration
├── db/
│   └── schema.sql                 # PostgreSQL schema
├── data/                           # Scraped data storage
├── uploads/                        # Temporary image uploads
├── logs/                           # Application logs
└── migrations/                     # Database migrations
```

## API Endpoints

### Authentication (`/api/auth`)

#### Register
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "username": "username",
  "password": "password123"
}

Response 201:
{
  "success": true,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "username"
  },
  "token": "eyJ..."
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123",
  "remember_me": true
}

Response 200:
{
  "success": true,
  "token": "eyJ...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "username",
    "group_id": 1,
    "profile_image_url": "http://localhost:5000/api/admin/groups/1/image"
  }
}
```

#### Refresh Token
```http
POST /api/auth/refresh
Authorization: Bearer <token>

Response 200:
{
  "token": "eyJ..."
}
```

#### Logout
```http
POST /api/auth/logout
Authorization: Bearer <token>

Response 200:
{
  "success": true,
  "message": "Logged out successfully"
}
```

### User Management (`/api/user`)

#### Get Profile
```http
GET /api/user/profile
Authorization: Bearer <token>

Response 200:
{
  "id": 1,
  "email": "user@example.com",
  "username": "username",
  "dark_mode": false,
  "language": "en",
  "group_id": 1,
  "profile_image_url": "http://..."
}
```

#### Update Profile
```http
PUT /api/user/profile
Authorization: Bearer <token>
Content-Type: application/json

{
  "username": "newusername",
  "dark_mode": true,
  "language": "en"
}

Response 200:
{
  "success": true,
  "user": { ... }
}
```

#### Upload Profile Image
```http
POST /api/user/upload-image
Authorization: Bearer <token>
Content-Type: multipart/form-data

FormData: {
  image: <File>
}

Response 200:
{
  "success": true,
  "image_id": 123,
  "image_url": "http://..."
}
```

#### Change Password
```http
POST /api/user/change-password
Authorization: Bearer <token>
Content-Type: application/json

{
  "current_password": "oldpass",
  "new_password": "newpass123"
}

Response 200:
{
  "success": true,
  "message": "Password changed successfully"
}
```

#### Delete Account
```http
DELETE /api/user/account
Authorization: Bearer <token>
Content-Type: application/json

{
  "password": "password123"
}

Response 200:
{
  "success": true,
  "message": "Account deleted"
}
```

### Shoe Matching (`/api/matches`)

#### Identify Shoe
```http
POST /api/matches/identify
Authorization: Bearer <token>
Content-Type: application/json

{
  "image_id": 123
}

Response 200:
{
  "matches": [
    {
      "shoe_id": 456,
      "brand": "Nike",
      "model": "Air Max 90",
      "color": "White/Black",
      "size": "10",
      "confidence_score": 95.8,
      "similarity_score": 0.958,
      "image_url": "http://...",
      "product_url": "https://nike.com/..."
    }
  ],
  "processing_time": 1.23
}
```

#### Get Match History
```http
GET /api/matches/history?page=1&limit=20
Authorization: Bearer <token>

Response 200:
{
  "matches": [ ... ],
  "total": 45,
  "page": 1,
  "pages": 3
}
```

#### Confirm Match
```http
POST /api/matches/confirm
Authorization: Bearer <token>
Content-Type: application/json

{
  "match_id": 789,
  "is_correct": true
}

Response 200:
{
  "success": true,
  "message": "Match confirmed"
}
```

### Admin (`/api/admin`)

#### Admin Login
```http
POST /api/admin/login
Content-Type: application/json

{
  "email": "admin@shoeidentifier.local",
  "password": "admin123",
  "mfa_token": "123456"  // Optional, if MFA enabled
}

Response 200:
{
  "success": true,
  "token": "eyJ...",
  "admin_user": { ... }
}
```

#### List Users
```http
GET /api/admin/users?page=1&limit=20
Authorization: Bearer <admin_token>

Response 200:
{
  "users": [ ... ],
  "total": 150,
  "page": 1,
  "pages": 8
}
```

#### Update User
```http
PUT /api/admin/users/:id
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "is_active": false
}

Response 200:
{
  "success": true,
  "user": { ... }
}
```

#### Delete User
```http
DELETE /api/admin/users/:id
Authorization: Bearer <admin_token>

Response 200:
{
  "success": true,
  "message": "User deleted"
}
```

#### System Statistics
```http
GET /api/admin/stats/system
Authorization: Bearer <admin_token>

Response 200:
{
  "total_users": 150,
  "total_shoes": 12500,
  "active_crawlers": 8,
  "database_size": "2.3 GB",
  "uptime": "7 days, 12:34:56"
}
```

### Crawler Management (`/api/admin/crawlers`)

#### List Crawlers
```http
GET /api/admin/crawlers
Authorization: Bearer <admin_token>

Response 200:
{
  "crawlers": [
    {
      "id": "nike_scraper",
      "name": "Nike.com",
      "website_url": "https://nike.com",
      "is_active": true,
      "is_running": false,
      "schedule_cron": "0 2 15 * *",
      "next_run_at": "2025-12-15T02:00:00",
      "items_scraped": 1523,
      "unique_images_added": 1245,
      "uniqueness_percentage": 81.7,
      "last_run_at": "2025-11-15T02:00:00"
    }
  ]
}
```

#### Start Crawler
```http
POST /api/admin/crawlers/:id/start
Authorization: Bearer <admin_token>

Response 200:
{
  "success": true,
  "message": "Crawler started",
  "job_id": "abc123"
}
```

#### Stop Crawler
```http
POST /api/admin/crawlers/:id/stop
Authorization: Bearer <admin_token>

Response 200:
{
  "success": true,
  "message": "Crawler stopped"
}
```

#### Update Crawler Config
```http
PUT /api/admin/crawlers/:id/config
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "schedule_cron": "0 2 15 3 *",
  "is_active": true,
  "min_uniqueness_threshold": 85
}

Response 200:
{
  "success": true,
  "crawler": { ... }
}
```

## Database Models

### User
```python
class User(db.Model):
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    dark_mode = Column(Boolean, default=False)
    language = Column(String(10), default='en')
    group_id = Column(Integer, ForeignKey('user_groups.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
```

### Shoe
```python
class Shoe(db.Model):
    id = Column(Integer, primary_key=True)
    brand = Column(String(100), nullable=False)
    model = Column(String(200), nullable=False)
    color = Column(String(100))
    size = Column(String(20))
    image_path = Column(String(500))
    image_url = Column(String(500))
    product_url = Column(String(500))
    features_vector = Column(Vector(512))  # pgvector
    lbp_features = Column(Vector(256))
    edge_features = Column(Vector(128))
    color_features = Column(Vector(64))
    clip_features = Column(Vector(512))
    line_trace_features = Column(Vector(256))
    uniqueness_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    source_crawler = Column(String(100))
```

### UploadedImage
```python
class UploadedImage(db.Model):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    image_path = Column(String(500))
    features_vector = Column(Vector(512))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    quality_score = Column(Float)
```

### MatchResult
```python
class MatchResult(db.Model):
    id = Column(Integer, primary_key=True)
    uploaded_image_id = Column(Integer, ForeignKey('uploaded_images.id'))
    shoe_id = Column(Integer, ForeignKey('shoes.id'))
    similarity_score = Column(Float)
    confidence_score = Column(Float)
    is_confirmed = Column(Boolean)
    matched_at = Column(DateTime, default=datetime.utcnow)
```

### Crawler
```python
class Crawler(db.Model):
    id = Column(String(100), primary_key=True)
    name = Column(String(200))
    website_url = Column(String(500))
    is_active = Column(Boolean, default=True)
    is_running = Column(Boolean, default=False)
    schedule_cron = Column(String(100))
    next_run_at = Column(DateTime)
    last_run_at = Column(DateTime)
    items_scraped = Column(Integer, default=0)
    unique_images_added = Column(Integer, default=0)
    min_uniqueness_threshold = Column(Float, default=0.85)
```

### UserGroup
```python
class UserGroup(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    profile_image_data = Column(LargeBinary)  # BYTEA storage
    image_content_type = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
```

## Image Processing Pipeline

### 5-Feature Extraction

**1. LBP (Local Binary Patterns)**
- Texture analysis of sole patterns
- 256-dimensional feature vector
- Rotation-invariant uniform patterns

**2. Edge Detection**
- Canny edge detection
- Sole outline and tread patterns
- 128-dimensional feature vector

**3. Color Histogram**
- HSV color space analysis
- Dominant color extraction
- 64-dimensional feature vector

**4. CLIP Embeddings**
- Pre-trained vision transformer
- Semantic understanding
- 512-dimensional feature vector

**5. Line Tracing**
- Footprint pattern analysis
- Unique tread signature detection
- 256-dimensional feature vector

### Combined Feature Vector
- All features concatenated
- Total: 1216 dimensions
- Reduced to 512 via PCA for efficiency
- Stored in PostgreSQL with pgvector extension

### Matching Algorithm
```python
1. Extract features from uploaded image
2. Query database with cosine similarity:
   SELECT *, 1 - (features_vector <=> query_vector) AS similarity
   FROM shoes
   ORDER BY features_vector <=> query_vector
   LIMIT 10
3. Calculate confidence score:
   - Excellent: 90-100%
   - Good: 75-89%
   - Fair: 60-74%
   - Poor: 0-59%
4. Return ranked matches
```

## Web Scraping System

### Supported Brands (15+)
- Nike (nike.com)
- Adidas (adidas.com)
- Puma (puma.com)
- New Balance (newbalance.com)
- Reebok (reebok.com)
- Under Armour (underarmour.com)
- Vans (vans.com)
- Converse (converse.com)
- ASICS (asics.com)
- Skechers (skechers.com)
- ... and more

### Scraper Features
- **JavaScript Rendering**: Playwright for dynamic content
- **Lazy Loading Detection**: Wait for images to load
- **Rate Limiting**: Respectful scraping with delays
- **Proxy Rotation**: Avoid IP bans (configurable)
- **Error Handling**: Retry logic and fallbacks
- **Data Validation**: Schema validation before insertion
- **Uniqueness Checking**: 85% threshold for duplicate detection

### Scraper Architecture
```python
class BaseScraper(ABC):
    def __init__(self, crawler_id, admin_id):
        self.crawler_id = crawler_id
        self.playwright_manager = PlaywrightManager()
        
    async def scrape(self):
        # 1. Initialize browser
        # 2. Navigate to product pages
        # 3. Extract shoe data
        # 4. Download images
        # 5. Process features
        # 6. Batch insert with uniqueness check
        # 7. Update statistics
        pass
```

### Scheduling
- **APScheduler**: Background job scheduling
- **Cron Expressions**: Flexible scheduling
- **Quarterly Auto-Reschedule**: After each run, reschedule for +3 months
- **Calendar UI**: Admin can pick date/time instead of raw cron

**Example:**
```python
# Schedule crawler for March 15, 2025 at 2:00 AM
schedule_cron = "0 2 15 3 *"

# After successful run, auto-reschedules to June 15, 2025 at 2:00 AM
new_schedule_cron = "0 2 15 6 *"
```

## Configuration

### Environment Variables (`.env`)
```env
# Flask
SECRET_KEY=your-super-secret-key-change-this
FLASK_ENV=development
FLASK_DEBUG=True

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/shoe_identifier

# JWT
JWT_SECRET_KEY=your-jwt-secret-change-this
JWT_ACCESS_TOKEN_EXPIRES=3600  # 1 hour
JWT_REFRESH_TOKEN_EXPIRES=2592000  # 30 days

# File Upload
MAX_CONTENT_LENGTH=10485760  # 10MB
UPLOAD_FOLDER=uploads/
ALLOWED_EXTENSIONS=jpg,jpeg,png,webp

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# Scheduler
SCHEDULER_ENABLED=True

# Email (Optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

### Configuration Classes
```python
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    
class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    
class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    # Additional production settings
```

## Security

### Authentication
- **JWT Tokens**: Stateless authentication
- **Password Hashing**: bcrypt with salt rounds=12
- **Token Expiration**: 1 hour access, 30 days refresh
- **MFA Support**: TOTP (Google Authenticator) for admin

### Authorization
- **Role-Based**: User vs Admin roles
- **Route Protection**: @jwt_required() decorator
- **Admin Only**: Separate admin_required middleware

### Input Validation
- **File Upload**: Type, size, magic bytes checking
- **SQL Injection**: Parameterized queries, SQLAlchemy ORM
- **XSS Prevention**: Input sanitization
- **CSRF**: Token validation on state-changing operations

### Rate Limiting
- **Login Attempts**: 5 attempts, exponential backoff
- **API Calls**: 100 requests/minute per user
- **File Uploads**: 10 uploads/hour per user

## Logging

### Log Levels
- **DEBUG**: Detailed information for debugging
- **INFO**: General informational messages
- **WARNING**: Warning messages
- **ERROR**: Error messages
- **CRITICAL**: Critical errors

### Log Format
```
[2025-11-16 10:30:45,123] INFO in routes.auth: User logged in: user@example.com
[2025-11-16 10:31:12,456] ERROR in routes.matches: Image processing failed: FileNotFoundError
```

### Log Rotation
- **Max File Size**: 10MB
- **Backup Count**: 5 files
- **Location**: `logs/app.log`

## Testing

### Unit Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test
pytest tests/test_auth.py
```

### Integration Tests
```bash
# Test API endpoints
pytest tests/integration/test_api.py

# Test scrapers
pytest tests/integration/test_scrapers.py
```

### Manual API Testing
```bash
# Using curl
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'

# Using Postman
# Import collection from tests/postman/
```

## Deployment

### Production Setup

#### 1. Environment
```bash
# Create production .env
cp .env.example .env
# Edit with production values

# Use strong secrets
SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
JWT_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
```

#### 2. Database
```bash
# Create production database
createdb shoe_identifier_prod

# Run migrations
python init_db.py

# Create admin user
python -c "from models import AdminUser; from extensions import db; ..."
```

#### 3. Waitress Server
```bash
# Install Waitress
pip install waitress

# Run production server
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 app:app
```

#### 4. Supervisor (Process Management)
```ini
[program:shoe_api]
command=/path/to/venv/bin/waitress-serve --host=0.0.0.0 --port=5000 app:app
directory=/path/to/backend
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/shoe_api.err.log
stdout_logfile=/var/log/shoe_api.out.log
```

#### 5. Nginx Reverse Proxy
```nginx
server {
    listen 80;
    server_name api.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # SSL configuration (Let's Encrypt)
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
}
```

### Docker Deployment
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 5000

# Run with Waitress
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "app:app"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "5000:5000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/shoe_identifier
      - SECRET_KEY=${SECRET_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      - db
    volumes:
      - ./backend/uploads:/app/uploads
      - ./backend/logs:/app/logs
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=shoe_identifier
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

## Performance Optimization

- **Database Indexing**: B-tree on common queries, IVFFLAT on vectors
- **Connection Pooling**: SQLAlchemy pool size=10, max_overflow=20
- **Caching**: Redis for session storage (optional)
- **Async Operations**: Celery for background tasks (planned)
- **Image Compression**: Optimize uploaded images before storage
- **Query Optimization**: Eager loading, pagination

## Troubleshooting

### Database Connection Error
```
Error: could not connect to server
Solution:
1. Check PostgreSQL is running
2. Verify DATABASE_URL in .env
3. Check firewall/network settings
4. Ensure pgvector extension installed
```

### Image Processing Fails
```
Error: Feature extraction failed
Solution:
1. Check image file integrity
2. Verify OpenCV installed correctly
3. Ensure CLIP model downloaded
4. Check available disk space
5. Review logs for detailed error
```

### Scheduler Not Running
```
Error: Crawlers not executing
Solution:
1. Verify SCHEDULER_ENABLED=True in .env
2. Check scheduler initialized in app.py
3. Validate cron expressions
4. Ensure crawler is_active=True
5. Check logs for scheduler errors
```

## Contributing

### Development Workflow
1. Create feature branch
2. Write tests for new features
3. Implement feature with documentation
4. Run tests and linting
5. Submit pull request

### Code Style
- Follow PEP 8 style guide
- Use type hints where applicable
- Write docstrings for functions/classes
- Keep functions focused and small

## License

Proprietary - All rights reserved

## Support

For issues or questions:
- Review logs: `logs/app.log`
- Check database: `psql shoe_identifier`
- Contact development team

---

**Version:** 1.0.0  
**Last Updated:** November 16, 2025  
**Framework:** Flask 3.0 + SQLAlchemy 2.0  
**Database:** PostgreSQL 15 + pgvector  
**Python:** 3.11+
