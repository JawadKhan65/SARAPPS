'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminAPI } from '@/lib/api';
import { useAdminStore } from '@/lib/store';

export default function SettingsPage() {
    const router = useRouter();
    const { isAuthenticated } = useAdminStore();
    const [settings, setSettings] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [passwordData, setPasswordData] = useState({
        current_password: '',
        new_password: '',
        confirm_password: ''
    });

    if (!isAuthenticated) {
        router.push('/login');
        return null;
    }

    useEffect(() => {
        loadSettings();
    }, []);

    const loadSettings = async () => {
        try {
            const response = await adminAPI.getSettings();
            setSettings(response.data);
        } catch (err) {
            setError('Failed to load settings');
        } finally {
            setLoading(false);
        }
    };

    const handleSaveSettings = async () => {
        try {
            setError('');
            setSuccess('');
            await adminAPI.updateSettings(settings);
            setSuccess('Settings updated successfully');
        } catch (err) {
            setError(err.response?.data?.message || 'Failed to save settings');
        }
    };



    const handleChangePassword = async () => {
        try {
            setError('');
            setSuccess('');

            if (!passwordData.current_password || !passwordData.new_password) {
                setError('Please fill in all password fields');
                return;
            }

            if (passwordData.new_password !== passwordData.confirm_password) {
                setError('New passwords do not match');
                return;
            }

            if (passwordData.new_password.length < 9) {
                setError('New password must be at least 9 characters');
                return;
            }

            await adminAPI.changePassword({
                current_password: passwordData.current_password,
                new_password: passwordData.new_password
            });

            setSuccess('Password changed successfully');
            setPasswordData({
                current_password: '',
                new_password: '',
                confirm_password: ''
            });
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to change password');
        }
    };

    return (
        <div className="min-h-screen bg-gray-100">
            <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="flex justify-between items-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
                    <button
                        onClick={() => router.back()}
                        className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
                    >
                        Back
                    </button>
                </div>

                {error && (
                    <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
                        {error}
                    </div>
                )}

                {success && (
                    <div className="mb-6 p-4 bg-green-100 border border-green-400 text-green-700 rounded">
                        {success}
                    </div>
                )}

                {loading ? (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                        <p className="mt-4 text-gray-600">Loading settings...</p>
                    </div>
                ) : settings ? (
                    <>
                        {/* Change Password Section */}
                        <div className="bg-white rounded-lg shadow-lg p-8 mb-8">
                            <h2 className="text-2xl font-bold text-gray-900 mb-6">Change Password</h2>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Current Password
                                    </label>
                                    <input
                                        type="password"
                                        value={passwordData.current_password}
                                        onChange={(e) =>
                                            setPasswordData({ ...passwordData, current_password: e.target.value })
                                        }
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                                        placeholder="Enter current password"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        New Password
                                    </label>
                                    <input
                                        type="password"
                                        value={passwordData.new_password}
                                        onChange={(e) =>
                                            setPasswordData({ ...passwordData, new_password: e.target.value })
                                        }
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                                        placeholder="Enter new password (min 9 characters)"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Confirm New Password
                                    </label>
                                    <input
                                        type="password"
                                        value={passwordData.confirm_password}
                                        onChange={(e) =>
                                            setPasswordData({ ...passwordData, confirm_password: e.target.value })
                                        }
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                                        placeholder="Confirm new password"
                                    />
                                </div>
                            </div>

                            <button
                                onClick={handleChangePassword}
                                className="mt-6 px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                            >
                                Change Password
                            </button>
                        </div>

                        {/* General Settings */}
                        <div className="bg-white rounded-lg shadow-lg p-8 mb-8">
                            <h2 className="text-2xl font-bold text-gray-900 mb-6">General Settings</h2>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Site Name
                                    </label>
                                    <input
                                        type="text"
                                        value={settings.site_name || ''}
                                        onChange={(e) =>
                                            setSettings({ ...settings, site_name: e.target.value })
                                        }
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Admin Email
                                    </label>
                                    <input
                                        type="email"
                                        value={settings.admin_email || ''}
                                        onChange={(e) =>
                                            setSettings({ ...settings, admin_email: e.target.value })
                                        }
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Max Upload Size (MB)
                                    </label>
                                    <input
                                        type="number"
                                        value={settings.max_upload_size || 10}
                                        onChange={(e) =>
                                            setSettings({ ...settings, max_upload_size: parseInt(e.target.value) })
                                        }
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                                    />
                                </div>

                                <div>
                                    <label className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={settings.maintenance_mode || false}
                                            onChange={(e) =>
                                                setSettings({ ...settings, maintenance_mode: e.target.checked })
                                            }
                                            className="w-4 h-4 rounded"
                                        />
                                        <span className="text-sm font-medium text-gray-700">Maintenance Mode</span>
                                    </label>
                                </div>
                            </div>

                            <button
                                onClick={handleSaveSettings}
                                className="mt-6 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                            >
                                Save Settings
                            </button>
                        </div>

                        {/* Scraper Settings */}
                        <div className="bg-white rounded-lg shadow-lg p-8 mb-8">
                            <h2 className="text-2xl font-bold text-gray-900 mb-6">Scraper Configuration</h2>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Scraper Timeout (seconds)
                                    </label>
                                    <input
                                        type="number"
                                        value={settings.scraper_timeout || 30}
                                        onChange={(e) =>
                                            setSettings({ ...settings, scraper_timeout: parseInt(e.target.value) })
                                        }
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Similarity Threshold
                                    </label>
                                    <input
                                        type="number"
                                        min="0"
                                        max="1"
                                        step="0.01"
                                        value={settings.similarity_threshold || 0.85}
                                        onChange={(e) =>
                                            setSettings({ ...settings, similarity_threshold: parseFloat(e.target.value) })
                                        }
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                                    />
                                </div>

                                <div>
                                    <label className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={settings.enable_scrapers || false}
                                            onChange={(e) =>
                                                setSettings({ ...settings, enable_scrapers: e.target.checked })
                                            }
                                            className="w-4 h-4 rounded"
                                        />
                                        <span className="text-sm font-medium text-gray-700">Enable All Scrapers</span>
                                    </label>
                                </div>
                            </div>

                            <button
                                onClick={handleSaveSettings}
                                className="mt-6 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                            >
                                Save Scraper Settings
                            </button>
                        </div>

                        {/* Database & Maintenance */}
                        <div className="bg-white rounded-lg shadow-lg p-8 mb-8">
                            <h2 className="text-2xl font-bold text-gray-900 mb-6">Database & Maintenance</h2>

                            <div className="space-y-4">
                                <div className="border border-gray-200 rounded-lg p-4 bg-red-50">
                                    <h3 className="font-bold text-red-900 mb-2">Danger Zone</h3>
                                    <p className="text-sm text-red-700 mb-4">
                                        Clear all data from the database. This action cannot be undone.
                                    </p>
                                    <button
                                        onClick={() => {
                                            if (window.confirm('Are you sure? This will delete ALL data.')) {
                                                adminAPI.clearDatabase().then(() => {
                                                    setSuccess('Database cleared successfully');
                                                });
                                            }
                                        }}
                                        className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                                    >
                                        Clear All Data
                                    </button>
                                </div>
                            </div>
                        </div>
                    </>
                ) : null}
            </div>
        </div>
    );
}
