import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import Cookies from 'js-cookie';
import { authAPI } from './api';

export const useAuthStore = create(
    persist(
        (set, get) => ({
            user: null,
            isAuthenticated: false,
            isLoading: false,
            error: null,

            setUser: (user) => set({ user, isAuthenticated: !!user }),
            setLoading: (isLoading) => set({ isLoading }),
            setError: (error) => set({ error }),

            register: async (email, password, name) => {
                set({ isLoading: true, error: null });
                try {
                    const response = await authAPI.register(email, password, name);
                    const { access_token, refresh_token, user } = response.data;

                    Cookies.set('access_token', access_token, {
                        expires: 1 / 24, // 1 hour
                        secure: process.env.NODE_ENV === 'production',
                        sameSite: 'strict',
                    });
                    Cookies.set('refresh_token', refresh_token, {
                        expires: 30,
                        secure: process.env.NODE_ENV === 'production',
                        sameSite: 'strict',
                    });

                    set({ user, isAuthenticated: true, isLoading: false });
                } catch (error) {
                    const message = error instanceof Error ? error.message : 'Registration failed';
                    set({ error: message, isLoading: false });
                    throw error;
                }
            },

            login: async (email, password) => {
                set({ isLoading: true, error: null });
                try {
                    const response = await authAPI.login(email, password);

                    // Check if OTP is required
                    if (response.data.otp_required) {
                        set({ isLoading: false });
                        return response.data; // Return the response so the component knows OTP is required
                    }

                    // If no OTP required (backward compatibility with old endpoint)
                    const { access_token, refresh_token, user } = response.data;

                    Cookies.set('access_token', access_token, {
                        expires: 1 / 24, // 1 hour
                        secure: process.env.NODE_ENV === 'production',
                        sameSite: 'strict',
                    });
                    Cookies.set('refresh_token', refresh_token, {
                        expires: 30,
                        secure: process.env.NODE_ENV === 'production',
                        sameSite: 'strict',
                    });

                    set({ user, isAuthenticated: true, isLoading: false });
                } catch (error) {
                    const message = error instanceof Error ? error.message : 'Login failed';
                    set({ error: message, isLoading: false });
                    throw error;
                }
            },

            verifyOtp: async (email, otpCode, rememberLogin = false) => {
                set({ isLoading: true, error: null });
                try {
                    const response = await authAPI.verifyOtp(email, otpCode, rememberLogin);
                    const { access_token, refresh_token, user } = response.data;

                    Cookies.set('access_token', access_token, {
                        expires: 1 / 24, // 1 hour
                        secure: process.env.NODE_ENV === 'production',
                        sameSite: 'strict',
                    });
                    Cookies.set('refresh_token', refresh_token, {
                        expires: 30,
                        secure: process.env.NODE_ENV === 'production',
                        sameSite: 'strict',
                    });

                    set({ user, isAuthenticated: true, isLoading: false });
                } catch (error) {
                    const message = error instanceof Error ? error.message : 'OTP verification failed';
                    set({ error: message, isLoading: false });
                    throw error;
                }
            },

            logout: async () => {
                set({ isLoading: true });
                try {
                    await authAPI.logout();
                } catch (error) {
                    console.error('Logout error:', error);
                } finally {
                    Cookies.remove('access_token');
                    Cookies.remove('refresh_token');
                    set({ user: null, isAuthenticated: false, isLoading: false });
                }
            },

            checkAuth: async () => {
                const token = Cookies.get('access_token');
                if (!token) {
                    set({ isAuthenticated: false, user: null });
                    return;
                }

                // Token exists, keep existing user data from localStorage
                // Don't overwrite user object that's already loaded from persist
                const currentState = get();
                if (!currentState.user) {
                    // If no user in state, set authenticated but user will be fetched when needed
                    set({ isAuthenticated: true });
                }
            },
        }),
        {
            name: 'auth-storage',
        }
    )
);
