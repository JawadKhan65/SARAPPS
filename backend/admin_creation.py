import sys
from werkzeug.security import generate_password_hash
from core.extensions import db
from core.models import AdminUser
from app import create_app
import uuid

def create_admins():
    app = create_app()
    with app.app_context():
        admins = [
            {'username': 'mike_april', 'email': 'mikebravens26april@gmail.com', 'password': 'admin123'},
            {'username': 'mike_vdsman', 'email': 'mikevdsman@gmail.com', 'password': 'admin123'},
            {'username': 'keytalk_admin', 'email': 'm.vandersman@keytalk.com', 'password': 'admin123'},
            {'username': 'sarapps_admin', 'email': 'admin@sarapps.com', 'password': 'admin123'}
        ]
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