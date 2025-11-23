'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { userAPI } from '@/lib/api';
import { useAuthStore } from '@/lib/store';

export default function MatchesPage() {
    const router = useRouter();
    const { isAuthenticated } = useAuthStore();

    const [matches, setMatches] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filter, setFilter] = useState('all');
    const [page, setPage] = useState(1);

    if (!isAuthenticated) {
        router.push('/login');
        return null;
    }

    useEffect(() => {
        loadMatches();
    }, [filter, page]);

    const loadMatches = async () => {
        setLoading(true);
        setError('');
        try {
            const response = await userAPI.getMatches({ page, filter });
            setMatches(response.data.matches || []);
        } catch (err) {
            setError(err.response?.data?.message || 'Failed to load matches');
        } finally {
            setLoading(false);
        }
    };

    const getTierBadge = (similarity) => {
        if (similarity > 0.9) return { label: 'Perfect Match', color: 'bg-green-100 text-green-800' };
        if (similarity > 0.75) return { label: 'High Confidence', color: 'bg-blue-100 text-blue-800' };
        if (similarity > 0.6) return { label: 'Possible Match', color: 'bg-yellow-100 text-yellow-800' };
        return { label: 'Low Confidence', color: 'bg-red-100 text-red-800' };
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
            {/* Header */}
            <header className="bg-white shadow">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
                    <h1 className="text-3xl font-bold text-gray-900">Match History</h1>
                    <div className="space-x-4">
                        <button
                            onClick={() => router.push('/dashboard')}
                            className="px-4 py-2 bg-gray-200 text-gray-900 rounded-lg hover:bg-gray-300"
                        >
                            Back
                        </button>
                        <button
                            onClick={() => {
                                useAuthStore.getState().logout();
                                router.push('/login');
                            }}
                            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                        >
                            Logout
                        </button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Filters */}
                <div className="mb-6 flex gap-4">
                    <button
                        onClick={() => { setFilter('all'); setPage(1); }}
                        className={`px-4 py-2 rounded-lg transition ${filter === 'all'
                            ? 'bg-blue-600 text-white'
                            : 'bg-white text-gray-700 hover:bg-gray-100'
                            }`}
                    >
                        All Matches
                    </button>
                    <button
                        onClick={() => { setFilter('high'); setPage(1); }}
                        className={`px-4 py-2 rounded-lg transition ${filter === 'high'
                            ? 'bg-blue-600 text-white'
                            : 'bg-white text-gray-700 hover:bg-gray-100'
                            }`}
                    >
                        High Confidence
                    </button>
                    <button
                        onClick={() => { setFilter('possible'); setPage(1); }}
                        className={`px-4 py-2 rounded-lg transition ${filter === 'possible'
                            ? 'bg-blue-600 text-white'
                            : 'bg-white text-gray-700 hover:bg-gray-100'
                            }`}
                    >
                        Possible Matches
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
                        <p className="mt-4 text-gray-600">Loading matches...</p>
                    </div>
                ) : matches.length > 0 ? (
                    <div className="space-y-4">
                        {matches.map((match) => {
                            const similarity = match.similarity_score || match.similarity || 0;
                            const tier = getTierBadge(similarity);
                            const shoe = match.shoe || {};
                            const brand = shoe.brand || match.brand || 'Unknown';
                            const productName = shoe.product_name || match.product_name || 'Unknown Product';
                            const productType = shoe.product_type || match.shoe_type || match.product_type || 'N/A';
                            const sourceUrl = shoe.source_url || match.url || '#';
                            const createdAt = match.matched_at || match.created_at || new Date().toISOString();

                            return (
                                <div
                                    key={match.id}
                                    className="bg-white rounded-lg shadow hover:shadow-lg transition p-6"
                                >
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
                                        {/* Product Info */}
                                        <div>
                                            <p className="text-sm text-gray-500">Brand</p>
                                            <p className="font-bold text-gray-900">{brand}</p>
                                            <p className="text-sm text-gray-600">{productName}</p>
                                        </div>

                                        {/* Type */}
                                        <div>
                                            <p className="text-sm text-gray-500">Type</p>
                                            <p className="font-medium text-gray-900">{productType}</p>
                                        </div>

                                        {/* Similarity Score */}
                                        <div>
                                            <p className="text-sm text-gray-500">Match Score</p>
                                            <div className="flex items-center gap-2">
                                                <div className="flex-1 bg-gray-200 rounded-full h-2">
                                                    <div
                                                        className="bg-blue-600 h-2 rounded-full"
                                                        style={{ width: `${similarity * 100}%` }}
                                                    ></div>
                                                </div>
                                                <span className="text-lg font-bold text-blue-600">
                                                    {Math.round(similarity * 100)}%
                                                </span>
                                            </div>
                                        </div>

                                        {/* Tier Badge and Action */}
                                        <div className="flex flex-col gap-2">
                                            <span className={`px-3 py-1 rounded-full text-sm font-medium text-center ${tier.color}`}>
                                                {tier.label}
                                            </span>
                                            {sourceUrl && sourceUrl !== '#' && (
                                                <a
                                                    href={sourceUrl}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                                                >
                                                    View Product →
                                                </a>
                                            )}
                                        </div>
                                    </div>

                                    {/* Metadata */}
                                    <div className="mt-4 pt-4 border-t border-gray-200 flex justify-between text-xs text-gray-500">
                                        <span>Identified: {new Date(createdAt).toLocaleDateString()}</span>
                                        <span>Source: {brand}</span>
                                    </div>
                                </div>
                            );
                        })}

                        {/* Pagination */}
                        <div className="flex justify-center gap-2 mt-8">
                            <button
                                onClick={() => setPage(Math.max(1, page - 1))}
                                disabled={page === 1}
                                className="px-4 py-2 bg-white text-gray-700 rounded-lg hover:bg-gray-100 disabled:opacity-50"
                            >
                                Previous
                            </button>
                            <span className="px-4 py-2 bg-white text-gray-700 rounded-lg">
                                Page {page}
                            </span>
                            <button
                                onClick={() => setPage(page + 1)}
                                disabled={matches.length < 20}
                                className="px-4 py-2 bg-white text-gray-700 rounded-lg hover:bg-gray-100 disabled:opacity-50"
                            >
                                Next
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="text-center py-12 bg-white rounded-lg shadow">
                        <p className="text-gray-500 text-lg">No matches found</p>
                        <button
                            onClick={() => router.push('/dashboard')}
                            className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                        >
                            Start Identifying
                        </button>
                    </div>
                )}
            </main>
        </div>
    );
}
