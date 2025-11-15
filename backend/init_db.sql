-- ============================================================================
-- Advanced Print Match System - Database Initialization Script
-- ============================================================================
-- This script initializes the PostgreSQL database with all required tables,
-- indexes, and extensions for the Shoe Identifier system.
--
-- Prerequisites:
-- - PostgreSQL 14+ installed
-- - pgvector extension available
-- - Database created
--
-- Usage:
-- psql -U postgres -d shoe_identifier -f init_db.sql
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pgvector;
CREATE EXTENSION IF NOT EXISTS uuid-ossp;

-- ============================================================================
-- USERS TABLE (without group_id initially)
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    
    -- Account Status
    is_active BOOLEAN DEFAULT true,
    is_deleted BOOLEAN DEFAULT false,
    
    -- Profile
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    avatar_url TEXT,
    bio TEXT,
    
    -- Preferences
    dark_mode BOOLEAN DEFAULT true,
    language VARCHAR(10) DEFAULT 'en',
    
    -- Security
    remember_token VARCHAR(255),
    trusted_devices JSONB DEFAULT '[]'::jsonb,
    failed_login_attempts INTEGER DEFAULT 0,
    last_failed_login TIMESTAMP,
    
    -- MFA
    mfa_enabled BOOLEAN DEFAULT false,
    mfa_secret VARCHAR(32),
    mfa_backup_codes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    last_login_ip INET,
    
    -- Storage
    storage_used_mb FLOAT DEFAULT 0.0,
    
    -- Role (user, admin)
    role VARCHAR(20) DEFAULT 'user'
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_is_active ON users(is_active);
CREATE INDEX idx_users_created_at ON users(created_at);

