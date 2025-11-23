'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import { userAPI } from '@/lib/api';
import { useAuthStore } from '@/lib/store';

export default function DashboardPage() {
    const router = useRouter();
    const { isAuthenticated, user } = useAuthStore();
    const fileInputRef = useRef(null);
    const cameraInputRef = useRef(null);

    const [uploadedImage, setUploadedImage] = useState(null);
    const [imagePreview, setImagePreview] = useState(null);
    const [fileName, setFileName] = useState('');
    const [matches, setMatches] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [dragActive, setDragActive] = useState(false);
    const [matchLimit, setMatchLimit] = useState(4);
    const [imageId, setImageId] = useState(null);
    const [featureData, setFeatureData] = useState(null);
    const [loadingFeatures, setLoadingFeatures] = useState(false);
    const [matchImages, setMatchImages] = useState({});

    useEffect(() => {
        if (!isAuthenticated) {
            router.push('/login');
        }
    }, [isAuthenticated, router]);

    if (!isAuthenticated) {
        return null;
    }

    const getConfidenceTier = (similarity) => {
        const percentage = similarity * 100;
        if (percentage > 90) return { label: 'Perfect Match', color: 'green', bgColor: 'bg-green-500' };
        if (percentage > 75) return { label: 'High Confidence', color: 'blue', bgColor: 'bg-blue-500' };
        if (percentage > 60) return { label: 'Possible Match', color: 'yellow', bgColor: 'bg-yellow-500' };
        return { label: 'Low Confidence', color: 'red', bgColor: 'bg-red-500' };
    };

    const handleImageUpload = async (file) => {
        if (!file) return;

        // Validate file type
        if (!file.type.startsWith('image/')) {
            setError('Please upload a valid image file');
            return;
        }

        // Validate file size (10MB max)
        if (file.size > 10 * 1024 * 1024) {
            setError('File size must be less than 10MB');
            return;
        }

        setLoading(true);
        setError('');
        setMatches(null);
        setFileName(file.name);

        try {
            // Preview image
            const reader = new FileReader();
            reader.onload = (e) => {
                setUploadedImage(file);
                setImagePreview(e.target.result);
            };
            reader.readAsDataURL(file);

            // Upload to backend
            const formData = new FormData();
            formData.append('image', file);

            const uploadResponse = await userAPI.uploadImage(formData);
            const imageId = uploadResponse.data.image_id;
            setImageId(imageId);

            // Identify shoe
            const identifyResponse = await userAPI.identifyShoe(imageId, matchLimit);

            // Map backend response to frontend format
            const mappedMatches = (identifyResponse.data.matches || []).map(match => ({
                ...match,
                similarity: match.confidence,
                url: match.source_url,
                source: match.brand
            }));

            setMatches(mappedMatches);

            // Load feature extraction data
            setLoadingFeatures(true);
            try {
                const featuresResponse = await userAPI.getImageFeatures(imageId);
                setFeatureData(featuresResponse.data);
            } catch (featErr) {
                console.error('Failed to load features:', featErr);
            }
            setLoadingFeatures(false);

            // Load match images
            const imagePromises = mappedMatches.slice(0, 4).map(async (match) => {
                try {
                    const imgResponse = await userAPI.getSoleImage(match.sole_image_id);
                    return [match.sole_image_id, imgResponse.data.image];
                } catch (err) {
                    console.error(`Failed to load image for ${match.sole_image_id}:`, err);
                    return [match.sole_image_id, null];
                }
            });

            const loadedImages = await Promise.all(imagePromises);
            const imagesMap = Object.fromEntries(loadedImages);
            setMatchImages(imagesMap);
        } catch (err) {
            setError(err.response?.data?.message || 'Failed to process image. Please try again.');
            setImagePreview(null);
            setUploadedImage(null);
        } finally {
            setLoading(false);
        }
    };

    const handleFileSelect = (e) => {
        const file = e.target.files?.[0];
        if (file) handleImageUpload(file);
    };

    const handleCameraCapture = (e) => {
        const file = e.target.files?.[0];
        if (file) handleImageUpload(file);
    };

    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true);
        } else if (e.type === 'dragleave') {
            setDragActive(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);

        const file = e.dataTransfer.files?.[0];
        if (file) handleImageUpload(file);
    };

    const resetUpload = () => {
        setUploadedImage(null);
        setImagePreview(null);
        setFileName('');
        setMatches(null);
        setError('');
        setImageId(null);
        setFeatureData(null);
        setMatchImages({});
        if (fileInputRef.current) fileInputRef.current.value = '';
        if (cameraInputRef.current) cameraInputRef.current.value = '';
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50">
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Welcome Section */}
                <div className="mb-8">
                    <h1 className="text-4xl font-extrabold text-gray-900 mb-2">
                        Welcome back, <span className="text-gradient">{user?.name || user?.email?.split('@')[0]}</span>
                    </h1>
                    <p className="text-lg text-gray-600">
                        Upload a shoe sole image to identify and match with our extensive database
                    </p>
                </div>

                {/* Error Message */}
                {error && (
                    <div className="mb-6 p-4 bg-red-50 border-l-4 border-red-500 rounded-lg flex items-start gap-3 animate-fade-in">
                        <svg className="w-6 h-6 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                        </svg>
                        <div>
                            <h3 className="text-sm font-semibold text-red-800">Error</h3>
                            <p className="text-sm text-red-700">{error}</p>
                        </div>
                    </div>
                )}

                {/* Upload Section */}
                <div className="bg-white rounded-2xl shadow-xl p-8 mb-8 border border-gray-100">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-2xl font-bold text-gray-900">Upload Image</h2>
                        {imagePreview && (
                            <button
                                onClick={resetUpload}
                                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-xl hover:bg-gray-200 text-sm font-semibold transition-all"
                            >
                                Reset
                            </button>
                        )}
                    </div>

                    {/* Match Limit Slider */}
                    <div className="mb-6 p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl border border-blue-200">
                        <div className="flex items-center justify-between mb-3">
                            <label className="text-sm font-semibold text-gray-700">
                                Number of Matches to Find
                            </label>
                            <span className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                                {matchLimit}
                            </span>
                        </div>
                        <input
                            type="range"
                            min="1"
                            max="20"
                            value={matchLimit}
                            onChange={(e) => setMatchLimit(parseInt(e.target.value))}
                            disabled={loading}
                            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <div className="flex justify-between text-xs text-gray-500 mt-2">
                            <span>1 match</span>
                            <span>20 matches</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Upload Area */}
                        <div
                            onClick={() => !loading && fileInputRef.current?.click()}
                            onDragEnter={handleDrag}
                            onDragLeave={handleDrag}
                            onDragOver={handleDrag}
                            onDrop={handleDrop}
                            className={`group relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-300 ${dragActive
                                ? 'border-blue-500 bg-blue-50 scale-105'
                                : 'border-gray-300 hover:border-blue-400 hover:bg-blue-50'
                                } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                            <div className="flex flex-col items-center">
                                <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-500 rounded-2xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform shadow-lg">
                                    <svg
                                        className="w-10 h-10 text-white"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                                        />
                                    </svg>
                                </div>
                                <p className="text-xl font-bold text-gray-900 mb-2">Upload from Device</p>
                                <p className="text-sm text-gray-500 mb-4">
                                    Drag & drop or click to browse
                                </p>
                                <p className="text-xs text-gray-400">
                                    Supports: JPG, PNG, WEBP (Max 10MB)
                                </p>
                            </div>
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/*"
                                onChange={handleFileSelect}
                                className="hidden"
                                disabled={loading}
                            />
                        </div>

                        {/* Camera Capture */}
                        <div
                            onClick={() => !loading && cameraInputRef.current?.click()}
                            className={`group border-2 border-dashed border-purple-300 rounded-2xl p-10 text-center cursor-pointer hover:border-purple-400 hover:bg-purple-50 transition-all duration-300 ${loading ? 'opacity-50 cursor-not-allowed' : ''
                                }`}
                        >
                            <div className="flex flex-col items-center">
                                <div className="w-20 h-20 bg-gradient-to-br from-purple-500 to-pink-500 rounded-2xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform shadow-lg">
                                    <svg
                                        className="w-10 h-10 text-white"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                                        />
                                        <circle cx="12" cy="13" r="3" />
                                    </svg>
                                </div>
                                <p className="text-xl font-bold text-gray-900 mb-2">Take a Photo</p>
                                <p className="text-sm text-gray-500 mb-4">
                                    Capture with your camera
                                </p>
                                <p className="text-xs text-gray-400">
                                    Best for mobile devices
                                </p>
                            </div>
                            <input
                                ref={cameraInputRef}
                                type="file"
                                accept="image/*"
                                capture="environment"
                                onChange={handleCameraCapture}
                                className="hidden"
                                disabled={loading}
                            />
                        </div>
                    </div>
                </div>

                {/* Image Preview and Results */}
                {imagePreview && (
                    <div className="bg-white rounded-2xl shadow-xl p-8 border border-gray-100 animate-fade-in">
                        <h3 className="text-2xl font-bold text-gray-900 mb-6">Analysis Results</h3>

                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                            {/* Image Preview */}
                            <div className="lg:col-span-1">
                                <div className="sticky top-24">
                                    <h4 className="text-sm font-semibold text-gray-500 uppercase mb-3">Uploaded Image</h4>
                                    <div className="relative w-full aspect-square rounded-2xl overflow-hidden bg-gray-100 shadow-lg border-2 border-gray-200">
                                        <Image
                                            src={imagePreview}
                                            alt="Uploaded shoe"
                                            fill
                                            className="object-cover"
                                        />
                                    </div>
                                    <div className="mt-3 p-3 bg-gray-50 rounded-lg">
                                        <p className="text-xs text-gray-600 truncate">{fileName}</p>
                                        {uploadedImage && (
                                            <p className="text-xs text-gray-500 mt-1">
                                                Size: {(uploadedImage.size / 1024).toFixed(2)} KB
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Matches Results */}
                            <div className="lg:col-span-2">
                                {loading ? (
                                    <div className="text-center py-16">
                                        <div className="relative inline-block">
                                            <div className="w-20 h-20 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
                                            <div className="absolute inset-0 flex items-center justify-center">
                                                <svg className="w-10 h-10 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                </svg>
                                            </div>
                                        </div>
                                        <p className="mt-6 text-lg font-semibold text-gray-700">Analyzing sole pattern...</p>
                                        <p className="text-sm text-gray-500 mt-2">Processing through compare_sole_images algorithm...</p>
                                    </div>
                                ) : matches && matches.length > 0 ? (
                                    <div className="space-y-6">
                                        {/* Analysis Statistics */}
                                        <div className="bg-gradient-to-br from-blue-50 to-purple-50 rounded-2xl p-6 border border-blue-200">
                                            <h4 className="text-lg font-bold text-gray-900 mb-4">📊 Match Analysis</h4>
                                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                                <div className="bg-white rounded-xl p-4 shadow-sm">
                                                    <div className="text-3xl font-extrabold text-blue-600">{matches.length}</div>
                                                    <div className="text-xs text-gray-600 font-semibold mt-1">Total Matches</div>
                                                </div>
                                                <div className="bg-white rounded-xl p-4 shadow-sm">
                                                    <div className="text-3xl font-extrabold text-green-600">
                                                        {(matches[0]?.similarity * 100).toFixed(1)}%
                                                    </div>
                                                    <div className="text-xs text-gray-600 font-semibold mt-1">Best Score</div>
                                                </div>
                                                <div className="bg-white rounded-xl p-4 shadow-sm">
                                                    <div className="text-3xl font-extrabold text-purple-600">
                                                        {((matches.reduce((acc, m) => acc + m.similarity, 0) / matches.length) * 100).toFixed(1)}%
                                                    </div>
                                                    <div className="text-xs text-gray-600 font-semibold mt-1">Average Score</div>
                                                </div>
                                                <div className="bg-white rounded-xl p-4 shadow-sm">
                                                    <div className="text-3xl font-extrabold text-orange-600">
                                                        {matches.filter(m => m.similarity > 0.7).length}
                                                    </div>
                                                    <div className="text-xs text-gray-600 font-semibold mt-1">High Confidence</div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Score Distribution Chart */}
                                        <div className="bg-white rounded-2xl p-6 border border-gray-200">
                                            <h5 className="text-sm font-bold text-gray-700 mb-4">Score Distribution</h5>
                                            <div className="space-y-2">
                                                {matches.map((match, idx) => (
                                                    <div key={idx} className="flex items-center gap-3">
                                                        <span className="text-xs font-mono text-gray-500 w-6">#{idx + 1}</span>
                                                        <div className="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden">
                                                            <div
                                                                className={`h-6 rounded-full transition-all duration-500 ${match.similarity > 0.8 ? 'bg-gradient-to-r from-green-400 to-green-600' :
                                                                    match.similarity > 0.6 ? 'bg-gradient-to-r from-blue-400 to-blue-600' :
                                                                        match.similarity > 0.4 ? 'bg-gradient-to-r from-yellow-400 to-yellow-600' :
                                                                            'bg-gradient-to-r from-red-400 to-red-600'
                                                                    }`}
                                                                style={{ width: `${match.similarity * 100}%` }}
                                                            />
                                                        </div>
                                                        <span className="text-sm font-bold text-gray-700 w-12 text-right">
                                                            {(match.similarity * 100).toFixed(1)}%
                                                        </span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>

                                        {/* Feature Extraction Visualization */}
                                        {featureData && (
                                            <details className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
                                                <summary className="cursor-pointer px-6 py-4 bg-gradient-to-r from-purple-50 to-pink-50 font-bold text-gray-900 hover:bg-purple-100 transition-colors">
                                                    🔬 Show Extracted Features & Processing Steps
                                                </summary>
                                                <div className="p-6">
                                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                                                        {[
                                                            ['L Channel', featureData.l_channel],
                                                            ['A Channel', featureData.a_channel],
                                                            ['B Channel', featureData.b_channel],
                                                            ['Denoised L', featureData.denoised_l],
                                                            ['Enhanced L', featureData.enhanced_l],
                                                            ['Binary Pattern', featureData.binary_pattern],
                                                            ['Cleaned Pattern', featureData.cleaned_pattern],
                                                            ['LBP Map', featureData.lbp],
                                                        ].map(([title, imgData], idx) => (
                                                            <div key={idx} className="text-center">
                                                                <div className="relative w-full aspect-square rounded-lg overflow-hidden bg-gray-100 border border-gray-300 mb-2">
                                                                    {imgData && (
                                                                        <Image
                                                                            src={imgData}
                                                                            alt={title}
                                                                            fill
                                                                            className="object-contain"
                                                                        />
                                                                    )}
                                                                </div>
                                                                <p className="text-xs font-semibold text-gray-700">{title}</p>
                                                            </div>
                                                        ))}
                                                    </div>

                                                    {featureData.lbp_features && featureData.lbp_features.length > 0 && (
                                                        <div className="mt-6 p-4 bg-blue-50 rounded-xl">
                                                            <h5 className="text-sm font-bold text-gray-900 mb-3">
                                                                LBP Feature Vector (Length: {featureData.lbp_features_length})
                                                            </h5>
                                                            <div className="h-40 flex items-end gap-0.5 overflow-x-auto">
                                                                {featureData.lbp_features.map((val, idx) => (
                                                                    <div
                                                                        key={idx}
                                                                        className="bg-blue-500 w-1 min-w-[2px]"
                                                                        style={{ height: `${(val / Math.max(...featureData.lbp_features)) * 100}%` }}
                                                                        title={`${idx}: ${val.toFixed(4)}`}
                                                                    />
                                                                ))}
                                                            </div>
                                                            <p className="text-xs text-gray-600 mt-2">
                                                                Showing first 200 values of {featureData.lbp_features_length} total features
                                                            </p>
                                                        </div>
                                                    )}
                                                </div>
                                            </details>
                                        )}

                                        {/* Top Matches - First 4 with Images */}
                                        <div>
                                            <h4 className="text-lg font-bold text-gray-900 mb-4">🏆 Top Matches</h4>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                {matches.slice(0, 4).map((match, idx) => {
                                                    const tier = getConfidenceTier(match.similarity);
                                                    const medals = ['🥇', '🥈', '🥉', '🏅'];
                                                    const matchImage = matchImages[match.sole_image_id];

                                                    return (
                                                        <div
                                                            key={idx}
                                                            className="group border-2 border-gray-200 rounded-2xl p-4 hover:shadow-2xl hover:border-purple-400 transition-all duration-300 transform hover:-translate-y-1 bg-white"
                                                        >
                                                            {/* Match Image */}
                                                            {matchImage && (
                                                                <div className="relative w-full aspect-square rounded-xl overflow-hidden bg-gray-100 mb-3 border border-gray-200">
                                                                    <Image
                                                                        src={matchImage}
                                                                        alt={match.product_name || 'Match'}
                                                                        fill
                                                                        className="object-contain"
                                                                    />
                                                                    <div className="absolute top-2 left-2 text-3xl">{medals[idx]}</div>
                                                                </div>
                                                            )}

                                                            <div className="flex items-start gap-3">
                                                                {!matchImage && <div className="text-3xl">{medals[idx]}</div>}
                                                                <div className="flex-1 min-w-0">
                                                                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                                                                        <span className="text-lg font-bold text-gray-900 truncate">{match.brand || 'Unknown'}</span>
                                                                        <span className={`px-2 py-1 ${tier.bgColor} text-white text-xs font-bold rounded-full shadow-md flex-shrink-0`}>
                                                                            {tier.label}
                                                                        </span>
                                                                    </div>
                                                                    <p className="text-sm text-gray-600 mb-2 line-clamp-2">{match.product_name || 'Product Name'}</p>
                                                                    <div className="flex flex-wrap gap-2 text-xs text-gray-500 mb-3">
                                                                        {match.product_type && (
                                                                            <span className="px-2 py-1 bg-gray-100 rounded-md">{match.product_type}</span>
                                                                        )}
                                                                        {match.feature_vector_size && (
                                                                            <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded-md font-mono">
                                                                                {match.feature_vector_size}D
                                                                            </span>
                                                                        )}
                                                                        {match.quality_score && (
                                                                            <span className="px-2 py-1 bg-purple-50 text-purple-700 rounded-md">
                                                                                Q: {match.quality_score.toFixed(2)}
                                                                            </span>
                                                                        )}
                                                                    </div>

                                                                    <div className="text-center mb-3">
                                                                        <div className="text-3xl font-extrabold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                                                                            {Math.round(match.similarity * 100)}%
                                                                        </div>
                                                                    </div>

                                                                    <div className="w-full bg-gray-200 rounded-full h-4 mb-3 overflow-hidden">
                                                                        <div
                                                                            className={`${tier.bgColor} h-4 rounded-full transition-all duration-1000 ease-out shadow-inner`}
                                                                            style={{ width: `${match.similarity * 100}%` }}
                                                                        ></div>
                                                                    </div>

                                                                    {match.url && (
                                                                        <a
                                                                            href={match.url}
                                                                            target="_blank"
                                                                            rel="noopener noreferrer"
                                                                            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white rounded-xl hover:shadow-lg hover:shadow-purple-500/50 text-sm font-bold transition-all w-full"
                                                                        >
                                                                            View Product
                                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                                            </svg>
                                                                        </a>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>

                                        {/* All Matches Table */}
                                        {matches.length > 4 && (
                                            <details className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
                                                <summary className="cursor-pointer px-6 py-4 bg-gradient-to-r from-gray-50 to-blue-50 font-bold text-gray-900 hover:bg-blue-100 transition-colors">
                                                    📋 View All {matches.length} Matches (Detailed List)
                                                </summary>
                                                <div className="p-6 max-h-96 overflow-y-auto">
                                                    <div className="space-y-3">
                                                        {matches.map((match, idx) => (
                                                            <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-blue-50 transition-colors">
                                                                <div className="flex items-center gap-3 flex-1">
                                                                    <span className="font-mono text-sm text-gray-500 w-8">#{idx + 1}</span>
                                                                    <div className="flex-1 min-w-0">
                                                                        <div className="font-semibold text-gray-900 truncate">{match.brand} - {match.product_name}</div>
                                                                        <div className="text-xs text-gray-500">{match.product_type || 'N/A'}</div>
                                                                    </div>
                                                                </div>
                                                                <div className="flex items-center gap-4">
                                                                    <div className="text-right">
                                                                        <div className="font-bold text-lg text-blue-600">{(match.similarity * 100).toFixed(2)}%</div>
                                                                        <div className="text-xs text-gray-500">Score</div>
                                                                    </div>
                                                                    {match.url && (
                                                                        <a
                                                                            href={match.url}
                                                                            target="_blank"
                                                                            rel="noopener noreferrer"
                                                                            className="px-3 py-1 bg-blue-500 text-white rounded-lg text-xs font-semibold hover:bg-blue-600 transition-colors"
                                                                        >
                                                                            View
                                                                        </a>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            </details>
                                        )}
                                    </div>
                                ) : (
                                    <div className="text-center py-16">
                                        <div className="w-20 h-20 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                            <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                            </svg>
                                        </div>
                                        <p className="text-lg font-semibold text-gray-700 mb-2">No matches found</p>
                                        <p className="text-sm text-gray-500">Try uploading a clearer image of the shoe sole</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {/* Quick Actions */}
                <div className="mt-8 flex flex-col sm:flex-row gap-4 justify-center">
                    <Link
                        href="/matches"
                        className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-white border-2 border-gray-300 text-gray-700 rounded-xl hover:border-purple-500 hover:bg-purple-50 font-semibold transition-all"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        View Match History
                    </Link>
                    <Link
                        href="/settings"
                        className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-white border-2 border-gray-300 text-gray-700 rounded-xl hover:border-blue-500 hover:bg-blue-50 font-semibold transition-all"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        Account Settings
                    </Link>
                </div>
            </main>
        </div>
    );
}
