'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/lib/store';

export default function Header() {
    const router = useRouter();
    const pathname = usePathname();
    const { isAuthenticated, user } = useAuthStore();
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [profileImageUrl, setProfileImageUrl] = useState(null);

    // Fetch profile image URL if user has a group
    useEffect(() => {
        if (user?.profile_image_url) {
            // Use the profile_image_url directly from backend
            setProfileImageUrl(user.profile_image_url);
        } else if (user?.group_id) {
            // Fallback: build URL from group_id if profile_image_url not provided
            const imageUrl = `/api/admin/groups/${user.group_id}/image`;
            setProfileImageUrl(imageUrl);
        } else {
            setProfileImageUrl(null);
        }
    }, [user?.group_id, user?.profile_image_url]); const handleLogout = () => {
        useAuthStore.getState().logout();
        router.push('/login');
    };

    // Don't show header on auth pages
    if (!isAuthenticated || pathname === '/login') {
        return null;
    }

    const navLinks = [
        { href: '/dashboard', label: 'Identify', icon: 'camera' },
        { href: '/matches', label: 'History', icon: 'history' },
        { href: '/settings', label: 'Settings', icon: 'settings' },
    ];

    const isActive = (href) => pathname === href;

    const getIcon = (iconName) => {
        const icons = {
            camera: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                </svg>
            ),
            history: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
            ),
            settings: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
            ),
        };
        return icons[iconName];
    };

    return (
        <header className="bg-white/95 backdrop-blur-md shadow-sm sticky top-0 z-50 border-b border-gray-100">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex justify-between items-center h-16">
                    {/* Logo */}
                    <Link href="/dashboard" className="flex items-center gap-3 group">
                        <Image
                            src="/SAR-Apps-logo.png"
                            alt="SAR Apps"
                            width={40}
                            height={40}
                            className="rounded-lg group-hover:scale-110 transition-transform duration-300"
                        />
                        <div className="hidden sm:block">
                            <span className="text-xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                                Shoe Type Identification System
                            </span>
                        </div>
                    </Link>

                    {/* Desktop Navigation */}
                    <nav className="hidden md:flex items-center gap-2">
                        {navLinks.map((link) => (
                            <Link
                                key={link.href}
                                href={link.href}
                                className={`flex items-center gap - 2 px - 4 py - 2 rounded - xl text - sm font - semibold transition - all duration - 300 ${isActive(link.href)
                                    ? 'bg-gradient-to-r from-blue-500 to-purple-500 text-white shadow-lg shadow-purple-500/30'
                                    : 'text-gray-700 hover:bg-gray-100'
                                    } `}
                            >
                                {getIcon(link.icon)}
                                {link.label}
                            </Link>
                        ))}
                    </nav>

                    {/* User Menu */}
                    <div className="hidden md:flex items-center gap-4">
                        <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 rounded-xl">
                            {profileImageUrl ? (
                                <img
                                    src={profileImageUrl}
                                    alt="Profile"
                                    className="w-8 h-8 rounded-full object-cover"
                                    onError={(e) => {
                                        e.target.style.display = 'none';
                                    }}
                                />
                            ) : null}
                            {!profileImageUrl && (
                                <div className="w-8 h-8 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white font-bold text-sm">
                                    {user?.email?.[0].toUpperCase() || 'U'}
                                </div>
                            )}
                            <span className="text-sm font-medium text-gray-700 max-w-[150px] truncate">
                                {user?.email}
                            </span>
                        </div>
                        <button
                            onClick={handleLogout}
                            className="px-5 py-2.5 bg-gradient-to-r from-red-500 to-red-600 text-white rounded-xl hover:shadow-lg hover:shadow-red-500/50 text-sm font-semibold transition-all duration-300 transform hover:scale-105"
                        >
                            Logout
                        </button>
                    </div>                    {/* Mobile Menu Button */}
                    <button
                        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                        className="md:hidden inline-flex items-center justify-center p-2 rounded-lg hover:bg-gray-100 transition-colors"
                    >
                        {mobileMenuOpen ? (
                            <svg className="w-6 h-6 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        ) : (
                            <svg className="w-6 h-6 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                            </svg>
                        )}
                    </button>
                </div>

                {/* Mobile Menu */}
                {mobileMenuOpen && (
                    <div className="md:hidden border-t border-gray-200 py-4 space-y-2 bg-white">
                        {/* User Info Mobile */}
                        <div className="px-4 py-3 mb-2 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg">
                            <div className="flex items-center gap-3">
                                {profileImageUrl ? (
                                    <img
                                        src={profileImageUrl}
                                        alt="Profile"
                                        className="w-10 h-10 rounded-full object-cover"
                                        onError={(e) => {
                                            e.target.style.display = 'none';
                                        }}
                                    />
                                ) : null}
                                {!profileImageUrl && (
                                    <div className="w-10 h-10 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white font-bold">
                                        {user?.email?.[0].toUpperCase() || 'U'}
                                    </div>
                                )}
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-semibold text-gray-900 truncate">{user?.email}</p>
                                    <p className="text-xs text-gray-500">Signed In</p>
                                </div>
                            </div>
                        </div>

                        {/* Nav Links Mobile */}
                        {navLinks.map((link) => (
                            <Link
                                key={link.href}
                                href={link.href}
                                onClick={() => setMobileMenuOpen(false)}
                                className={`flex items - center gap - 3 px - 4 py - 3 rounded - lg text - sm font - semibold transition - all ${isActive(link.href)
                                    ? 'bg-gradient-to-r from-blue-500 to-purple-500 text-white shadow-lg'
                                    : 'text-gray-700 hover:bg-gray-100'
                                    } `}
                            >
                                {getIcon(link.icon)}
                                {link.label}
                            </Link>
                        ))}

                        {/* Logout Button Mobile */}
                        <div className="pt-2 border-t border-gray-200 mt-2">
                            <button
                                onClick={() => {
                                    handleLogout();
                                    setMobileMenuOpen(false);
                                }}
                                className="w-full flex items-center gap-3 px-4 py-3 text-red-600 hover:bg-red-50 rounded-lg text-sm font-semibold transition-all"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                                </svg>
                                Logout
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </header>
    );
}
