import axios from 'axios';
import { useAdminStore } from '@/lib/store';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/api';

// Create axios instance
const apiClient = axios.create({
    baseURL: API_BASE_URL,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request interceptor - add auth token
apiClient.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('admin_access_token');

        console.log('🔍 API Request:', config.url);

        if (token) {
            console.log('Token from localStorage:', `${token.substring(0, 20)}...`);
            config.headers.Authorization = `Bearer ${token}`;
        } else {
            console.warn('⚠️  No token found in localStorage for:', config.url);
        }

        return config;
    },
    (error) => Promise.reject(error)
);

// Response interceptor - handle 401
apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            useAdminStore.getState().logout();
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);

// Admin API endpoints
export const adminAPI = {
    // Users management
    listUsers: (params) => apiClient.get('/admin/users', { params }),
    getUser: (id) => apiClient.get(`/admin/users/${id}`),
    updateUser: (id, data) => apiClient.put(`/admin/users/${id}`, data),
    deleteUser: (id) => apiClient.delete(`/admin/users/${id}`),
    createUser: (data) => apiClient.post('/admin/users', data),
    blockUser: (id) => apiClient.post(`/admin/users/${id}/block`),
    unblockUser: (id) => apiClient.post(`/admin/users/${id}/unblock`),
    changeUserPassword: (id, data) => apiClient.put(`/admin/users/${id}/password`, data),

    // User Groups management
    listGroups: () => apiClient.get('/admin/groups'),
    createGroup: (data) => apiClient.post('/admin/groups', data),
    updateGroup: (id, data) => apiClient.put(`/admin/groups/${id}`, data),
    deleteGroup: (id) => apiClient.delete(`/admin/groups/${id}`),
    uploadGroupImage: (groupId, formData) => apiClient.post(`/admin/groups/${groupId}/upload-image`, formData, {
        headers: {
            'Content-Type': 'multipart/form-data'
        }
    }),

    // Crawler management
    listCrawlers: () => apiClient.get('/admin/crawlers'),
    getCrawlerStatus: (id) => apiClient.get(`/admin/crawlers/${id}/status`),
    startCrawler: (id) => apiClient.post(`/admin/crawlers/${id}/start`),
    stopCrawler: (id) => apiClient.post(`/admin/crawlers/${id}/stop`),
    getCrawlerLogs: (id, params) => apiClient.get(`/admin/crawlers/${id}/logs`, { params }),
    updateCrawlerConfig: (id, config) => apiClient.put(`/admin/crawlers/${id}/config`, config),
    getCrawlerStats: (id) => apiClient.get(`/admin/crawlers/${id}/stats`),
    clearCrawlerCache: (id) => apiClient.post(`/admin/crawlers/${id}/cache/clear`),

    // System statistics
    getStats: () => apiClient.get('/admin/stats'),
    getUserStats: () => apiClient.get('/admin/stats/users'),
    getMatchStats: () => apiClient.get('/admin/stats/matches'),
    getCrawlerStats: () => apiClient.get('/admin/stats/crawlers'),
    getSystemHealth: () => apiClient.get('/admin/stats/health'),

    // Logs and monitoring
    getSystemLogs: (params) => apiClient.get('/admin/logs', { params }),
    getErrorLogs: (params) => apiClient.get('/admin/logs/errors', { params }),
    getAuditLogs: (params) => apiClient.get('/admin/logs/audit', { params }),
    clearLogs: () => apiClient.post('/admin/logs/clear'),

    // Database management
    initDatabase: () => apiClient.post('/admin/database/init'),
    clearDatabase: () => apiClient.post('/admin/database/clear'),
    getBackupStatus: () => apiClient.get('/admin/database/backup/status'),
    createBackup: () => apiClient.post('/admin/database/backup/create'),
    restoreBackup: (backupId) => apiClient.post(`/admin/database/backup/restore/${backupId}`),

    // Settings
    getSettings: () => apiClient.get('/admin/settings'),
    updateSettings: (data) => apiClient.put('/admin/settings', data),
    changePassword: (data) => apiClient.post('/admin/change-password', data),
};

// Export adminAPI as 'api' as well for convenience
export const api = adminAPI;

export default apiClient;
