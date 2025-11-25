'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { authAPI } from '../../lib/api';

export default function ForgotPasswordPage() {
    const router = useRouter();
    const [step, setStep] = useState(1); // 1: Email, 2: OTP, 3: New Password
    const [email, setEmail] = useState('');
    const [otpCode, setOtpCode] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [resetToken, setResetToken] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');

    const handleSendOTP = async (e) => {
        e.preventDefault();
        setError('');
        setMessage('');
        setLoading(true);

        try {
            const response = await authAPI.forgotPassword(email);
            setMessage('Verification code sent to your email');
            setStep(2);
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to send verification code');
        } finally {
            setLoading(false);
        }
    };

    const handleVerifyOTP = async (e) => {
        e.preventDefault();
        setError('');
        setMessage('');
        setLoading(true);

        try {
            const response = await authAPI.verifyResetOTP(email, otpCode);
            setResetToken(response.data.reset_token);
            setMessage('OTP verified! Enter your new password');
            setStep(3);
        } catch (err) {
            setError(err.response?.data?.error || 'Invalid or expired OTP code. Please try again.');
            // Clear OTP input to allow user to try again
            setOtpCode('');
        } finally {
            setLoading(false);
        }
    };

    const handleResetPassword = async (e) => {
        e.preventDefault();
        setError('');
        setMessage('');

        if (newPassword.length < 9) {
            setError('Password must be at least 9 characters');
            return;
        }

        if (newPassword !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        setLoading(true);

        try {
            await authAPI.resetPassword(resetToken, newPassword);
            setMessage('Password reset successfully! Redirecting to login...');
            setTimeout(() => {
                router.push('/login');
            }, 2000);
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to reset password');
        } finally {
            setLoading(false);
        }
    };

    const handleResendOTP = async () => {
        setError('');
        setMessage('');
        setLoading(true);

        try {
            await authAPI.forgotPassword(email);
            setMessage('New verification code sent to your email');
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to resend code');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-purple-50 to-pink-50 flex items-center justify-center p-4 relative overflow-hidden">
            {/* Animated background elements */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-20 left-10 w-72 h-72 bg-blue-400 rounded-full mix-blend-multiply filter blur-xl opacity-20 animate-blob"></div>
                <div className="absolute top-40 right-10 w-72 h-72 bg-purple-400 rounded-full mix-blend-multiply filter blur-xl opacity-20 animate-blob animation-delay-2000"></div>
                <div className="absolute bottom-20 left-1/2 w-72 h-72 bg-pink-400 rounded-full mix-blend-multiply filter blur-xl opacity-20 animate-blob animation-delay-4000"></div>
            </div>

            <div className="relative bg-white/90 backdrop-blur-xl rounded-3xl shadow-2xl w-full max-w-md border border-gray-100">
                <div className="p-8 sm:p-10">
                    <div className="text-center mb-8">
                        <h1 className="text-3xl font-bold text-gray-900 mb-3">
                            Reset Password
                        </h1>
                        <p className="text-gray-500 text-sm">
                            {step === 1 && "Enter your email to receive a verification code"}
                            {step === 2 && "Enter the 6-digit code sent to your email"}
                            {step === 3 && "Create your new password"}
                        </p>
                    </div>

                    {error && (
                        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                            <p className="text-sm text-red-600">{error}</p>
                        </div>
                    )}

                    {message && (
                        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg">
                            <p className="text-sm text-green-600">{message}</p>
                        </div>
                    )}

                    {/* Step 1: Enter Email */}
                    {step === 1 && (
                        <form onSubmit={handleSendOTP} className="space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-900 mb-2">
                                    Email Address
                                </label>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-gray-900"
                                    placeholder="your@email.com"
                                />
                            </div>

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                            >
                                {loading ? 'Sending...' : 'Send Verification Code'}
                            </button>

                            <div className="text-center">
                                <Link
                                    href="/login"
                                    className="text-sm text-blue-600 hover:text-blue-700 font-medium inline-flex items-center gap-1"
                                >
                                    <span>←</span> Back to Login
                                </Link>
                            </div>
                        </form>
                    )}

                    {/* Step 2: Enter OTP */}
                    {step === 2 && (
                        <form onSubmit={handleVerifyOTP} className="space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Verification Code
                                </label>
                                <input
                                    type="text"
                                    value={otpCode}
                                    onChange={(e) => {
                                        setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6));
                                        setError('');
                                        setMessage('');
                                    }}
                                    required
                                    maxLength={6}
                                    className="w-full px-4 py-3 border border-gray-300 rounded-lg text-center text-2xl font-mono tracking-widest focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                                    placeholder="000000"
                                />
                                <p className="text-xs text-gray-500 mt-2 text-center">
                                    Code sent to {email}
                                </p>
                            </div>

                            <button
                                type="submit"
                                disabled={loading || otpCode.length !== 6}
                                className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {loading ? 'Verifying...' : 'Verify Code'}
                            </button>

                            <div className="text-center space-y-2">
                                <button
                                    type="button"
                                    onClick={handleResendOTP}
                                    disabled={loading}
                                    className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
                                >
                                    Resend Code
                                </button>
                                <br />
                                <button
                                    type="button"
                                    onClick={() => setStep(1)}
                                    className="text-sm text-gray-600 hover:text-gray-800"
                                >
                                    ← Change Email
                                </button>
                            </div>
                        </form>
                    )}

                    {/* Step 3: Set New Password */}
                    {step === 3 && (
                        <form onSubmit={handleResetPassword} className="space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-900 mb-2">
                                    New Password
                                </label>
                                <input
                                    type="password"
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    required
                                    minLength={9}
                                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-gray-900"
                                    placeholder="At least 9 characters"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-900 mb-2">
                                    Confirm Password
                                </label>
                                <input
                                    type="password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    required
                                    minLength={9}
                                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-gray-900"
                                    placeholder="Re-enter your password"
                                />
                            </div>

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {loading ? 'Resetting...' : 'Reset Password'}
                            </button>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
}
