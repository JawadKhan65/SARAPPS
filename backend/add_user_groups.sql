-- ============================================================================
-- Migration Script: Add User Groups Feature
-- ============================================================================
-- This script adds user groups functionality to existing database
-- Run this if you already have data and don't want to reset everything
--
-- Usage:
-- psql -U postgres -d shoe_identifier -f add_user_groups.sql
-- ============================================================================

-- Step 1: Create user_groups table
CREATE TABLE
IF NOT EXISTS user_groups
(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4
(),
    name VARCHAR
(100) UNIQUE NOT NULL,
    description TEXT,
    
    -- Profile image
    profile_image_url VARCHAR
(500),
    profile_image_path VARCHAR
(500),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES admin_users
(id) ON
DELETE
SET NULL
,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Step 2: Create indexes for user_groups
CREATE INDEX
IF NOT EXISTS idx_user_groups_name ON user_groups
(name);
CREATE INDEX
IF NOT EXISTS idx_user_groups_created_by ON user_groups
(created_by);

-- Step 3: Add group_id column to users table
DO $$ 
BEGIN
    -- Check if column exists
    IF NOT EXISTS (
        SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'group_id'
    ) THEN
    -- Add the column
    ALTER TABLE users ADD COLUMN group_id UUID;

-- Add foreign key constraint
ALTER TABLE users ADD CONSTRAINT fk_users_group 
            FOREIGN KEY (group_id) REFERENCES user_groups(id) ON DELETE SET NULL;

-- Add index
CREATE INDEX idx_users_group_id ON users(group_id);

RAISE NOTICE 'Added group_id column to users table';
    ELSE
        RAISE NOTICE 'group_id column already exists in users table';
END
IF;
END $$;

-- Step 4: Create sample groups (optional - comment out if not needed)
-- INSERT INTO user_groups (name, description) 
-- VALUES 
--     ('Premium Users', 'Users with premium subscription'),
--     ('Beta Testers', 'Users testing new features'),
--     ('VIP Members', 'VIP members with exclusive access')
-- ON CONFLICT (name) DO NOTHING;

-- Verify the changes
    SELECT
        'user_groups table' as table_name,
        COUNT(*) as record_count
    FROM user_groups
UNION ALL
    SELECT
        'users with groups' as table_name,
        COUNT(*) as record_count
    FROM users
    WHERE group_id IS NOT NULL;

-- Show column information
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'users' AND column_name = 'group_id';

RAISE NOTICE 'Migration completed successfully!';
