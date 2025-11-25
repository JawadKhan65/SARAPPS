"""
Migration: Convert group images from file storage to binary database storage
This script migrates existing user_groups to use binary image storage
"""

import os
import sys
from sqlalchemy import text
from core.extensions import db
from app import create_app


def migrate_to_binary_storage():
    """Migrate user_groups table to use binary image storage"""

    print("🔄 Starting migration to binary image storage...")

    app = create_app()

    with app.app_context():
        try:
            print("\n📋 Step 1: Adding new binary image columns...")

            # Add new columns
            db.session.execute(
                text("""
                ALTER TABLE user_groups 
                ADD COLUMN IF NOT EXISTS profile_image_data BYTEA,
                ADD COLUMN IF NOT EXISTS profile_image_mimetype VARCHAR(50),
                ADD COLUMN IF NOT EXISTS profile_image_filename VARCHAR(255)
            """)
            )

            db.session.commit()
            print("✅ New columns added")

            print("\n📋 Step 2: Migrating existing image files to database...")

            # Get all groups with file-based images
            result = db.session.execute(
                text("""
                SELECT id, name, profile_image_path, profile_image_url 
                FROM user_groups 
                WHERE profile_image_path IS NOT NULL
            """)
            )

            groups_with_images = result.fetchall()
            migrated_count = 0
            failed_count = 0

            for group_id, name, image_path, image_url in groups_with_images:
                try:
                    if os.path.exists(image_path):
                        # Read image file
                        with open(image_path, "rb") as f:
                            image_data = f.read()

                        # Determine mimetype from extension
                        ext = os.path.splitext(image_path)[1].lower()
                        mimetype_map = {
                            ".png": "image/png",
                            ".jpg": "image/jpeg",
                            ".jpeg": "image/jpeg",
                            ".gif": "image/gif",
                            ".webp": "image/webp",
                        }
                        mimetype = mimetype_map.get(ext, "image/jpeg")

                        # Get filename
                        filename = os.path.basename(image_path)

                        # Update database with binary data
                        db.session.execute(
                            text("""
                                UPDATE user_groups 
                                SET profile_image_data = :data,
                                    profile_image_mimetype = :mimetype,
                                    profile_image_filename = :filename
                                WHERE id = :id
                            """),
                            {
                                "data": image_data,
                                "mimetype": mimetype,
                                "filename": filename,
                                "id": group_id,
                            },
                        )

                        migrated_count += 1
                        print(f"✅ Migrated image for group: {name}")
                    else:
                        print(f"⚠️  Image file not found for group {name}: {image_path}")
                        failed_count += 1

                except Exception as e:
                    print(f"❌ Error migrating image for group {name}: {e}")
                    failed_count += 1

            db.session.commit()

            if migrated_count > 0:
                print(f"\n✅ Successfully migrated {migrated_count} images to database")
            if failed_count > 0:
                print(f"⚠️  Failed to migrate {failed_count} images")

            print("\n📋 Step 3: Checking if old columns can be removed...")

            # Check if all images have been migrated
            result = db.session.execute(
                text("""
                SELECT COUNT(*) 
                FROM user_groups 
                WHERE profile_image_path IS NOT NULL 
                    AND profile_image_data IS NULL
            """)
            )

            pending_count = result.scalar()

            if pending_count == 0:
                print("✅ All images migrated. Old columns can be safely removed.")

                remove = input(
                    "\nDo you want to remove old file storage columns? (yes/no): "
                )
                if remove.lower() == "yes":
                    print("\n📋 Removing old columns...")
                    db.session.execute(
                        text("""
                        ALTER TABLE user_groups 
                        DROP COLUMN IF EXISTS profile_image_url,
                        DROP COLUMN IF EXISTS profile_image_path
                    """)
                    )
                    db.session.commit()
                    print("✅ Old columns removed")
                else:
                    print(
                        "ℹ️  Old columns kept. You can remove them manually later with:"
                    )
                    print(
                        "   ALTER TABLE user_groups DROP COLUMN profile_image_url, DROP COLUMN profile_image_path;"
                    )
            else:
                print(f"⚠️  {pending_count} images still pending migration")
                print("   Old columns will NOT be removed automatically")

            print("\n📋 Step 4: Verifying migration...")

            result = db.session.execute(
                text("""
                SELECT 
                    COUNT(*) as total_groups,
                    COUNT(profile_image_data) as groups_with_binary_images
                FROM user_groups
            """)
            )

            stats = result.fetchone()
            print(f"✅ Total groups: {stats[0]}")
            print(f"✅ Groups with binary images: {stats[1]}")

            print("\n" + "=" * 60)
            print("🎉 Migration completed successfully!")
            print("=" * 60)

            print(
                "\nIMPORTANT: Update your code to use the new image serving endpoint:"
            )
            print("  Old: /uploads/group_images/{filename}")
            print("  New: /api/admin/groups/{group_id}/image")
            print()

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            db.session.rollback()
            raise


if __name__ == "__main__":
    migrate_to_binary_storage()
