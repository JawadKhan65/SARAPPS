# Forgot Password Feature - OTP-Based Reset

## Overview
Implemented a secure password reset flow using OTP (One-Time Password) verification instead of email links. Users receive a 6-digit code via email to verify their identity before resetting their password.

## User Flow

### Step 1: Request Password Reset
1. User clicks "Forgot Password?" on the login page
2. User enters their email address
3. System generates a 6-digit OTP code (valid for 10 minutes)
4. OTP is sent to the user's email
5. User redirected to OTP verification page

### Step 2: Verify OTP
1. User enters the 6-digit code from their email
2. System validates the OTP code
3. If valid, system generates a temporary reset token (valid for 10 minutes)
4. User redirected to password reset page

### Step 3: Reset Password
1. User enters new password (minimum 9 characters)
2. User confirms the new password
3. System updates the password using the reset token
4. Confirmation email sent to user
5. User redirected to login page

## Backend Implementation

### New Endpoints

#### 1. `/api/auth/forgot-password` (POST)
**Purpose:** Request password reset OTP

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response (200):**
```json
{
  "message": "OTP sent to email",
  "email": "user@example.com"
}
```

**Features:**
- Generates 6-digit OTP code using `secrets.randbelow(1000000)`
- OTP valid for 10 minutes
- Stores OTP in `users.otp_code` and expiry in `users.otp_code_expiry`
- Sends HTML email with styled OTP code
- Doesn't reveal if email exists (security best practice)

#### 2. `/api/auth/verify-reset-otp` (POST)
**Purpose:** Verify OTP code for password reset

**Request Body:**
```json
{
  "email": "user@example.com",
  "otp_code": "123456"
}
```

**Response (200):**
```json
{
  "message": "OTP verified",
  "reset_token": "abc123...xyz"
}
```

**Error Responses:**
- `401` - Invalid or expired OTP
- `401` - No OTP request found
- `401` - Invalid credentials

**Features:**
- Validates OTP code against stored value
- Checks expiry time
- Generates temporary reset token (valid 10 minutes)
- Stores token in `users.reset_token` and expiry in `users.reset_token_expiry`

#### 3. `/api/auth/reset-password` (POST)
**Purpose:** Reset password with verified token

**Request Body:**
```json
{
  "reset_token": "abc123...xyz",
  "new_password": "newpassword123"
}
```

**Response (200):**
```json
{
  "message": "Password reset successfully"
}
```

**Features:**
- Validates reset token and expiry
- Enforces minimum 9-character password
- Hashes new password
- Clears reset token and OTP codes
- Sends confirmation email

### Database Changes

Added to `users` table:
```sql
reset_token VARCHAR(255) -- Temporary token after OTP verification
reset_token_expiry TIMESTAMP -- Token expiration time
```

Existing fields used:
```sql
otp_code VARCHAR(6) -- 6-digit OTP code
otp_code_expiry TIMESTAMP -- OTP expiration time
```

### Email Template

Created `backend/templates/password_reset_otp.html`:
- Professional HTML email design
- Large, centered OTP code display
- Expiry time warning (10 minutes)
- Security tips
- Gradient background for OTP box
- Inline logo support (cid:stip_logo)

## Frontend Implementation

### New Page: `/forgot-password`

Created `frontend/app/forgot-password/page.jsx`:

**Features:**
- Three-step wizard interface
- Real-time form validation
- Auto-format OTP input (6 digits, numbers only)
- Resend OTP functionality
- Change email option
- Loading states and error handling
- Success messages with auto-redirect

**Step Components:**

1. **Email Input:**
   - Email validation
   - "Send Verification Code" button
   - Back to login link

2. **OTP Verification:**
   - 6-digit input (auto-formatted, monospace font)
   - Shows email where code was sent
   - "Resend Code" button
   - "Change Email" option

3. **Password Reset:**
   - New password input (min 9 chars)
   - Confirm password input
   - Password match validation
   - Auto-redirect to login after success

### API Integration

Updated `frontend/lib/api.js`:
```javascript
authAPI: {
  forgotPassword: (email) => 
    api.post('/auth/forgot-password', { email }),
  
  verifyResetOTP: (email, otpCode) => 
    api.post('/auth/verify-reset-otp', { email, otp_code: otpCode }),
  
  resetPassword: (resetToken, newPassword) => 
    api.post('/auth/reset-password', { reset_token: resetToken, new_password: newPassword }),
}
```

## Security Features

1. **No Email Enumeration:** System doesn't reveal if email exists
2. **Time-Limited OTP:** 10-minute expiry for OTP codes
3. **Time-Limited Token:** 10-minute expiry for reset tokens
4. **Secure Random Generation:** Uses `secrets.randbelow()` for OTP
5. **Password Hashing:** Uses Werkzeug's `generate_password_hash()`
6. **Cleanup:** Clears OTP and reset tokens after use
7. **Confirmation Email:** User notified of successful password change

## Configuration

**OTP Settings:**
- Code Length: 6 digits
- OTP Expiry: 10 minutes
- Reset Token Expiry: 10 minutes
- Min Password Length: 9 characters

**Email Settings:**
- Subject: "STIP - Password Reset Verification Code"
- Template: `password_reset_otp.html`
- Includes inline logo attachment

## Testing Checklist

- [ ] Request OTP with valid email
- [ ] Check email arrives with correct OTP code
- [ ] Verify OTP code (valid)
- [ ] Verify OTP code (invalid)
- [ ] Verify OTP code (expired - wait 10+ minutes)
- [ ] Reset password with valid token
- [ ] Reset password with expired token
- [ ] Test password validation (< 9 chars)
- [ ] Test password mismatch
- [ ] Test resend OTP functionality
- [ ] Test change email functionality
- [ ] Verify confirmation email sent
- [ ] Test with non-existent email (should not reveal)
- [ ] Check OTP logged in console (development)

## Migration Required

Run the migration script to add reset_token fields:

```bash
cd backend
python migrations/add_reset_token_fields.py
```

Or manually execute SQL:
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expiry TIMESTAMP;
```

## Files Modified/Created

### Backend
- ✅ `routes/auth.py` - Added 3 new endpoints
- ✅ `models.py` - Added reset_token fields to User model
- ✅ `templates/password_reset_otp.html` - New email template
- ✅ `migrations/add_reset_token_fields.py` - New migration script

### Frontend
- ✅ `app/forgot-password/page.jsx` - New password reset page
- ✅ `lib/api.js` - Added forgotPassword, verifyResetOTP, resetPassword functions
- ✅ `app/login/page.jsx` - Already has "Forgot Password?" link

## Usage

1. **Start the backend:**
   ```bash
   cd backend
   python app.py
   ```

2. **Run migration:**
   ```bash
   python migrations/add_reset_token_fields.py
   ```

3. **Start the frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

4. **Access forgot password:**
   - Navigate to http://localhost:3000/login
   - Click "Forgot Password?" link
   - Follow the 3-step process

## Future Enhancements

- [ ] Rate limiting for OTP requests (prevent spam)
- [ ] SMS OTP option alongside email
- [ ] Remember device after successful reset
- [ ] Password strength meter on reset page
- [ ] Breach password checking (HaveIBeenPwned API)
- [ ] Account recovery questions as backup
- [ ] Admin notification for suspicious reset attempts
- [ ] Configurable OTP expiry time in settings
