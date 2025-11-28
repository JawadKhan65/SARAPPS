import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useAdminStore = create(
    persist(
        (set, get) => ({
            // State
            admin: null,
            isAuthenticated: false,
            isLoading: false,
            error: '',
            mfaRequired: false,
            mfaEmail: '',
            mfaResolver: null,

            // Actions
            setAdmin: (admin) => set({ admin }),
            setLoading: (isLoading) => set({ isLoading }),
            setError: (error) => set({ error }),
            setMfaRequired: (required, email = '', resolver = null) => set({
                mfaRequired: required,
                mfaEmail: email,
                mfaResolver: resolver
            }),

            login: async (email, password) => {
                console.log('🔐 Starting login for:', email);
                set({ isLoading: true, error: '' });
                try {
                    // Send credentials directly to backend
                    console.log('📡 Sending credentials to backend...');
                    const response = await fetch('/api/auth/admin/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email, password }),
                    });

                    console.log('📥 Backend response status:', response.status);
                    const data = await response.json();
                    console.log('📦 Backend response data:', data);

                    // Check if MFA is required
                    if (data.mfa_required) {
                        console.log('🔐 MFA Required - email code sent');
                        set({
                            mfaRequired: true,
                            mfaEmail: email,
                            isLoading: false,
                        });
                        return { mfa_required: true, message: data.message };
                    }

                    if (!response.ok) {
                        const errorMsg = data.error || 'Login failed';
                        console.error('❌ Backend error:', errorMsg);
                        throw new Error(errorMsg);
                    }

                    // Store tokens in localStorage
                    console.log('💾 Storing tokens...');
                    if (data.access_token) {
                        localStorage.setItem('admin_access_token', data.access_token);
                        console.log('✅ Access token stored');
                    }
                    if (data.refresh_token) {
                        localStorage.setItem('admin_refresh_token', data.refresh_token);
                        console.log('✅ Refresh token stored');
                    }

                    console.log('✅ Login successful! Admin:', data.admin);
                    set({
                        admin: data.admin,
                        isAuthenticated: true,
                        isLoading: false,
                        mfaRequired: false,
                        mfaEmail: '',
                    });

                    return data;
                } catch (err) {
                    console.error('❌ Login error:', err);
                    console.error('Error code:', err.code);
                    console.error('Error message:', err.message);

                    const errorMsg = err.message || 'Login failed';
                    set({ error: errorMsg, isLoading: false });
                    throw err;
                }
            }, verifyMfa: async (verificationCode) => {
                console.log('🔐 Starting MFA verification with code:', verificationCode);
                set({ isLoading: true, error: '' });
                try {
                    const email = get().mfaEmail;

                    if (!email) {
                        console.error('❌ No email found for MFA verification');
                        throw new Error('No email found for MFA verification');
                    }

                    console.log('📤 Sending MFA code to backend...');
                    const response = await fetch('/api/auth/admin/mfa-verify', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email, mfa_code: verificationCode }),
                    });

                    const data = await response.json();

                    if (!response.ok) {
                        const errorMsg = data.error || 'MFA verification failed';
                        console.error('❌ MFA verification failed:', errorMsg);
                        throw new Error(errorMsg);
                    }

                    console.log('✅ MFA verified successfully');

                    // Store tokens
                    if (data.access_token) {
                        localStorage.setItem('admin_access_token', data.access_token);
                    }

                    set({
                        admin: data.admin,
                        isAuthenticated: true,
                        isLoading: false,
                        mfaRequired: false,
                        mfaEmail: '',
                    });

                    return data;
                } catch (err) {
                    const errorMsg = err.message || 'MFA verification failed';
                    set({ error: errorMsg, isLoading: false });
                    throw err;
                }
            },

            logout: async () => {
                console.log('🚪 Logging out...');
                try {
                    // Clear localStorage
                    console.log('🗑️ Clearing localStorage...');
                    localStorage.removeItem('admin_access_token');
                    localStorage.removeItem('admin_refresh_token');
                    console.log('✅ localStorage cleared');

                    set({
                        admin: null,
                        isAuthenticated: false,
                        error: '',
                        mfaRequired: false,
                        mfaEmail: '',
                        mfaResolver: null,
                    });

                    console.log('✅ Logout complete');
                } catch (err) {
                    console.error('❌ Logout error:', err);
                }
            }, checkAuth: async () => {
                try {
                    const token = localStorage.getItem('admin_access_token');

                    if (!token) {
                        set({ isAuthenticated: false });
                        return;
                    }

                    const response = await fetch('/api/admin/profile', {
                        headers: { Authorization: `Bearer ${token}` },
                    });

                    if (response.ok) {
                        const data = await response.json();
                        set({ admin: data, isAuthenticated: true });
                    } else {
                        set({ isAuthenticated: false });
                    }
                } catch (err) {
                    set({ isAuthenticated: false });
                }
            },
        }),
        {
            name: 'admin-storage',
            partialize: (state) => ({
                admin: state.admin,
                isAuthenticated: state.isAuthenticated,
            }),
        }
    )
);
