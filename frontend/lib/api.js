import axios from 'axios';
import Cookies from 'js-cookie';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/api';

const createApiClient = () => {
    const client = axios.create({
        baseURL: API_BASE_URL,
        headers: {
            'Content-Type': 'application/json',
        },
    });

    // Add authorization header if token exists
    client.interceptors.request.use((config) => {
        const token = Cookies.get('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    });

    // Handle 401 responses
    client.interceptors.response.use(
        (response) => response,
        (error) => {
            if (error.response?.status === 401) {
                Cookies.remove('access_token');
                Cookies.remove('refresh_token');
                window.location.href = '/login';
            }
            return Promise.reject(error);
        }
    );

    return client;
};

const api = createApiClient();

export const authAPI = {
    register: (email, password, name) =>
        api.post('/auth/register', { email, password, username: name }),

    login: (email, password) =>
        api.post('/auth/login', { email, password }),

    verifyOtp: (email, otpCode, rememberLogin = false) =>
        api.post('/auth/verify-otp', { email, otp_code: otpCode, remember_login: rememberLogin }),

    forgotPassword: (email) =>
        api.post('/auth/forgot-password', { email }),

    verifyResetOTP: (email, otpCode) =>
        api.post('/auth/verify-reset-otp', { email, otp_code: otpCode }),

    resetPassword: (resetToken, newPassword) =>
        api.post('/auth/reset-password', { reset_token: resetToken, new_password: newPassword }),

    refresh: () => api.post('/auth/refresh'),

    logout: () => api.post('/auth/logout'),

    setupMFA: () => api.post('/auth/mfa/setup'),

    verifyMFA: (token, secret) =>
        api.post('/auth/mfa/verify', { token, secret }),
};

export const userAPI = {
    getProfile: () => api.get('/user/profile'),

    updateProfile: (data) =>
        api.put('/user/profile', data),

    uploadImage: (formData) =>
        api.post('/user/upload-image', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        }),

    identifyShoe: (imageId, limit = 4) =>
        api.post(`/user/match-image/${imageId}`, { limit }),

    getMatches: (params = {}) =>
        api.get('/user/matches', { params }),

    deleteAccount: () => api.delete('/user/account'),

    getImageFeatures: (imageId) =>
        api.get(`/user/image/${imageId}/features`),

    getSoleImage: (soleImageId) =>
        api.get(`/user/sole-image/${soleImageId}`),

    getSoleImageOriginal: (soleImageId) =>
        api.get(`/user/sole-image/${soleImageId}/original`),
};

export const matchesAPI = {
    getHistory: (limit = 50, offset = 0) =>
        api.get('/matches/history', { params: { limit, offset } }),

    confirmMatch: (matchId, correct) =>
        api.post(`/matches/${matchId}/confirm`, { correct }),

    reprocessImage: (imageId) =>
        api.post(`/matches/${imageId}/reprocess`),
};

export default api;
