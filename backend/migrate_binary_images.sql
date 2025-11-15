-- Migration: Convert group images from file storage to binary database storage
-- This migration updates the user_groups table structure

-- Step 1: Add new binary image columns
ALTER TABLE user_groups 
ADD COLUMN
IF NOT EXISTS profile_image_data BYTEA,
ADD COLUMN
IF NOT EXISTS profile_image_mimetype VARCHAR
(50),
ADD COLUMN
IF NOT EXISTS profile_image_filename VARCHAR
(255);

-- Step 2: Drop old file storage columns (after ensuring data is migrated if needed)
-- Note: Only drop if you've already migrated existing images
-- ALTER TABLE user_groups DROP COLUMN IF EXISTS profile_image_url;
-- ALTER TABLE user_groups DROP COLUMN IF EXISTS profile_image_path;

-- Step 3: Verification queries
SELECT 'Migration completed successfully' AS status;

SELECT
    COUNT(*) as total_groups,
    COUNT(profile_image_data) as groups_with_images
FROM user_groups;

-- Display new column structure
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'user_groups'
    AND column_name LIKE 'profile_image%'
ORDER BY column_name;
