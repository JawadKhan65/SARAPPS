import firebase_admin
from firebase_admin import credentials, auth, firestore
import os
from datetime import datetime

# Initialize Firebase Admin SDK
cred_path = os.path.join(os.path.dirname(__file__), "firebase-admin-key.json")

try:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase Admin SDK initialized successfully")
except Exception as e:
    print(f"❌ Failed to initialize Firebase Admin SDK: {e}")
    db = None


def verify_firebase_token(id_token):
    """Verify Firebase ID token and return decoded token"""
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        print(f"Error verifying Firebase token: {e}")
        return None


def get_user_by_email(email):
    """Get Firebase user by email"""
    try:
        user = auth.get_user_by_email(email)
        return user
    except Exception as e:
        print(f"Error getting user by email: {e}")
        return None


def create_firebase_user(email, password):
    """Create a new Firebase user"""
    try:
        user = auth.create_user(email=email, password=password, email_verified=False)
        return user
    except Exception as e:
        print(f"Error creating Firebase user: {e}")
        return None


def delete_firebase_user(uid):
    """Delete a Firebase user"""
    try:
        auth.delete_user(uid)
        return True
    except Exception as e:
        print(f"Error deleting Firebase user: {e}")
        return False


def send_email_via_firebase(to_email, subject, text_body, html_body=None):
    """
    Send email via Firebase by writing to Firestore mail collection.
    Requires Firebase Extension: Trigger Email from Firestore
    https://extensions.dev/extensions/firebase/firestore-send-email

    Args:
        to_email: Recipient email address
        subject: Email subject
        text_body: Plain text email body
        html_body: Optional HTML email body

    Returns:
        bool: True if email was queued successfully, False otherwise
    """
    if not db:
        print("❌ Firestore not initialized, cannot send email")
        return False

    try:
        email_data = {
            "to": [to_email],
            "message": {
                "subject": subject,
                "text": text_body,
            },
            "created_at": datetime.utcnow(),
        }

        # Add HTML body if provided
        if html_body:
            email_data["message"]["html"] = html_body

        # Write to Firestore 'mail' collection - Firebase extension will trigger email
        doc_ref = db.collection("mail").add(email_data)
        print(f"✅ Email queued in Firestore for {to_email}: {doc_ref[1].id}")
        return True

    except Exception as e:
        print(f"❌ Error queuing email via Firebase: {e}")
        return False


def update_firebase_user(uid, **kwargs):
    """Update Firebase user properties"""
    try:
        auth.update_user(uid, **kwargs)
        return True
    except Exception as e:
        print(f"Error updating Firebase user: {e}")
        return False


def send_password_reset_email(email):
    """Generate password reset link"""
    try:
        link = auth.generate_password_reset_link(email)
        return link
    except Exception as e:
        print(f"Error generating password reset link: {e}")
        return None


def enable_mfa_for_user(uid):
    """Enable MFA for a user"""
    try:
        # Firebase MFA is handled client-side
        # This is a placeholder for backend tracking
        return True
    except Exception as e:
        print(f"Error enabling MFA: {e}")
        return False