-- ============================================================================
-- UPLOADED IMAGES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS uploaded_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Image metadata
    filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    mime_type VARCHAR(50),
    
    -- Dimensions
    width INTEGER,
    height INTEGER,
    
    -- Processing
    is_processed BOOLEAN DEFAULT false,
    processing_status VARCHAR(50) DEFAULT 'pending',
    processing_error TEXT,
    
    -- Features
    features_vector vector(512),
    lbp_features FLOAT8[],
    edge_features FLOAT8[],
    color_features FLOAT8[],
    clip_embedding vector(512),
    line_tracing_features FLOAT8[],
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE INDEX idx_uploaded_images_user_id ON uploaded_images(user_id);
CREATE INDEX idx_uploaded_images_created_at ON uploaded_images(created_at);
CREATE INDEX idx_uploaded_images_is_processed ON uploaded_images(is_processed);
CREATE INDEX idx_uploaded_images_features_vector ON uploaded_images USING IVFFLAT (features_vector vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_uploaded_images_clip_embedding ON uploaded_images USING IVFFLAT (clip_embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- SHOES TABLE (Product Database)
-- ============================================================================
CREATE TABLE IF NOT EXISTS shoes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Basic Info
    brand VARCHAR(255) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    shoe_type VARCHAR(100),
    description TEXT,
    
    -- Physical Properties
    color VARCHAR(100),
    size VARCHAR(20),
    material VARCHAR(100),
    
    -- Source Info
    source VARCHAR(100),
    source_id VARCHAR(255),
    source_url TEXT,
    
    -- Image
    image_url TEXT,
    
    -- Features (from sole analysis)
    features_vector vector(512),
    clip_embedding vector(512),
    lbp_features FLOAT8[],
    edge_features FLOAT8[],
    color_features FLOAT8[],
    line_tracing_features FLOAT8[],
    
    -- Metadata
    is_available BOOLEAN DEFAULT true,
    price DECIMAL(10, 2),
    rating FLOAT DEFAULT 0.0,
    review_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scraped TIMESTAMP
);

CREATE INDEX idx_shoes_brand ON shoes(brand);
CREATE INDEX idx_shoes_product_name ON shoes(product_name);
CREATE INDEX idx_shoes_shoe_type ON shoes(shoe_type);
CREATE INDEX idx_shoes_source ON shoes(source);
CREATE INDEX idx_shoes_is_available ON shoes(is_available);
CREATE INDEX idx_shoes_features_vector ON shoes USING IVFFLAT (features_vector vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_shoes_clip_embedding ON shoes USING IVFFLAT (clip_embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- MATCH RESULTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS match_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    image_id UUID NOT NULL REFERENCES uploaded_images(id) ON DELETE CASCADE,
    shoe_id UUID NOT NULL REFERENCES shoes(id) ON DELETE SET NULL,
    
    -- Similarity Scores
    overall_similarity FLOAT NOT NULL,
    cosine_similarity FLOAT,
    orb_similarity FLOAT,
    clip_similarity FLOAT,
    
    -- Confidence Tier
    confidence_tier VARCHAR(20),
    
    -- Match Metadata
    matched_brand VARCHAR(255),
    matched_product_name VARCHAR(255),
    matched_shoe_type VARCHAR(100),
    
    -- User Feedback
    user_confirmed BOOLEAN DEFAULT false,
    user_rejected BOOLEAN DEFAULT false,
    user_feedback TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_match_results_user_id ON match_results(user_id);
CREATE INDEX idx_match_results_image_id ON match_results(image_id);
CREATE INDEX idx_match_results_shoe_id ON match_results(shoe_id);
CREATE INDEX idx_match_results_similarity ON match_results(overall_similarity DESC);
CREATE INDEX idx_match_results_created_at ON match_results(created_at);
CREATE INDEX idx_match_results_confidence_tier ON match_results(confidence_tier);

-- ============================================================================
-- CRAWLER HISTORY TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS crawler_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Crawler Info
    crawler_name VARCHAR(255) NOT NULL,
    crawler_url TEXT NOT NULL,
    
    -- Execution Details
    status VARCHAR(50),
    items_scraped INTEGER DEFAULT 0,
    items_processed INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    
    -- Performance
    execution_time_seconds INTEGER,
    error_message TEXT,
    
    -- Timestamps
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_crawler_history_crawler_name ON crawler_history(crawler_name);
CREATE INDEX idx_crawler_history_status ON crawler_history(status);
CREATE INDEX idx_crawler_history_created_at ON crawler_history(created_at);

-- ============================================================================
-- SYSTEM LOGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Log Details
    level VARCHAR(20),
    message TEXT,
    source VARCHAR(255),
    
    -- Context
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    request_id VARCHAR(255),
    ip_address INET,
    
    -- Timestamp
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_system_logs_level ON system_logs(level);
CREATE INDEX idx_system_logs_created_at ON system_logs(created_at);
CREATE INDEX idx_system_logs_user_id ON system_logs(user_id);

-- ============================================================================
-- AUDIT LOGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Action Details
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    
    -- Actor
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    actor_email VARCHAR(255),
    
    -- Changes
    changes JSONB,
    old_values JSONB,
    new_values JSONB,
    
    -- Metadata
    ip_address INET,
    user_agent TEXT,
    
    -- Timestamp
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_actor_id ON audit_logs(actor_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- ============================================================================
-- CRAWLER STATUS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS crawler_status (
    id SERIAL PRIMARY KEY,
    
    -- Crawler Info
    crawler_name VARCHAR(255) UNIQUE NOT NULL,
    crawler_url TEXT,
    
    -- Current Status
    is_running BOOLEAN DEFAULT false,
    current_progress INTEGER DEFAULT 0,
    last_run TIMESTAMP,
    last_error TEXT,
    
    -- Statistics
    total_items_scraped BIGINT DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    
    -- Configuration
    is_enabled BOOLEAN DEFAULT true,
    frequency_hours INTEGER DEFAULT 24,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_crawler_status_name ON crawler_status(crawler_name);
CREATE INDEX idx_crawler_status_is_running ON crawler_status(is_running);

-- ============================================================================
-- SESSION TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Session Details
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    refresh_token_hash VARCHAR(255),
    
    -- Device Info
    device_fingerprint VARCHAR(255),
    user_agent TEXT,
    ip_address INET,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    last_activity TIMESTAMP
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_is_active ON sessions(is_active);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);

-- ============================================================================
-- ADMIN USERS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    
    -- Admin Level (super, full, limited)
    admin_level VARCHAR(20) DEFAULT 'limited',
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Permissions
    permissions JSONB DEFAULT '{}'::jsonb,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX idx_admin_users_email ON admin_users(email);
CREATE INDEX idx_admin_users_is_active ON admin_users(is_active);

-- ============================================================================
-- USER GROUPS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    
    -- Profile image stored as binary data
    profile_image_data BYTEA,  -- Binary image data
    profile_image_mimetype VARCHAR(50),  -- e.g., 'image/png', 'image/jpeg'
    profile_image_filename VARCHAR(255),  -- Original filename
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_groups_name ON user_groups(name);
CREATE INDEX idx_user_groups_created_by ON user_groups(created_by);

-- Add group_id column to users table (after user_groups is created)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'group_id'
    ) THEN
        ALTER TABLE users ADD COLUMN group_id UUID REFERENCES user_groups(id) ON DELETE SET NULL;
        CREATE INDEX idx_users_group_id ON users(group_id);
    END IF;
END $$;

-- ============================================================================
-- DEFAULT DATA INSERTION
-- ============================================================================

-- Insert default admin user (password: admin123)
-- Hash should be bcrypt(admin123) in production
INSERT INTO admin_users (id, email, password_hash, admin_level, is_active)
VALUES (
    uuid_generate_v4(),
    'admin@shoeidentifier.local',
    '$2b$12$8Zx7yZ3mK5j8vL2qP9nN9eJ1m3k5L7z9X2b4D6f8H0j2L4n6P8r0S',
    'super',
    true
)
ON CONFLICT (email) DO NOTHING;

-- Insert sample crawlers
INSERT INTO crawler_status (crawler_name, crawler_url, is_enabled, frequency_hours)
VALUES
    ('Nike Crawler', 'https://www.nike.com', true, 24),
    ('Adidas Crawler', 'https://www.adidas.com', true, 24),
    ('Puma Crawler', 'https://www.puma.com', true, 24),
    ('New Balance Crawler', 'https://www.newbalance.com', true, 24),
    ('Converse Crawler', 'https://www.converse.com', true, 24)
ON CONFLICT (crawler_name) DO NOTHING;

-- ============================================================================
-- VIEWS FOR ANALYTICS
-- ============================================================================

CREATE OR REPLACE VIEW user_statistics AS
SELECT
    COUNT(DISTINCT u.id) as total_users,
    COUNT(DISTINCT CASE WHEN u.is_active = true THEN u.id END) as active_users,
    COUNT(DISTINCT CASE WHEN u.created_at >= CURRENT_DATE - INTERVAL '30 days' THEN u.id END) as active_last_30_days,
    COUNT(DISTINCT CASE WHEN u.is_active = false THEN u.id END) as blocked_users,
    COUNT(DISTINCT CASE WHEN DATE(u.created_at) = CURRENT_DATE THEN u.id END) as new_users_today,
    COUNT(DISTINCT CASE WHEN DATE(u.created_at) >= DATE_TRUNC('month', CURRENT_DATE) THEN u.id END) as new_users_this_month
FROM users u;

CREATE OR REPLACE VIEW match_statistics AS
SELECT
    COUNT(*) as total_matches,
    AVG(overall_similarity) as avg_similarity,
    COUNT(DISTINCT CASE WHEN overall_similarity > 0.9 THEN id END) as perfect_matches,
    COUNT(DISTINCT CASE WHEN overall_similarity BETWEEN 0.75 AND 0.9 THEN id END) as high_confidence_matches,
    COUNT(DISTINCT CASE WHEN overall_similarity BETWEEN 0.6 AND 0.75 THEN id END) as possible_matches,
    COUNT(DISTINCT CASE WHEN overall_similarity < 0.6 THEN id END) as low_confidence_matches
FROM match_results;

CREATE OR REPLACE VIEW crawler_statistics AS
SELECT
    COUNT(DISTINCT crawler_name) as total_crawlers,
    COUNT(DISTINCT CASE WHEN is_running = true THEN crawler_name END) as active_crawlers,
    SUM(total_items_scraped) as total_items_scraped,
    AVG(CASE WHEN (success_count + failure_count) > 0 
            THEN (success_count::float / (success_count + failure_count)) 
            ELSE 0 END) as avg_success_rate
FROM crawler_status;

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function to update user storage
CREATE OR REPLACE FUNCTION update_user_storage(p_user_id UUID, p_file_size_bytes INTEGER)
RETURNS void AS $$
BEGIN
    UPDATE users
    SET storage_used_mb = storage_used_mb + (p_file_size_bytes::float / 1024 / 1024)
    WHERE id = p_user_id;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate match confidence tier
CREATE OR REPLACE FUNCTION calculate_confidence_tier(p_similarity FLOAT)
RETURNS VARCHAR AS $$
BEGIN
    IF p_similarity > 0.9 THEN
        RETURN 'perfect_match';
    ELSIF p_similarity > 0.75 THEN
        RETURN 'high_confidence';
    ELSIF p_similarity > 0.6 THEN
        RETURN 'possible_match';
    ELSE
        RETURN 'low_confidence';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PERMISSIONS & GRANTS
-- ============================================================================

-- Create role for application
CREATE ROLE shoe_app WITH PASSWORD 'ShoeApp123!' LOGIN;

-- Grant permissions
GRANT CONNECT ON DATABASE shoe_identifier TO shoe_app;
GRANT USAGE ON SCHEMA public TO shoe_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO shoe_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO shoe_app;

-- ============================================================================
-- CLEANUP & OPTIMIZATION
-- ============================================================================

-- Analyze all tables
ANALYZE;

-- Set proper table settings
ALTER TABLE users SET (fillfactor = 70);
ALTER TABLE uploaded_images SET (fillfactor = 70);
ALTER TABLE shoes SET (fillfactor = 70);
ALTER TABLE match_results SET (fillfactor = 70);

-- ============================================================================
-- INITIALIZATION COMPLETE
-- ============================================================================

\echo 'Database initialization complete!'
\echo 'Created tables:'
\echo '  - users'
\echo '  - uploaded_images'
\echo '  - shoes'
\echo '  - match_results'
\echo '  - crawler_history'
\echo '  - system_logs'
\echo '  - audit_logs'
\echo '  - crawler_status'
\echo '  - sessions'
\echo '  - admin_users'
\echo ''
\echo 'Created views:'
\echo '  - user_statistics'
\echo '  - match_statistics'
\echo '  - crawler_statistics'
\echo ''
\echo 'Default admin user created:'
\echo '  Email: admin@shoeidentifier.local'
\echo '  Password: admin123 (change on first login)'
\echo ''
\echo 'Sample crawlers initialized'
\echo 'pgvector extension enabled for vector similarity search'
