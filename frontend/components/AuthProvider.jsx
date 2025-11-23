'use client';

import { useEffect } from 'react';
import { useAuthStore } from '@/lib/store';

export function AuthProvider({ children }) {
    useEffect(() => {
        useAuthStore.getState().checkAuth();
    }, []);

    return <>{children}</>;
}
