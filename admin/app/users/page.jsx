'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminAPI, api } from '@/lib/api';
import { useAdminStore } from '@/lib/store';

export default function UsersPage() {
    const router = useRouter();
    const { isAuthenticated } = useAdminStore();
    const [users, setUsers] = useState([]);
    const [groups, setGroups] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [message, setMessage] = useState({ type: '', text: '' });
    const [searchTerm, setSearchTerm] = useState('');
    const [page, setPage] = useState(1);
    const [selectedUser, setSelectedUser] = useState(null);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [showGroupModal, setShowGroupModal] = useState(false);
    const [passwordFormData, setPasswordFormData] = useState({
        userId: '',
        newPassword: '',
        confirmPassword: ''
    });
    const [groupFormData, setGroupFormData] = useState({
        userId: '',
        group_id: ''
    });
    const [formData, setFormData] = useState({
        email: '',
        username: '',
        password: '',
        group_id: ''
    });
    const [creatingUser, setCreatingUser] = useState(false);

    // Redirect if not authenticated
    useEffect(() => {
        if (!isAuthenticated) {
            router.push('/login');
        }
    }, [isAuthenticated, router]);

    useEffect(() => {
        if (isAuthenticated) {
            loadUsers();
            loadGroups();
        }
    }, [page, searchTerm, isAuthenticated]);

    if (!isAuthenticated) {
        return null;
    }

    const loadGroups = async () => {
        try {
            const response = await api.listGroups();
            setGroups(response.data.groups || []);
        } catch (err) {
            console.error('Failed to load groups:', err);
        }
    };

    const loadUsers = async () => {
        setLoading(true);
        setError('');
        try {
            const response = await adminAPI.listUsers({ page, search: searchTerm, limit: 20 });
            setUsers(response.data.users || []);
        } catch (err) {
            setError(err.response?.data?.message || 'Failed to load users');
        } finally {
            setLoading(false);
        }
    };

    const handleBlockUser = async (userId) => {
        try {
            await adminAPI.blockUser(userId);
            loadUsers();
        } catch (err) {
            setError('Failed to block user');
        }
    };

    const handleUnblockUser = async (userId) => {
        try {
            await adminAPI.unblockUser(userId);
            loadUsers();
        } catch (err) {
            setError('Failed to unblock user');
        }
    };

    const handleDeleteUser = async (userId) => {
        if (!window.confirm('Are you sure you want to PERMANENTLY DELETE this user? This action cannot be undone and will remove all their data.')) return;
        try {
            await adminAPI.deleteUser(userId);
            setMessage({ type: 'success', text: 'User permanently deleted' });
            loadUsers();
        } catch (err) {
            setError('Failed to delete user');
        }
    };

    const openGroupModal = (userId) => {
        setGroupFormData({ userId, group_id: '' });
        setShowGroupModal(true);
    };

    const handleAssignGroup = async (e) => {
        e.preventDefault();
        if (!groupFormData.group_id) {
            setError('Please select a group');
            return;
        }
        try {
            await adminAPI.updateUser(groupFormData.userId, { group_id: groupFormData.group_id });
            setMessage({ type: 'success', text: 'Group assigned successfully' });
            setShowGroupModal(false);
            setGroupFormData({ userId: '', group_id: '' });
            loadUsers();
        } catch (err) {
            setError(err.response?.data?.message || 'Failed to assign group');
        }
    };

    const handleChangePassword = async (e) => {
        e.preventDefault();

        if (passwordFormData.newPassword !== passwordFormData.confirmPassword) {
            setMessage({ type: 'error', text: 'Passwords do not match' });
            return;
        }

        if (passwordFormData.newPassword.length < 8) {
            setMessage({ type: 'error', text: 'Password must be at least 8 characters' });
            return;
        }

        try {
            await adminAPI.changeUserPassword(passwordFormData.userId, {
                new_password: passwordFormData.newPassword
            });
            setMessage({ type: 'success', text: 'Password changed successfully' });
            setShowPasswordModal(false);
            setPasswordFormData({ userId: '', newPassword: '', confirmPassword: '' });
        } catch (err) {
            setMessage({
                type: 'error',
                text: err.response?.data?.error || 'Failed to change password'
            });
        }
    };

    const openPasswordModal = (userId) => {
        setPasswordFormData({ userId, newPassword: '', confirmPassword: '' });
        setShowPasswordModal(true);
        setMessage({ type: '', text: '' });
    };

    const handleCreateUser = async (e) => {
        e.preventDefault();

        // Validate password length
        if (formData.password.length < 9) {
            setMessage({ type: 'error', text: 'Password must be at least 9 characters long' });
            return;
        }

        setCreatingUser(true);
        try {
            await api.createUser({
                email: formData.email,
                username: formData.username,
                password: formData.password,
                group_id: formData.group_id || null
            });
            setMessage({ type: 'success', text: 'User created successfully' });
            setFormData({ email: '', username: '', password: '', group_id: '' });
            setShowCreateModal(false);
            await loadUsers();
        } catch (err) {
            setMessage({
                type: 'error',
                text: err.response?.data?.error || 'Failed to create user'
            });
        } finally {
            setCreatingUser(false);
        }
    };

    const closeModal = () => {
        setShowCreateModal(false);
        setFormData({ email: '', username: '', password: '', group_id: '' });
        setMessage({ type: '', text: '' });
    };

    return (
        <div className="min-h-screen bg-gray-100">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="flex justify-between items-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-900">User Management</h1>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setShowCreateModal(true)}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                        >
                            Create User
                        </button>
                        <button
                            onClick={() => router.back()}
                            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
                        >
                            Back
                        </button>
                    </div>
                </div>

                {error && (
                    <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
                        {error}
                    </div>
                )}

                {message.text && (
                    <div className={`mb-6 p-4 rounded ${message.type === 'success' ? 'bg-green-100 border border-green-400 text-green-700' : 'bg-red-100 border border-red-400 text-red-700'}`}>
                        {message.text}
                    </div>
                )}

                {/* Search */}
                <div className="mb-6">
                    <input
                        type="text"
                        placeholder="Search users by email or name..."
                        value={searchTerm}
                        onChange={(e) => {
                            setSearchTerm(e.target.value);
                            setPage(1);
                        }}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-600 outline-none"
                    />
                </div>

                {loading ? (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                        <p className="mt-4 text-gray-600">Loading users...</p>
                    </div>
                ) : users.length > 0 ? (
                    <div className="bg-white rounded-lg shadow overflow-hidden">
                        <table className="w-full">
                            <thead className="bg-gray-50 border-b border-gray-200">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Profile</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Username</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Group</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Joined</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Login</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Storage</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200">
                                {users.map((user) => (
                                    <tr key={user.id} className="hover:bg-gray-50">
                                        <td className="px-6 py-4">
                                            {user.group && user.group.profile_image_url ? (
                                                <img
                                                    src={`http://localhost:5000${user.group.profile_image_url}`}
                                                    alt={user.username}
                                                    className="h-10 w-10 rounded-full object-cover"
                                                />
                                            ) : (
                                                <div className="h-10 w-10 rounded-full bg-gray-200 flex items-center justify-center">
                                                    <span className="text-gray-500 text-xs">No Image</span>
                                                </div>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 text-sm font-medium text-gray-900">{user.email}</td>
                                        <td className="px-6 py-4 text-sm text-gray-600">{user.username}</td>
                                        <td className="px-6 py-4 text-sm text-gray-600">
                                            {user.group ? (
                                                <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">
                                                    {user.group.name}
                                                </span>
                                            ) : (
                                                <span className="text-gray-400">No Group</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 text-sm">
                                            <span
                                                className={`px-3 py-1 rounded-full text-xs font-medium ${user.is_deleted
                                                    ? 'bg-gray-100 text-gray-800'
                                                    : user.is_active
                                                        ? 'bg-green-100 text-green-800'
                                                        : 'bg-red-100 text-red-800'
                                                    }`}
                                            >
                                                {user.is_deleted ? 'Deleted' : user.is_active ? 'Active' : 'Blocked'}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-sm text-gray-600">
                                            {new Date(user.created_at).toLocaleDateString()}
                                        </td>
                                        <td className="px-6 py-4 text-sm text-gray-600">
                                            {user.last_login ? (
                                                <div className="flex flex-col">
                                                    <span>{new Date(user.last_login).toLocaleDateString()}</span>
                                                    <span className="text-xs text-gray-400">
                                                        {new Date(user.last_login).toLocaleTimeString()}
                                                    </span>
                                                </div>
                                            ) : (
                                                <span className="text-gray-400">Never</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 text-sm text-gray-600">
                                            {user.storage_used_mb ? `${user.storage_used_mb.toFixed(2)} MB` : '0 MB'}
                                        </td>
                                        <td className="px-6 py-4 text-sm">
                                            {!user.is_deleted && (
                                                <div className="flex flex-col gap-2">
                                                    {user.is_active ? (
                                                        <button
                                                            onClick={() => handleBlockUser(user.id)}
                                                            className="px-3 py-1 bg-orange-600 text-white rounded hover:bg-orange-700 text-xs whitespace-nowrap"
                                                        >
                                                            Block
                                                        </button>
                                                    ) : (
                                                        <button
                                                            onClick={() => handleUnblockUser(user.id)}
                                                            className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 text-xs whitespace-nowrap"
                                                        >
                                                            Unblock
                                                        </button>
                                                    )}
                                                    {!user.group && (
                                                        <button
                                                            onClick={() => openGroupModal(user.id)}
                                                            className="px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700 text-xs whitespace-nowrap"
                                                        >
                                                            Assign Group
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={() => openPasswordModal(user.id)}
                                                        className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-xs whitespace-nowrap"
                                                    >
                                                        Password
                                                    </button>
                                                    <button
                                                        onClick={() => handleDeleteUser(user.id)}
                                                        className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 text-xs whitespace-nowrap"
                                                    >
                                                        Delete
                                                    </button>
                                                </div>
                                            )}
                                            {user.is_deleted && (
                                                <span className="text-xs text-gray-500 italic">No actions available</span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        {/* Pagination */}
                        <div className="bg-gray-50 px-6 py-4 flex justify-center gap-2 border-t">
                            <button
                                onClick={() => setPage(Math.max(1, page - 1))}
                                disabled={page === 1}
                                className="px-4 py-2 bg-white text-gray-700 rounded-lg hover:bg-gray-100 disabled:opacity-50"
                            >
                                Previous
                            </button>
                            <span className="px-4 py-2 text-gray-700">Page {page}</span>
                            <button
                                onClick={() => setPage(page + 1)}
                                disabled={users.length < 20}
                                className="px-4 py-2 bg-white text-gray-700 rounded-lg hover:bg-gray-100 disabled:opacity-50"
                            >
                                Next
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="text-center py-12 bg-white rounded-lg">
                        <p className="text-gray-500">No users found</p>
                    </div>
                )}

                {/* Create User Modal */}
                {showCreateModal && (
                    <div className="fixed z-10 inset-0 overflow-y-auto">
                        <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20">
                            <div
                                className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
                                onClick={closeModal}
                            ></div>
                            <div className="relative bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:max-w-lg sm:w-full">
                                <form onSubmit={handleCreateUser}>
                                    <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                                        <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                                            Create New User
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700">
                                                    Email *
                                                </label>
                                                <input
                                                    type="email"
                                                    required
                                                    value={formData.email}
                                                    onChange={(e) =>
                                                        setFormData({ ...formData, email: e.target.value })
                                                    }
                                                    placeholder="user@example.com"
                                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700">
                                                    Username *
                                                </label>
                                                <input
                                                    type="text"
                                                    required
                                                    value={formData.username}
                                                    onChange={(e) =>
                                                        setFormData({ ...formData, username: e.target.value })
                                                    }
                                                    placeholder="username"
                                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                                    Password * (min 9 characters)
                                                </label>
                                                <input
                                                    type="password"
                                                    required
                                                    minLength={9}
                                                    value={formData.password}
                                                    onChange={(e) =>
                                                        setFormData({ ...formData, password: e.target.value })
                                                    }
                                                    placeholder="At least 9 characters"
                                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700">
                                                    Group (Optional)
                                                </label>
                                                <select
                                                    value={formData.group_id}
                                                    onChange={(e) =>
                                                        setFormData({ ...formData, group_id: e.target.value })
                                                    }
                                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                                >
                                                    <option value="">No Group</option>
                                                    {groups.map((group) => (
                                                        <option key={group.id} value={group.id}>
                                                            {group.name}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
                                        <button
                                            type="submit"
                                            disabled={creatingUser}
                                            className="w-full inline-flex justify-center items-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-base font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            {creatingUser ? (
                                                <>
                                                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                                    </svg>
                                                    Creating...
                                                </>
                                            ) : (
                                                'Create User'
                                            )}
                                        </button>
                                        <button
                                            type="button"
                                            onClick={closeModal}
                                            disabled={creatingUser}
                                            className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                )}

                {/* Change Password Modal */}
                {showPasswordModal && (
                    <div className="fixed z-10 inset-0 overflow-y-auto">
                        <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20">
                            <div
                                className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
                                onClick={() => setShowPasswordModal(false)}
                            ></div>
                            <div className="relative bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:max-w-lg sm:w-full">
                                <form onSubmit={handleChangePassword}>
                                    <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                                        <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                                            Change User Password
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700">
                                                    New Password * (min 8 characters)
                                                </label>
                                                <input
                                                    type="password"
                                                    required
                                                    minLength={8}
                                                    value={passwordFormData.newPassword}
                                                    onChange={(e) =>
                                                        setPasswordFormData({ ...passwordFormData, newPassword: e.target.value })
                                                    }
                                                    placeholder="Enter new password"
                                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700">
                                                    Confirm Password *
                                                </label>
                                                <input
                                                    type="password"
                                                    required
                                                    minLength={8}
                                                    value={passwordFormData.confirmPassword}
                                                    onChange={(e) =>
                                                        setPasswordFormData({ ...passwordFormData, confirmPassword: e.target.value })
                                                    }
                                                    placeholder="Confirm new password"
                                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                                />
                                            </div>
                                        </div>
                                    </div>
                                    <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
                                        <button
                                            type="submit"
                                            className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-base font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:ml-3 sm:w-auto sm:text-sm"
                                        >
                                            Change Password
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setShowPasswordModal(false)}
                                            className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                )}

                {/* Assign Group Modal */}
                {showGroupModal && (
                    <div className="fixed z-10 inset-0 overflow-y-auto">
                        <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20">
                            <div
                                className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
                                onClick={() => setShowGroupModal(false)}
                            ></div>
                            <div className="relative bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:max-w-lg sm:w-full">
                                <form onSubmit={handleAssignGroup}>
                                    <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                                        <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                                            Assign User to Group
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700">
                                                    Select Group *
                                                </label>
                                                <select
                                                    required
                                                    value={groupFormData.group_id}
                                                    onChange={(e) =>
                                                        setGroupFormData({ ...groupFormData, group_id: e.target.value })
                                                    }
                                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                                >
                                                    <option value="">Choose a group</option>
                                                    {groups.map((group) => (
                                                        <option key={group.id} value={group.id}>
                                                            {group.name}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
                                        <button
                                            type="submit"
                                            className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-purple-600 text-base font-medium text-white hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 sm:ml-3 sm:w-auto sm:text-sm"
                                        >
                                            Assign Group
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setShowGroupModal(false)}
                                            className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
