'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { useAuthStore } from '@/lib/store';
import { useToast } from '@/components/ui/Toast';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';

function LoginPageContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const toast = useToast();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [rememberMe, setRememberMe] = useState(false);
    const [errors, setErrors] = useState({});
    const [otpRequired, setOtpRequired] = useState(false);
    const [otpCode, setOtpCode] = useState('');
    const [otpError, setOtpError] = useState('');
    const [resendingOtp, setResendingOtp] = useState(false);
    const { login, verifyOtp, isLoading, error, setError } = useAuthStore();

    const redirect = searchParams.get('redirect') || '/dashboard';

    useEffect(() => {
        // Load remembered email
        const savedEmail = localStorage.getItem('rememberEmail');
        if (savedEmail) {
            setEmail(savedEmail);
            setRememberMe(true);
        }
    }, []);

    const MAX_PASSWORD_LENGTH = 64;
    const MIN_PASSWORD_LENGTH = 9;

    const validateForm = () => {
        const newErrors = {};

        if (!email) {
            newErrors.email = 'Email is required';
        } else if (!/\S+@\S+\.\S+/.test(email)) {
            newErrors.email = 'Email is invalid';
        }

        if (!password) {
            newErrors.password = 'Password is required';
        } else if (password.length < MIN_PASSWORD_LENGTH) {
            newErrors.password = `Password must be at least ${MIN_PASSWORD_LENGTH} characters`;
        } else if (password.length > MAX_PASSWORD_LENGTH) {
            newErrors.password = `Password must be at most ${MAX_PASSWORD_LENGTH} characters`;
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        // Validate form
        if (!validateForm()) {
            toast.error('Please fix the errors in the form');
            return;
        }

        try {
            const result = await login(email, password);

            // Check if OTP is required
            if (result?.otp_required) {
                setOtpRequired(true);
                toast.success('Verification code sent to your email');
                return;
            }

            // Save email if remember me is checked
            if (rememberMe) {
                localStorage.setItem('rememberEmail', email);
            } else {
                localStorage.removeItem('rememberEmail');
            }

            toast.success('Welcome back! Redirecting...');

            // Redirect after short delay for toast to show
            setTimeout(() => {
                router.push(redirect);
            }, 500);
        } catch (error) {
            toast.error(error.message || 'Invalid email or password');
            console.error('Login failed:', error);
        }
    };

    const handleOtpSubmit = async (e) => {
        e.preventDefault();

        if (!otpCode || otpCode.length !== 6) {
            setOtpError('Please enter a valid 6-digit code');
            toast.error('Please enter a valid 6-digit code');
            return;
        }

        try {
            setOtpError('');
            await verifyOtp(email, otpCode, rememberMe);

            // Save email if remember me is checked
            if (rememberMe) {
                localStorage.setItem('rememberEmail', email);
            } else {
                localStorage.removeItem('rememberEmail');
            }

            toast.success('Welcome back! Redirecting...');

            // Redirect after short delay for toast to show
            setTimeout(() => {
                router.push(redirect);
            }, 500);
        } catch (error) {
            // Keep OTP screen visible and show error
            const errorMessage = error.response?.data?.message || error.message || 'Invalid verification code. Please try again.';
            setOtpError(errorMessage);
            toast.error(errorMessage);
            // Clear the OTP input so user can try again
            setOtpCode('');
            console.error('OTP verification failed:', error);
        }
    };

    const handleResendOtp = async () => {
        setResendingOtp(true);
        setOtpError('');
        try {
            // Re-trigger login to get a new OTP
            const result = await login(email, password);
            if (result?.otp_required) {
                toast.success('New verification code sent to your email');
                setOtpCode('');
            }
        } catch (error) {
            toast.error('Failed to resend code. Please try again.');
        } finally {
            setResendingOtp(false);
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

            <div className="relative bg-white/90 backdrop-blur-xl rounded-3xl shadow-2xl w-full max-w-md border border-gray-100 animate-fade-in">
                <div className="p-8 sm:p-10">
                    {/* Logo and Title */}
                    <div className="text-center mb-8">
                        <div className="flex justify-center mb-4">
                            <Image
                                src="/SAR-Apps-logo.png"
                                alt="SAR Apps"
                                width={60}
                                height={60}
                                className="rounded-2xl shadow-lg"
                            />
                        </div>
                        <h1 className="text-3xl font-extrabold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent mb-2">
                            Welcome Back
                        </h1>
                        <p className="text-gray-600">Sign in to Shoe Type Identification System</p>
                    </div>

                    {/* Error Message */}
                    {error && (
                        <div className="mb-6 p-4 bg-red-50 border-l-4 border-red-500 rounded-lg flex items-start gap-3 animate-fade-in">
                            <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                            </svg>
                            <div>
                                <p className="text-sm font-semibold text-red-800">Login Failed</p>
                                <p className="text-sm text-red-700">{error}</p>
                            </div>
                        </div>
                    )}

                    {/* Login Form */}
                    <form onSubmit={otpRequired ? handleOtpSubmit : handleSubmit} className="space-y-5">
                        {!otpRequired ? (
                            <>
                                {/* Email Field */}
                                <Input
                                    id="email"
                                    type="email"
                                    label="Email Address"
                                    value={email}
                                    onChange={(e) => {
                                        setEmail(e.target.value);
                                        if (errors.email) setErrors({ ...errors, email: null });
                                    }}
                                    error={errors.email}
                                    placeholder="you@example.com"
                                    required
                                    leftIcon={
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207" />
                                        </svg>
                                    }
                                />

                                {/* Password Field */}
                                <div>
                                    <div className="flex justify-between items-center mb-2">
                                        <span className="block text-sm font-semibold text-neutral-700">
                                            Password <span className="text-red-500">*</span>
                                        </span>
                                        <Link
                                            href="/forgot-password"
                                            className="text-xs text-purple-600 hover:text-purple-700 font-semibold transition-colors"
                                        >
                                            Forgot?
                                        </Link>
                                    </div>
                                    <Input
                                        id="password"
                                        type="password"
                                        value={password}
                                        onChange={(e) => {
                                            setPassword(e.target.value);
                                            if (errors.password) setErrors({ ...errors, password: null });
                                        }}
                                        error={errors.password}
                                        placeholder="••••••••"
                                        maxLength={MAX_PASSWORD_LENGTH}
                                        required
                                        leftIcon={
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                                            </svg>
                                        }
                                    />
                                </div>

                                {/* Remember Me */}
                                <div className="flex items-center">
                                    <input
                                        id="remember"
                                        type="checkbox"
                                        checked={rememberMe}
                                        onChange={(e) => setRememberMe(e.target.checked)}
                                        className="w-4 h-4 text-purple-600 border-neutral-300 rounded focus:ring-2 focus:ring-purple-500 focus:ring-offset-0 transition-all"
                                    />
                                    <label htmlFor="remember" className="ml-2.5 text-sm text-neutral-700 font-medium select-none cursor-pointer">
                                        Remember me for 30 days
                                    </label>
                                </div>

                                {/* Submit Button */}
                                <Button
                                    type="submit"
                                    variant="primary"
                                    size="lg"
                                    fullWidth
                                    isLoading={isLoading}
                                    disabled={isLoading}
                                >
                                    {isLoading ? 'Signing in...' : 'Sign In'}
                                </Button>
                            </>
                        ) : (
                            <>
                                {/* OTP Verification */}
                                <div className="text-center mb-6">
                                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-purple-100 mb-4">
                                        <svg className="w-8 h-8 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                        </svg>
                                    </div>
                                    <h2 className="text-2xl font-bold text-gray-900 mb-2">Check Your Email</h2>
                                    <p className="text-gray-600">We've sent a 6-digit verification code to</p>
                                    <p className="text-purple-600 font-semibold">{email}</p>
                                </div>

                                <div>
                                    <Input
                                        id="otp"
                                        type="text"
                                        label="Verification Code"
                                        value={otpCode}
                                        onChange={(e) => {
                                            setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6));
                                            setOtpError('');
                                            setError(null);
                                        }}
                                        placeholder="000000"
                                        required
                                        maxLength={6}
                                        error={otpError}
                                        leftIcon={
                                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                                            </svg>
                                        }
                                    />

                                    {/* Resend Code Button */}
                                    <div className="mt-3 text-center">
                                        <button
                                            type="button"
                                            onClick={handleResendOtp}
                                            disabled={resendingOtp}
                                            className="text-sm text-purple-600 hover:text-purple-700 font-semibold transition-colors disabled:opacity-50"
                                        >
                                            {resendingOtp ? 'Sending...' : 'Didn\'t receive the code? Resend'}
                                        </button>
                                    </div>
                                </div>

                                <Button
                                    type="submit"
                                    variant="primary"
                                    size="lg"
                                    fullWidth
                                    isLoading={isLoading}
                                    disabled={isLoading || otpCode.length !== 6}
                                >
                                    {isLoading ? 'Verifying...' : 'Verify Code'}
                                </Button>

                                <button
                                    type="button"
                                    onClick={() => {
                                        setOtpRequired(false);
                                        setOtpCode('');
                                        setOtpError('');
                                        setError(null);
                                    }}
                                    className="w-full text-center text-sm text-gray-600 hover:text-gray-800 font-medium transition-colors"
                                >
                                    ← Back to login
                                </button>
                            </>
                        )}
                    </form>
                </div>
            </div>
        </div>
    );
}

export default function LoginPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-gradient-to-br from-blue-50 via-purple-50 to-pink-50 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
                    <p className="mt-4 text-gray-600">Loading...</p>
                </div>
            </div>
        }>
            <LoginPageContent />
        </Suspense>
    );
}
