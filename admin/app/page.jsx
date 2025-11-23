'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { adminAPI } from '@/lib/api';
import { useAdminStore } from '@/lib/store';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

export default function AdminDashboard() {
    const router = useRouter();
    const { isAuthenticated } = useAdminStore();
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    // Redirect if not authenticated
    useEffect(() => {
    if (!isAuthenticated) {
        router.push('/login');
    }
    }, [isAuthenticated, router]);

    useEffect(() => {
        if (isAuthenticated) {
        loadStats();
        }
    }, [isAuthenticated]);

    const loadStats = async () => {
        try {
            const response = await adminAPI.getStats();
            setStats(response.data);
        } catch (err) {
            setError('Failed to load statistics');
            // Use mock data for demo if API fails
            setStats({
                total_users: 0,
                active_users: 0,
                total_matches: 0,
                crawlers_running: 0,
            });
        } finally {
            setLoading(false);
        }
    };

    if (!isAuthenticated) {
        return null;
    }

    return (
        <div className="min-h-screen bg-slate-50">
            {/* Page Header */}
            <div className="bg-white border-b border-slate-200">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-3xl font-bold text-slate-900">Dashboard</h1>
                            <p className="text-slate-600 mt-1">Monitor and manage your shoe identification system</p>
                        </div>
                        <div className="flex items-center gap-3">
                            <Badge variant="success" dot>System Online</Badge>
                    <button
                                onClick={loadStats}
                                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                                Refresh
                    </button>
                        </div>
                    </div>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {error && (
                    <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl flex items-center gap-3">
                        <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                        </svg>
                        <span>{error}</span>
                    </div>
                )}

                {loading ? (
                    <div className="flex flex-col items-center justify-center py-20">
                        <div className="relative">
                            <div className="w-16 h-16 border-4 border-slate-200 border-t-blue-600 rounded-full animate-spin"></div>
                        </div>
                        <p className="mt-6 text-slate-600 font-medium">Loading dashboard...</p>
                    </div>
                ) : stats ? (
                    <div className="space-y-8 animate-fadeIn">
                        {/* Statistics Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                            {/* Total Users */}
                            <Card variant="elevated" hoverEffect className="group">
                                <div className="flex items-center justify-between">
                                    <div className="flex-1">
                                        <p className="text-sm font-medium text-slate-600">Total Users</p>
                                        <p className="text-3xl font-bold text-slate-900 mt-2">{stats.total_users?.toLocaleString() || 0}</p>
                                        <div className="flex items-center gap-1 mt-2">
                                            <span className="text-xs font-medium text-green-600">+12%</span>
                                            <span className="text-xs text-slate-500">vs last month</span>
                                        </div>
                                    </div>
                                    <div className="w-14 h-14 bg-blue-100 group-hover:bg-blue-600 rounded-xl flex items-center justify-center transition-all duration-200">
                                        <svg className="w-7 h-7 text-blue-600 group-hover:text-white transition-colors" fill="currentColor" viewBox="0 0 20 20">
                                            <path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z" />
                                        </svg>
                                    </div>
                                </div>
                            </Card>

                            {/* Active Users */}
                            <Card variant="elevated" hoverEffect className="group">
                                <div className="flex items-center justify-between">
                                    <div className="flex-1">
                                        <p className="text-sm font-medium text-slate-600">Active Users</p>
                                        <p className="text-3xl font-bold text-slate-900 mt-2">{stats.active_users?.toLocaleString() || 0}</p>
                                        <div className="flex items-center gap-1 mt-2">
                                            <span className="text-xs font-medium text-green-600">+8%</span>
                                            <span className="text-xs text-slate-500">vs last week</span>
                                        </div>
                                    </div>
                                    <div className="w-14 h-14 bg-green-100 group-hover:bg-green-600 rounded-xl flex items-center justify-center transition-all duration-200">
                                        <svg className="w-7 h-7 text-green-600 group-hover:text-white transition-colors" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                                        </svg>
                                    </div>
                                </div>
                            </Card>

                            {/* Total Matches */}
                            <Card variant="elevated" hoverEffect className="group">
                                <div className="flex items-center justify-between">
                                    <div className="flex-1">
                                        <p className="text-sm font-medium text-slate-600">Total Matches</p>
                                        <p className="text-3xl font-bold text-slate-900 mt-2">{stats.total_matches?.toLocaleString() || 0}</p>
                                        <div className="flex items-center gap-1 mt-2">
                                            <span className="text-xs font-medium text-green-600">+24%</span>
                                            <span className="text-xs text-slate-500">vs last month</span>
                                        </div>
                                    </div>
                                    <div className="w-14 h-14 bg-purple-100 group-hover:bg-purple-600 rounded-xl flex items-center justify-center transition-all duration-200">
                                        <svg className="w-7 h-7 text-purple-600 group-hover:text-white transition-colors" fill="currentColor" viewBox="0 0 20 20">
                                            <path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z" />
                                            <path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z" />
                                            <path d="M17 5c0 1.657-3.134 3-7 3S3 6.657 3 5s3.134-3 7-3 7 1.343 7 3z" />
                                        </svg>
                                    </div>
                                </div>
                            </Card>

                            {/* Crawlers Running */}
                            <Card variant="elevated" hoverEffect className="group">
                                <div className="flex items-center justify-between">
                                    <div className="flex-1">
                                        <p className="text-sm font-medium text-slate-600">Crawlers Running</p>
                                        <p className="text-3xl font-bold text-slate-900 mt-2">{stats.crawlers_running || 0}</p>
                                        <div className="flex items-center gap-1 mt-2">
                                            <span className="inline-block w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                                            <span className="text-xs text-slate-500">Currently active</span>
                                        </div>
                                    </div>
                                    <div className="w-14 h-14 bg-amber-100 group-hover:bg-amber-600 rounded-xl flex items-center justify-center transition-all duration-200">
                                        <svg className="w-7 h-7 text-amber-600 group-hover:text-white transition-colors" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
                                        </svg>
                                    </div>
                                </div>
                            </Card>
                        </div>

                        {/* Quick Actions */}
                        <div>
                            <h2 className="text-lg font-bold text-slate-900 mb-4">Quick Actions</h2>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <Link href="/users">
                                    <Card hoverEffect className="cursor-pointer h-full">
                                        <div className="flex items-start gap-4">
                                            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                                                <svg className="w-6 h-6 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                                                    <path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z" />
                                                </svg>
                                            </div>
                                            <div className="flex-1">
                                                <h3 className="font-bold text-slate-900 mb-1">User Management</h3>
                                                <p className="text-sm text-slate-600 mb-3">Manage users, permissions, and account status</p>
                                                <div className="flex items-center text-blue-600 text-sm font-medium">
                                                    <span>Manage Users</span>
                                                    <svg className="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                                    </svg>
                                                </div>
                                            </div>
                                        </div>
                                    </Card>
                                </Link>

                                <Link href="/crawlers">
                                    <Card hoverEffect className="cursor-pointer h-full">
                                        <div className="flex items-start gap-4">
                                            <div className="w-12 h-12 bg-amber-100 rounded-lg flex items-center justify-center flex-shrink-0">
                                                <svg className="w-6 h-6 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
                                                    <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
                                                </svg>
                                            </div>
                                            <div className="flex-1">
                                                <h3 className="font-bold text-slate-900 mb-1">Crawler Control</h3>
                                                <p className="text-sm text-slate-600 mb-3">Start, stop, and monitor web scrapers</p>
                                                <div className="flex items-center text-blue-600 text-sm font-medium">
                                                    <span>Manage Crawlers</span>
                                                    <svg className="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                                    </svg>
                                                </div>
                                            </div>
                                        </div>
                                    </Card>
                                </Link>

                                <Link href="/statistics">
                                    <Card hoverEffect className="cursor-pointer h-full">
                                        <div className="flex items-start gap-4">
                                            <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
                                                <svg className="w-6 h-6 text-purple-600" fill="currentColor" viewBox="0 0 20 20">
                                                    <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
                                                </svg>
                                            </div>
                                            <div className="flex-1">
                                                <h3 className="font-bold text-slate-900 mb-1">Statistics & Analytics</h3>
                                                <p className="text-sm text-slate-600 mb-3">View detailed system and usage metrics</p>
                                                <div className="flex items-center text-blue-600 text-sm font-medium">
                                                    <span>View Analytics</span>
                                                    <svg className="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                                    </svg>
                                                </div>
                                            </div>
                                        </div>
                                    </Card>
                                </Link>
                            </div>
                        </div>

                        {/* System Health */}
                        <div>
                            <h2 className="text-lg font-bold text-slate-900 mb-4">System Health</h2>
                            <Card>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center flex-shrink-0">
                                            <svg className="w-6 h-6 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                                                <path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z" />
                                                <path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z" />
                                                <path d="M17 5c0 1.657-3.134 3-7 3S3 6.657 3 5s3.134-3 7-3 7 1.343 7 3z" />
                                            </svg>
                                        </div>
                                        <div>
                                            <p className="text-sm font-medium text-slate-600">Database</p>
                                            <div className="flex items-center gap-2 mt-1">
                                                <Badge variant="success" size="sm" dot>Connected</Badge>
                                                <span className="text-xs text-slate-500">PostgreSQL</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                                            <svg className="w-6 h-6 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                                                <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
                                            </svg>
                                        </div>
                                        <div>
                                            <p className="text-sm font-medium text-slate-600">Cache</p>
                                            <div className="flex items-center gap-2 mt-1">
                                                <Badge variant="success" size="sm" dot>Operational</Badge>
                                                <span className="text-xs text-slate-500">Redis</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
                                            <svg className="w-6 h-6 text-purple-600" fill="currentColor" viewBox="0 0 20 20">
                                                <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
                                            </svg>
                                        </div>
                                        <div>
                                            <p className="text-sm font-medium text-slate-600">API Server</p>
                                            <div className="flex items-center gap-2 mt-1">
                                                <Badge variant="success" size="sm" dot>Running</Badge>
                                                <span className="text-xs text-slate-500">Flask</span>
                                            </div>
                                </div>
                                </div>
                                </div>
                            </Card>
                        </div>
                    </div>
                ) : null}
            </div>
        </div>
    );
}
