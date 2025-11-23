'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAdminStore } from '@/lib/store';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';

export default function AdminLoginPage() {
    const router = useRouter();
    const { isAuthenticated, mfaRequired } = useAdminStore();
    const toast = useToast();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [mfaCode, setMfaCode] = useState('');
    const [emailError, setEmailError] = useState('');
    const [passwordError, setPasswordError] = useState('');
    const [mfaError, setMfaError] = useState('');
    const [loading, setLoading] = useState(false);

    // Redirect if already authenticated
    useEffect(() => {
        if (isAuthenticated) {
            router.push('/');
        }
    }, [isAuthenticated, router]);

    // Don't render login form if authenticated
    if (isAuthenticated) {
        return null;
    }

    const validateEmail = (value) => {
        if (!value) {
            setEmailError('Email is required');
            return false;
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
            setEmailError('Please enter a valid email');
            return false;
        }
        setEmailError('');
        return true;
    };

    const validatePassword = (value) => {
        if (!value) {
            setPasswordError('Password is required');
            return false;
        }
        if (value.length < 8) {
            setPasswordError('Password must be at least 8 characters');
            return false;
        }
        setPasswordError('');
        return true;
    };

    const validateMfaCode = (value) => {
        if (!value || value.length !== 6) {
            setMfaError('MFA code must be 6 digits');
            return false;
        }
        if (!/^\d{6}$/.test(value)) {
            setMfaError('MFA code must contain only numbers');
            return false;
        }
        setMfaError('');
        return true;
    };

    const handleLoginSubmit = async (e) => {
        e.preventDefault();

        const isEmailValid = validateEmail(email);
        const isPasswordValid = validatePassword(password);

        if (!isEmailValid || !isPasswordValid) {
            toast.error('Please fix the errors before submitting');
            return;
        }

        setLoading(true);

        try {
            const { login } = useAdminStore.getState();
            const result = await login(email, password);

            if (result.mfa_required) {
                toast.info('MFA code sent to your email. Please enter it below.');
            } else {
                toast.success('Login successful! Welcome back.');
                router.push('/');
            }
        } catch (err) {
            toast.error(err.message || 'Login failed. Please check your credentials.');
        } finally {
            setLoading(false);
        }
    };

    const handleMfaSubmit = async (e) => {
        e.preventDefault();

        if (!validateMfaCode(mfaCode)) {
            return;
        }

        setLoading(true);

        try {
            const { verifyMfa } = useAdminStore.getState();
            await verifyMfa(mfaCode);
            toast.success('MFA verified! Welcome back.');
            router.push('/');
        } catch (err) {
            toast.error(err.message || 'MFA verification failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleBackToLogin = () => {
        setMfaCode('');
        setEmail('');
        setPassword('');
        setMfaError('');
        const { setMfaRequired } = useAdminStore.getState();
        setMfaRequired(false);
    };

    return (
        <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
            {/* Animated Background */}
            <div className="absolute inset-0 bg-gradient-dark">
                <div className="absolute top-0 right-0 w-96 h-96 bg-blue-600/20 rounded-full blur-3xl animate-pulse-slow"></div>
                <div className="absolute bottom-0 left-0 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl animate-pulse-slow" style={{ animationDelay: '1s' }}></div>
            </div>

            {/* Login Card */}
            <div className="relative z-10 w-full max-w-md px-4 animate-fadeIn">
                <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
                    {/* Header with gradient */}
                    <div className="bg-gradient-admin px-8 py-6 text-center">
                        <div className="inline-flex items-center justify-center w-20 h-20 bg-white rounded-2xl mb-3 shadow-glow p-2">
                            <img
                                src="/web-app-manifest-512x512.png"
                                alt="Logo"
                                className="w-full h-full object-contain"
                            />
                        </div>
                        <h1 className="text-2xl font-bold text-white">
                            {mfaRequired ? 'Verify Identity' : 'Admin Portal'}
                        </h1>
                        <p className="text-blue-100 text-sm mt-1">
                            {mfaRequired ? 'Enter the code sent to your email' : 'Shoe Identifier Administration'}
                        </p>
                    </div>

                    {/* Form */}
                    <div className="px-8 py-8">
                        {mfaRequired ? (
                            // MFA Form
                            <form onSubmit={handleMfaSubmit} className="space-y-5">
                                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                                    <p className="text-sm text-blue-800">
                                        🔐 A verification code has been sent to your authentication app. Please enter the 6-digit code.
                                    </p>
                                </div>

                                <Input
                                    label="Verification Code"
                                    id="mfa_code"
                                    type="text"
                                    maxLength="6"
                                    value={mfaCode}
                                    onChange={(e) => {
                                        const value = e.target.value.replace(/\D/g, '');
                                        setMfaCode(value);
                                        if (mfaError) validateMfaCode(value);
                                    }}
                                    onBlur={() => validateMfaCode(mfaCode)}
                                    placeholder="000000"
                                    error={mfaError}
                                    required
                                    leftIcon={
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                                        </svg>
                                    }
                                />

                                <Button
                                    type="submit"
                                    variant="primary"
                                    size="lg"
                                    fullWidth
                                    isLoading={loading}
                                >
                                    {loading ? 'Verifying...' : 'Verify Code'}
                                </Button>

                                <Button
                                    type="button"
                                    variant="secondary"
                                    size="lg"
                                    fullWidth
                                    onClick={handleBackToLogin}
                                    disabled={loading}
                                >
                                    Back to Login
                                </Button>
                            </form>
                        ) : (
                            // Login Form
                            <form onSubmit={handleLoginSubmit} className="space-y-5">
                                <Input
                                    label="Email Address"
                                    id="email"
                                    type="email"
                                    value={email}
                                    onChange={(e) => {
                                        setEmail(e.target.value);
                                        if (emailError) validateEmail(e.target.value);
                                    }}
                                    onBlur={() => validateEmail(email)}
                                    placeholder="admin@example.com"
                                    error={emailError}
                                    required
                                    leftIcon={
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207" />
                                        </svg>
                                    }
                                />

                                <Input
                                    label="Password"
                                    id="password"
                                    type="password"
                                    value={password}
                                    onChange={(e) => {
                                        setPassword(e.target.value);
                                        if (passwordError) validatePassword(e.target.value);
                                    }}
                                    onBlur={() => validatePassword(password)}
                                    placeholder="Enter your password"
                                    error={passwordError}
                                    required
                                    leftIcon={
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                                        </svg>
                                    }
                                />

                                <Button
                                    type="submit"
                                    variant="primary"
                                    size="lg"
                                    fullWidth
                                    isLoading={loading}
                                >
                                    {loading ? 'Signing in...' : 'Sign In to Dashboard'}
                                </Button>
                            </form>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="px-8 py-4 bg-slate-50 border-t border-slate-100">
                        <div className="flex items-center justify-center gap-2 text-xs text-slate-600">
                            <svg className="w-4 h-4 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                            </svg>
                            <span>Admin access only • Unauthorized access is prohibited</span>
                        </div>
                    </div>
                </div>

                {/* Helper Text */}
                <p className="text-center text-sm text-slate-300 mt-6">
                    Need help? Contact system administrator
                </p>
            </div>
        </div>
    );
}
