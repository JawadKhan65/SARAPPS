'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminAPI } from '@/lib/api';
import { useAdminStore } from '@/lib/store';

export default function StatisticsPage() {
    const router = useRouter();
    const { isAuthenticated } = useAdminStore();
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    // Handle authentication redirect
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
            const [statsRes, userRes, matchRes, crawlerRes] = await Promise.all([
                adminAPI.getStats(),
                adminAPI.getUserStats(),
                adminAPI.getMatchStats(),
                adminAPI.getCrawlerStats(),
            ]);

            setStats({
                general: statsRes.data,
                users: userRes.data,
                matches: matchRes.data,
                crawlers: crawlerRes.data,
            });
        } catch (err) {
            setError('Failed to load statistics');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gray-100">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="flex justify-between items-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-900">Statistics & Analytics</h1>
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

                {loading ? (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                        <p className="mt-4 text-gray-600">Loading statistics...</p>
                    </div>
                ) : stats ? (
                    <>
                        {/* User Statistics */}
                        <div className="mb-8">
                            <h2 className="text-2xl font-bold text-gray-900 mb-4">User Statistics</h2>
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">Total Users</p>
                                    <p className="text-3xl font-bold text-gray-900">{stats.users.total_users}</p>
                                    <p className="text-xs text-gray-600 mt-2">All registered users</p>
                                </div>
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">Active Users</p>
                                    <p className="text-3xl font-bold text-green-600">{stats.users.active_users}</p>
                                    <p className="text-xs text-gray-600 mt-2">Last 30 days</p>
                                </div>
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">New Users</p>
                                    <p className="text-3xl font-bold text-blue-600">{stats.users.new_users}</p>
                                    <p className="text-xs text-gray-600 mt-2">This month</p>
                                </div>
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">Blocked Users</p>
                                    <p className="text-3xl font-bold text-red-600">{stats.users.blocked_users}</p>
                                    <p className="text-xs text-gray-600 mt-2">Account status</p>
                                </div>
                            </div>
                        </div>

                        {/* Match Statistics */}
                        <div className="mb-8">
                            <h2 className="text-2xl font-bold text-gray-900 mb-4">Match Statistics</h2>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">Total Matches</p>
                                    <p className="text-3xl font-bold text-gray-900">{stats.matches.total_matches}</p>
                                </div>
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">Average Confidence</p>
                                    <p className="text-3xl font-bold text-purple-600">
                                        {(stats.matches.avg_confidence * 100).toFixed(1)}%
                                    </p>
                                </div>
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">Perfect Matches</p>
                                    <p className="text-3xl font-bold text-green-600">
                                        {stats.matches.perfect_matches}
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Crawler Statistics */}
                        <div className="mb-8">
                            <h2 className="text-2xl font-bold text-gray-900 mb-4">Crawler Statistics</h2>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">Total Items Scraped</p>
                                    <p className="text-3xl font-bold text-gray-900">
                                        {(stats.crawlers.total_items || 0).toLocaleString()}
                                    </p>
                                    <p className="text-xs text-gray-600 mt-2">All time</p>
                                </div>
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm">Active Crawlers</p>
                                    <p className="text-3xl font-bold text-orange-600">{stats.crawlers.active_crawlers}</p>
                                    <p className="text-xs text-gray-600 mt-2">
                                        {stats.crawlers.running_crawlers > 0
                                            ? `${stats.crawlers.running_crawlers} running now`
                                            : 'None running'}
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* System Performance */}
                        <div>
                            <h2 className="text-2xl font-bold text-gray-900 mb-4">System Performance</h2>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm mb-4">Database Size</p>
                                    <p className="text-2xl font-bold text-gray-900">
                                        {(stats.general.db_size_mb).toFixed(2)} MB
                                    </p>
                                    <div className="mt-4 bg-gray-200 rounded-full h-2">
                                        <div
                                            className="bg-blue-600 h-2 rounded-full"
                                            style={{ width: `${Math.min((stats.general.db_size_mb / 1000) * 100, 100)}%` }}
                                        ></div>
                                    </div>
                                </div>

                                <div className="bg-white rounded-lg shadow p-6">
                                    <p className="text-gray-500 text-sm mb-4">Cache Hit Rate</p>
                                    <p className="text-2xl font-bold text-green-600">
                                        {(stats.general.cache_hit_rate * 100).toFixed(1)}%
                                    </p>
                                    <div className="mt-4 bg-gray-200 rounded-full h-2">
                                        <div
                                            className="bg-green-600 h-2 rounded-full"
                                            style={{ width: `${stats.general.cache_hit_rate * 100}%` }}
                                        ></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </>
                ) : null}
            </div>
        </div>
    );
}
