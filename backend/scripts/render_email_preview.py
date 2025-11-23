import os
from datetime import datetime
from app import create_app
from flask import render_template

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "rendered_emails")


def ensure_outdir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def write_html(name: str, html: str):
    ensure_outdir()
    path = os.path.join(OUTPUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote: {os.path.abspath(path)} (length: {len(html)} chars)")


def main():
    app = create_app()
    with app.app_context():
        # Render login notification
        login_html = render_template(
            "login_notification.html",
            username="preview_user",
            login_time=datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC"),
            ip_address="127.0.0.1",
            device="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        )
        write_html("login_notification.html", login_html)

        # Render logout notification
        logout_html = render_template(
            "logout_notification.html",
            username="preview_user",
            logout_time=datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC"),
            ip_address="127.0.0.1",
        )
        write_html("logout_notification.html", logout_html)

        # Render OTP email
        otp_html = render_template(
            "otp_email.html",
            username="preview_admin",
            otp_code="123456",
            expiry_minutes=5,
        )
        write_html("otp_email.html", otp_html)


if __name__ == "__main__":
    main()
