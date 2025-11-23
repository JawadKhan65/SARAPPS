'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminAPI } from '@/lib/api';
import { useAdminStore } from '@/lib/store';

export default function CrawlersPage() {
    const router = useRouter();
    const { isAuthenticated } = useAdminStore();
    const [crawlers, setCrawlers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedCrawler, setSelectedCrawler] = useState(null);

    if (!isAuthenticated) {
        router.push('/login');
        return null;
    }

    useEffect(() => {
        loadCrawlers();
        const interval = setInterval(loadCrawlers, 5000);
        return () => clearInterval(interval);
    }, []);

    const loadCrawlers = async () => {
        try {
            const response = await adminAPI.listCrawlers();
            setCrawlers(response.data.crawlers || []);
        } catch (err) {
            setError('Failed to load crawlers');
        } finally {
            setLoading(false);
        }
    };

    const handleStartCrawler = async (crawlerId) => {
        try {
            await adminAPI.startCrawler(crawlerId);
            loadCrawlers();
        } catch (err) {
            setError('Failed to start crawler');
        }
    };

    const handleStopCrawler = async (crawlerId) => {
        try {
            await adminAPI.stopCrawler(crawlerId);
            loadCrawlers();
        } catch (err) {
            setError('Failed to stop crawler');
        }
    };

    const handleClearCache = async (crawlerId) => {
        try {
            await adminAPI.clearCrawlerCache(crawlerId);
            alert('Cache cleared successfully');
            loadCrawlers();
        } catch (err) {
            setError('Failed to clear cache');
        }
    };

    return (
        <div className="min-h-screen bg-gray-100">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="flex justify-between items-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-900">Crawler Management</h1>
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
                        <p className="mt-4 text-gray-600">Loading crawlers...</p>
                    </div>
                ) : crawlers.length > 0 ? (
                    <div className="space-y-4">
                        {crawlers.map((crawler) => (
                            <div
                                key={crawler.id}
                                className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition"
                            >
                                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
                                    {/* Crawler Info */}
                                    <div>
                                        <p className="text-sm text-gray-500">Crawler</p>
                                        <p className="font-bold text-gray-900">{crawler.name}</p>
                                        <p className="text-xs text-gray-600">{crawler.url}</p>
                                    </div>

                                    {/* Status */}
                                    <div>
                                        <p className="text-sm text-gray-500">Status</p>
                                        <div className="flex items-center gap-2">
                                            <span
                                                className={`w-2 h-2 rounded-full ${crawler.is_running ? 'bg-green-600' : 'bg-gray-400'
                                                    }`}
                                            ></span>
                                            <p className="font-medium text-gray-900">
                                                {crawler.is_running ? 'Running' : 'Stopped'}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Statistics */}
                                    <div>
                                        <p className="text-sm text-gray-500">Items Scraped</p>
                                        <p className="font-bold text-gray-900">{crawler.items_scraped}</p>
                                        <p className="text-xs text-gray-600">Last run: {crawler.last_run_date || 'Never'}</p>
                                    </div>

                                    {/* Actions */}
                                    <div className="flex flex-col gap-2">
                                        {crawler.is_running ? (
                                            <button
                                                onClick={() => handleStopCrawler(crawler.id)}
                                                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium"
                                            >
                                                Stop
                                            </button>
                                        ) : (
                                            <button
                                                onClick={() => handleStartCrawler(crawler.id)}
                                                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium"
                                            >
                                                Start
                                            </button>
                                        )}
                                        <button
                                            onClick={() => handleClearCache(crawler.id)}
                                            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-medium"
                                        >
                                            Clear Cache
                                        </button>
                                    </div>
                                </div>

                                {/* Progress Bar */}
                                {crawler.is_running && (
                                    <div className="mt-4 pt-4 border-t">
                                        <div className="flex items-center justify-between mb-2">
                                            <p className="text-xs font-medium text-gray-600">Progress</p>
                                            <p className="text-xs text-gray-600">{crawler.progress}%</p>
                                        </div>
                                        <div className="w-full bg-gray-200 rounded-full h-2">
                                            <div
                                                className="bg-blue-600 h-2 rounded-full transition"
                                                style={{ width: `${crawler.progress}%` }}
                                            ></div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="text-center py-12 bg-white rounded-lg">
                        <p className="text-gray-500">No crawlers found</p>
                    </div>
                )}
            </div>
        </div>
    );
}
