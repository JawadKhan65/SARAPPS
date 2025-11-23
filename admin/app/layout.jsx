import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AdminProvider } from "@/components/AdminProvider";
import AdminHeader from "@/components/AdminHeader";
import { ToastProvider } from "@/components/ui/Toast";

const geistSans = Geist({
    variable: "--font-geist-sans",
    subsets: ["latin"],
});

const geistMono = Geist_Mono({
    variable: "--font-geist-mono",
    subsets: ["latin"],
});

export const metadata = {
    title: "Admin Dashboard - Shoe Type Identification System",
    description: "Administrator panel for managing users, crawlers, and system settings",
};

export default function RootLayout({ children }) {
    return (
        <html lang="en">
            <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
                <ToastProvider>
                    <AdminProvider>
                        <AdminHeader />
                        {children}
                    </AdminProvider>
                </ToastProvider>
            </body>
        </html>
    );
}
