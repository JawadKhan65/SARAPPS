'use client';

import { useEffect } from 'react';
import { useAdminStore } from '@/lib/store';

export function AdminProvider({ children }) {
    useEffect(() => {
        // Clean up old undefined cookies
        document.cookie = 'access_token=; path=/; max-age=0';
        document.cookie = 'refresh_token=; path=/; max-age=0';
        
        useAdminStore.getState().checkAuth();
    }, []);

    return <>{children}</>;
}

export default AdminProvider;
