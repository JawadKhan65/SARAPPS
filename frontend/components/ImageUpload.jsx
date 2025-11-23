'use client';

import { useRef, useState } from 'react';
import Image from 'next/image';

export default function ImageUpload({ onUpload, loading = false }) {
    const fileInputRef = useRef(null);
    const cameraInputRef = useRef(null);
    const [preview, setPreview] = useState(null);
    const [fileName, setFileName] = useState('');

    const handleFileSelect = (file) => {
        if (!file) return;

        setFileName(file.name);

        // Create preview
        const reader = new FileReader();
        reader.onload = (e) => {
            setPreview(e.target.result);
        };
        reader.readAsDataURL(file);

        onUpload(file);
    };

    const handleFileInputChange = (e) => {
        const file = e.target.files?.[0];
        if (file) handleFileSelect(file);
    };

    const handleCameraCapture = (e) => {
        const file = e.target.files?.[0];
        if (file) handleFileSelect(file);
    };

    const handleDragOver = (e) => {
        e.preventDefault();
        e.currentTarget.classList.add('border-blue-500', 'bg-blue-50');
    };

    const handleDragLeave = (e) => {
        e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50');
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50');

        const file = e.dataTransfer.files?.[0];
        if (file && file.type.startsWith('image/')) {
            handleFileSelect(file);
        }
    };

    return (
        <div className="space-y-6">
            {/* Upload Area */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* File Upload */}
                <div
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    className="border-2 border-dashed border-blue-300 rounded-lg p-8 text-center cursor-pointer hover:border-blue-500 transition bg-white"
                >
                    <svg
                        className="w-16 h-16 mx-auto text-blue-400 mb-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 4v16m8-8H4"
                        />
                    </svg>
                    <p className="text-lg font-medium text-gray-700">Upload from Device</p>
                    <p className="text-sm text-gray-500 mt-2">
                        {loading ? 'Uploading...' : 'Click to select or drag and drop'}
                    </p>
                    <p className="text-xs text-gray-400 mt-2">JPG, PNG or WebP</p>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        onChange={handleFileInputChange}
                        disabled={loading}
                        className="hidden"
                    />
                </div>

                {/* Camera Capture */}
                <div
                    onClick={() => cameraInputRef.current?.click()}
                    className="border-2 border-dashed border-purple-300 rounded-lg p-8 text-center cursor-pointer hover:border-purple-500 transition bg-white"
                >
                    <svg
                        className="w-16 h-16 mx-auto text-purple-400 mb-4"
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
                    </svg>
                    <p className="text-lg font-medium text-gray-700">Take a Photo</p>
                    <p className="text-sm text-gray-500 mt-2">
                        {loading ? 'Processing...' : 'Use device camera'}
                    </p>
                    <p className="text-xs text-gray-400 mt-2">Best for shoe sole closeup</p>
                    <input
                        ref={cameraInputRef}
                        type="file"
                        accept="image/*"
                        capture="environment"
                        onChange={handleCameraCapture}
                        disabled={loading}
                        className="hidden"
                    />
                </div>
            </div>

            {/* Preview */}
            {preview && (
                <div className="border border-gray-200 rounded-lg p-6 bg-gray-50">
                    <h3 className="text-lg font-bold text-gray-900 mb-4">Preview</h3>
                    <div className="relative w-full aspect-square rounded-lg overflow-hidden bg-white">
                        <Image
                            src={preview}
                            alt="Preview"
                            fill
                            className="object-cover"
                        />
                    </div>
                    <p className="text-sm text-gray-600 mt-4">
                        File: <span className="font-medium">{fileName}</span>
                    </p>
                    {loading && (
                        <div className="mt-4 flex items-center gap-2">
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                            <span className="text-gray-600">Analyzing image...</span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
