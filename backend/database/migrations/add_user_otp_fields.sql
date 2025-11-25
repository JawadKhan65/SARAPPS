-- Migration: Add OTP fields to users table for login verification
-- Date: 2025-11-18
-- Description: Adds otp_code and otp_code_expiry columns to support OTP-based login

-- Add OTP code field (6-digit string)
ALTER TABLE users ADD COLUMN
IF NOT EXISTS otp_code VARCHAR
(6);

-- Add OTP code expiry timestamp
ALTER TABLE users ADD COLUMN
IF NOT EXISTS otp_code_expiry TIMESTAMP;

-- Add comments for documentation
COMMENT ON COLUMN users.otp_code IS 'One-time password for login verification (6 digits)';
COMMENT ON COLUMN users.otp_code_expiry IS 'Expiry timestamp for the OTP code (5 minutes from generation)';
