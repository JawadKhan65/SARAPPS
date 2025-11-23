'use client';

export default function MatchCard({ match, onConfirm, onReject, showActions = false }) {
    const getTierColor = (similarity) => {
        if (similarity > 0.9) return 'text-green-600';
        if (similarity > 0.75) return 'text-blue-600';
        if (similarity > 0.6) return 'text-yellow-600';
        return 'text-red-600';
    };

    const getTierLabel = (similarity) => {
        if (similarity > 0.9) return 'Perfect Match';
        if (similarity > 0.75) return 'High Confidence';
        if (similarity > 0.6) return 'Possible Match';
        return 'Low Confidence';
    };

    return (
        <div className="bg-white rounded-lg shadow hover:shadow-lg transition border border-gray-200">
            <div className="p-6">
                {/* Header */}
                <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                        <p className="text-sm text-gray-500">Brand</p>
                        <p className="text-lg font-bold text-gray-900">{match.brand}</p>
                        <p className="text-sm text-gray-600 mt-1">{match.product_name}</p>
                    </div>
                    <div className="text-right">
                        <div className={`text-3xl font-bold ${getTierColor(match.similarity)}`}>
                            {Math.round(match.similarity * 100)}%
                        </div>
                        <p className="text-xs text-gray-500">Match Score</p>
                    </div>
                </div>

                {/* Progress Bar */}
                <div className="mb-4">
                    <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                            className={`h-2 rounded-full transition ${match.similarity > 0.9
                                    ? 'bg-green-600'
                                    : match.similarity > 0.75
                                        ? 'bg-blue-600'
                                        : match.similarity > 0.6
                                            ? 'bg-yellow-600'
                                            : 'bg-red-600'
                                }`}
                            style={{ width: `${match.similarity * 100}%` }}
                        ></div>
                    </div>
                </div>

                {/* Details Grid */}
                <div className="grid grid-cols-2 gap-4 mb-4 py-4 border-y border-gray-200">
                    <div>
                        <p className="text-xs text-gray-500">Shoe Type</p>
                        <p className="font-medium text-gray-900">{match.shoe_type}</p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-500">Confidence</p>
                        <p className={`font-medium ${getTierColor(match.similarity)}`}>
                            {getTierLabel(match.similarity)}
                        </p>
                    </div>
                    {match.size && (
                        <div>
                            <p className="text-xs text-gray-500">Size</p>
                            <p className="font-medium text-gray-900">{match.size}</p>
                        </div>
                    )}
                    {match.color && (
                        <div>
                            <p className="text-xs text-gray-500">Color</p>
                            <p className="font-medium text-gray-900">{match.color}</p>
                        </div>
                    )}
                </div>

                {/* Metadata */}
                {match.source && (
                    <p className="text-xs text-gray-500 mb-4">
                        Source: <span className="text-gray-700">{match.source}</span>
                    </p>
                )}

                {/* Actions */}
                <div className="flex gap-3">
                    <a
                        href={match.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-center text-sm font-medium transition"
                    >
                        View Product
                    </a>
                    {showActions && (
                        <>
                            <button
                                onClick={() => onConfirm?.(match.id)}
                                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium transition"
                                title="Confirm this match"
                            >
                                ✓
                            </button>
                            <button
                                onClick={() => onReject?.(match.id)}
                                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium transition"
                                title="Reject this match"
                            >
                                ✕
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
