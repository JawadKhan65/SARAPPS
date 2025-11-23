-- ============================================================================
-- Reset Sole Images for Line Tracing Integration
-- ============================================================================
-- This script clears all sole images and match results so they can be
-- reprocessed with the new process_reference_sole() function.
--
-- Usage:
-- psql -U postgres -d shoe_identifier -f reset_sole_images.sql
-- ============================================================================

-- Disable foreign key checks temporarily
SET session_replication_role
= 'replica';

-- Clear match results first (has foreign keys to uploaded_images and sole_images)
TRUNCATE TABLE match_results
CASCADE;

-- Clear uploaded images and their matches
TRUNCATE TABLE uploaded_images
CASCADE;

-- Clear sole images (the main table to reset)
TRUNCATE TABLE sole_images
CASCADE;

-- Clear crawler statistics (optional - keeps crawler definitions)
TRUNCATE TABLE crawler_statistics
CASCADE;

-- Re-enable foreign key checks
SET session_replication_role
= 'origin';

-- Verify counts
    SELECT 'sole_images' as table_name, COUNT(*) as count
    FROM sole_images
UNION ALL
    SELECT 'uploaded_images', COUNT(*)
    FROM uploaded_images
UNION ALL
    SELECT 'match_results', COUNT(*)
    FROM match_results
UNION ALL
    SELECT 'crawler_statistics', COUNT(*)
    FROM crawler_statistics;

-- Show remaining crawlers (should still exist)
SELECT id, name, base_url, is_active
FROM crawlers
ORDER BY name;

SELECT 'Database reset complete. Ready to scrape with process_reference_sole()' as status;
