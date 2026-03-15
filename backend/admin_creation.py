import sys
import os
from werkzeug.security import generate_password_hash
from core.extensions import db
from core.models import AdminUser
from app import create_app
import uuid

def create_admins():
    app = create_app()
    with app.app_context():
        # Get admins from environment or use empty list
        # Format: ADMIN_USERS=username1:email1:password1,username2:email2:password2
        admin_env = os.getenv('ADMIN_USERS', '')
        if not admin_env:
            print('⚠️  ADMIN_USERS environment variable not set. Skipping admin creation.')
            print('   Set ADMIN_USERS=username:email:password to create admins.')
            return
        
        admins = []
        for admin_str in admin_env.split(','):
            parts = admin_str.strip().split(':')
            if len(parts) == 3:
                admins.append({
                    'username': parts[0],
                    'email': parts[1],
                    'password': parts[2]
                })
        for admin_data in admins:
            try:
                existing = AdminUser.query.filter_by(email=admin_data['email']).first()
                if existing:
                    print(f"⚠️  {admin_data['email']} exists, skipping...")
                    continue
                admin = AdminUser(
                    id=str(uuid.uuid4()),
                    username=admin_data['username'],
                    email=admin_data['email'],
                    password_hash=generate_password_hash(admin_data['password']),
                    is_active=True,
                    mfa_enabled=False
                )
                db.session.add(admin)
                db.session.commit()
                print(f"✅ Created: {admin_data['email']}")
            except Exception as e:
                print(f"❌ Error: {e}")
                db.session.rollback()

if __name__ == '__main__':
    create_admins()