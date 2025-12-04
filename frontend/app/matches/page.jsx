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
    const [thumbs, setThumbs] = useState({}); // { historyId: { uploaded, sole } }
    const [featurePanels, setFeaturePanels] = useState({}); // { historyId: { loading, data } }

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

    // Load thumbnails when matches change
    useEffect(() => {
        (async () => {
            const list = matches || [];
            for (const m of list) {
                const historyId = m.id;
                const upd = { ...(thumbs[historyId] || {}) };
                try {
                    if (m.uploaded_image_id && !upd.uploaded) {
                        const up = await userAPI.getUploadedImage(m.uploaded_image_id);
                        upd.uploaded = up.data.image;
                    }
                } catch (e) { }
                try {
                    const soleId = m.shoe?.id;
                    if (soleId && !upd.sole) {
                        const so = await userAPI.getSoleImageOriginal(soleId);
                        upd.sole = so.data.image;
                    }
                } catch (e) { }
                if (upd.uploaded || upd.sole) {
                    setThumbs((prev) => ({ ...prev, [historyId]: upd }));
                }
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [matches]);

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
                                const ok = typeof window !== 'undefined' ? window.confirm('Are you sure you want to log out?') : true;
                                if (!ok) return;
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
                            const totalMatches = match.total_matches || 0;
                            const allMatches = match.all_matches || [];

                            return (
                                <div
                                    key={match.id}
                                    className="bg-white rounded-lg shadow hover:shadow-lg transition"
                                >
                                    <div className="p-6">
                                        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-center">
                                            {/* Thumbnails */}
                                            <div className="flex gap-2">
                                                <div className="w-16 h-16 bg-gray-100 rounded overflow-hidden border">
                                                    {thumbs[match.id]?.uploaded ? (
                                                        <img src={thumbs[match.id].uploaded} alt="Uploaded" className="w-full h-full object-cover" />
                                                    ) : (
                                                        <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-400">Uploaded</div>
                                                    )}
                                                </div>
                                                <div className="w-16 h-16 bg-gray-100 rounded overflow-hidden border">
                                                    {thumbs[match.id]?.sole ? (
                                                        <img src={thumbs[match.id].sole} alt="Match" className="w-full h-full object-cover" />
                                                    ) : (
                                                        <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-400">Match</div>
                                                    )}
                                                </div>
                                            </div>
                                            {/* Product Info */}
                                            <div>
                                                <p className="text-sm text-gray-500">Top Match</p>
                                                <p className="font-bold text-gray-900">{brand}</p>
                                                <p className="text-sm text-gray-600">{productName}</p>
                                                <p className="text-xs text-gray-400 mt-1">{productType}</p>
                                            </div>

                                            {/* Match Stats */}
                                            <div>
                                                <p className="text-sm text-gray-500">Total Matches Found</p>
                                                <p className="text-2xl font-bold text-gray-900">{totalMatches}</p>
                                            </div>

                                            {/* Similarity Score */}
                                            <div>
                                                <p className="text-sm text-gray-500">Best Match Score</p>
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
                                                        className="text-blue-600 hover:text-blue-800 text-sm font-medium text-center"
                                                    >
                                                        View Product →
                                                    </a>
                                                )}
                                            </div>
                                        </div>

                                        {/* Metadata */}
                                        <div className="mt-4 pt-4 border-t border-gray-200 flex justify-between text-xs text-gray-500">
                                            <span>Identified: {new Date(createdAt).toLocaleDateString()} at {new Date(createdAt).toLocaleTimeString()}</span>
                                            <span>{totalMatches} total results</span>
                                        </div>
                                    </div>

                                    {/* All Matches Details - Expandable */}
                                    {allMatches && allMatches.length > 1 && (
                                        <details className="border-t border-gray-200">
                                            <summary className="cursor-pointer px-6 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-sm font-semibold text-gray-700">
                                                📋 View All {allMatches.length} Matches
                                            </summary>
                                            <div className="p-6 bg-gray-50 max-h-96 overflow-y-auto">
                                                <div className="space-y-2">
                                                    {allMatches.map((m, idx) => {
                                                        const matchTier = getTierBadge(m.similarity_score || 0);
                                                        return (
                                                            <div
                                                                key={idx}
                                                                className="flex items-center justify-between p-3 bg-white rounded-lg hover:bg-blue-50 transition-colors"
                                                            >
                                                                <div className="flex items-center gap-3 flex-1 min-w-0">
                                                                    <span className="font-mono text-sm text-gray-500 w-8">#{m.rank}</span>
                                                                    <div className="flex-1 min-w-0">
                                                                        <div className="font-semibold text-gray-900 truncate">
                                                                            {m.brand} - {m.product_name}
                                                                        </div>
                                                                        <div className="text-xs text-gray-500">{m.product_type}</div>
                                                                    </div>
                                                                </div>
                                                                <div className="flex items-center gap-4">
                                                                    <div className="text-right">
                                                                        <div className="font-bold text-lg text-blue-600">
                                                                            {(m.similarity_score * 100).toFixed(1)}%
                                                                        </div>
                                                                        <span className={`text-xs px-2 py-1 rounded-full ${matchTier.color}`}>
                                                                            {matchTier.label}
                                                                        </span>
                                                                    </div>
                                                                    {m.source_url && (
                                                                        <a
                                                                            href={m.source_url}
                                                                            target="_blank"
                                                                            rel="noopener noreferrer"
                                                                            className="px-3 py-1 bg-blue-500 text-white rounded-lg text-xs font-semibold hover:bg-blue-600 transition-colors"
                                                                        >
                                                                            View
                                                                        </a>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        </details>
                                    )}

                                    {/* AI Breakdown Panel */}
                                    <details className="border-t border-gray-200">
                                        <summary className="cursor-pointer px-6 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-sm font-semibold text-gray-700">
                                            🔬 Show AI Breakdown
                                        </summary>
                                        <div className="p-6 bg-white">
                                            {!featurePanels[match.id]?.data && !featurePanels[match.id]?.loading && (
                                                <button
                                                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm"
                                                    onClick={async () => {
                                                        setFeaturePanels((p) => ({ ...p, [match.id]: { loading: true } }));
                                                        try {
                                                            const res = await userAPI.getImageFeatures(match.uploaded_image_id);
                                                            setFeaturePanels((p) => ({ ...p, [match.id]: { loading: false, data: res.data } }));
                                                        } catch (e) {
                                                            setFeaturePanels((p) => ({ ...p, [match.id]: { loading: false, data: null } }));
                                                        }
                                                    }}
                                                >
                                                    Load Breakdown
                                                </button>
                                            )}
                                            {featurePanels[match.id]?.loading && (
                                                <p className="text-sm text-gray-500">Loading features…</p>
                                            )}
                                            {featurePanels[match.id]?.data && (
                                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                                    {[
                                                        ['L Channel', 'l_channel'],
                                                        ['A Channel', 'a_channel'],
                                                        ['B Channel', 'b_channel'],
                                                        ['Denoised L', 'denoised_l'],
                                                        ['Enhanced L', 'enhanced_l'],
                                                        ['Binary Pattern', 'binary_pattern'],
                                                        ['Cleaned Pattern', 'cleaned_pattern'],
                                                        ['LBP Map', 'lbp'],
                                                    ].map(([title, key]) => (
                                                        <div key={key} className="text-center">
                                                            <div className="w-full aspect-square bg-gray-100 rounded border overflow-hidden mb-2">
                                                                <img src={featurePanels[match.id].data[key]} alt={title} className="w-full h-full object-contain" />
                                                            </div>
                                                            <p className="text-xs text-gray-600 font-semibold">{title}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </details>
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
