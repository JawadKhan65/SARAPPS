'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminAPI } from '@/lib/api';
import { useAdminStore } from '@/lib/store';
import {
    Play, Pause, Settings, TrendingUp, Database,
    AlertCircle, CheckCircle, Clock, XCircle, Loader2, ChevronDown, ChevronRight
} from 'lucide-react';

export default function CrawlersPage() {
    const router = useRouter();
    const { isAuthenticated } = useAdminStore();
    const [crawlers, setCrawlers] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedCrawler, setSelectedCrawler] = useState(null);
    const [expandedCrawlers, setExpandedCrawlers] = useState(new Set());
    const [configModal, setConfigModal] = useState(null);
    const [jobStatuses, setJobStatuses] = useState({});
    const [workerHealth, setWorkerHealth] = useState(null);
    const [startingCrawlers, setStartingCrawlers] = useState(new Set());

    // Check authentication in useEffect to avoid rendering errors
    useEffect(() => {
        if (!isAuthenticated) {
            router.push('/login');
        }
    }, [isAuthenticated, router]);

    useEffect(() => {
        if (!isAuthenticated) return;

        loadCrawlers();
        loadStats();
        loadWorkerHealth();
        
        const interval = setInterval(() => {
            loadCrawlers();
            loadStats();
            loadWorkerHealth();
            loadJobStatuses();
        }, 3000); // Refresh every 3s
        
        return () => clearInterval(interval);
    }, [isAuthenticated]);

    if (!isAuthenticated) {
        return null;
    }

    const loadCrawlers = async () => {
        try {
            const response = await adminAPI.listCrawlers();
            setCrawlers(response.data.crawlers || []);
        } catch (err) {
            console.error('Failed to load crawlers:', err);
            setError('Failed to load crawlers');
        } finally {
            setLoading(false);
        }
    };

    const loadStats = async () => {
        try {
            const response = await adminAPI.getCrawlerStats();
            setStats(response.data);
        } catch (err) {
            console.error('Failed to load stats:', err);
        }
    };

    const loadWorkerHealth = async () => {
        try {
            const response = await adminAPI.getWorkersHealth();
            setWorkerHealth(response.data);
        } catch (err) {
            console.error('Failed to load worker health:', err);
        }
    };

    const loadJobStatuses = async () => {
        // Load job status for all running crawlers
        const runningCrawlers = crawlers.filter(c => c.is_running);
        const statusPromises = runningCrawlers.map(async (crawler) => {
            try {
                const response = await adminAPI.getCrawlerJobStatus(crawler.id);
                return { id: crawler.id, status: response.data };
            } catch (err) {
                console.error(`Failed to load job status for ${crawler.id}:`, err);
                return { id: crawler.id, status: null };
            }
        });

        const statuses = await Promise.all(statusPromises);
        const statusMap = {};
        statuses.forEach(({ id, status }) => {
            if (status) statusMap[id] = status;
        });
        setJobStatuses(statusMap);
    };

    const handleStartCrawler = async (crawlerId) => {
        // Add to starting set to show loading state
        setStartingCrawlers(prev => new Set(prev).add(crawlerId));
        
        try {
            await adminAPI.startCrawler(crawlerId);
            
            // Start polling job status immediately
            setTimeout(() => {
                loadJobStatuses();
            }, 1000);
            
            await loadCrawlers();
        } catch (err) {
            setError('Failed to start crawler: ' + (err.response?.data?.error || err.message));
        } finally {
            // Remove from starting set after a delay
            setTimeout(() => {
                setStartingCrawlers(prev => {
                    const newSet = new Set(prev);
                    newSet.delete(crawlerId);
                    return newSet;
                });
            }, 2000);
        }
    };

    const handleStopCrawler = async (crawlerId) => {
        try {
            await adminAPI.stopCrawler(crawlerId);
            loadCrawlers();
        } catch (err) {
            setError('Failed to stop crawler: ' + err.response?.data?.error);
        }
    };

    const handleSaveConfig = async () => {
        if (!selectedCrawler) return;

        try {
            await adminAPI.updateCrawlerConfig(selectedCrawler.id, {
                is_active: selectedCrawler.is_active,
                min_uniqueness_threshold: selectedCrawler.min_uniqueness_threshold
            });
            setConfigModal(false);
            setSelectedCrawler(null);
            loadCrawlers();
        } catch (err) {
            setError('Failed to update crawler config: ' + err.response?.data?.error);
        }
    };

    const handleSettings = (crawler) => {
        setSelectedCrawler(crawler);
        setConfigModal(true);
    };

    const toggleExpanded = (crawlerId) => {
        const newExpanded = new Set(expandedCrawlers);
        if (newExpanded.has(crawlerId)) {
            newExpanded.delete(crawlerId);
        } else {
            newExpanded.add(crawlerId);
        }
        setExpandedCrawlers(newExpanded);
    };

    const getStatusColor = (crawler) => {
        if (crawler.is_running) return 'text-green-600 bg-green-50';
        if (crawler.last_error) return 'text-red-600 bg-red-50';
        if (!crawler.is_active) return 'text-gray-600 bg-gray-50';
        return 'text-blue-600 bg-blue-50';
    };

    const getStatusIcon = (crawler) => {
        if (crawler.is_running) return <Loader2 className="w-4 h-4 animate-spin" />;
        if (crawler.last_error) return <XCircle className="w-4 h-4" />;
        if (!crawler.is_active) return <AlertCircle className="w-4 h-4" />;
        return <CheckCircle className="w-4 h-4" />;
    };

    const getStatusText = (crawler) => {
        if (crawler.is_running) return `Running (${crawler.progress_percentage?.toFixed(1) || 0}%)`;
        if (crawler.last_error) return 'Error';
        if (!crawler.is_active) return 'Disabled';
        return 'Ready';
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Header */}
                <div className="mb-8">
                    <div className="flex justify-between items-center mb-2">
                        <div>
                            <h1 className="text-4xl font-bold text-gray-900 flex items-center gap-3">
                                Data Crawlers
                                {workerHealth && (
                                    <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${
                                        workerHealth.healthy && workerHealth.workers > 0
                                            ? 'text-green-700 bg-green-50 border border-green-200'
                                            : 'text-red-700 bg-red-50 border border-red-200'
                                    }`}>
                                        <span className={`w-2 h-2 rounded-full ${
                                            workerHealth.healthy && workerHealth.workers > 0
                                                ? 'bg-green-500 animate-pulse'
                                                : 'bg-red-500'
                                        }`}></span>
                                        {workerHealth.workers || 0} Worker{workerHealth.workers !== 1 ? 's' : ''}
                                    </span>
                                )}
                            </h1>
                            <p className="text-gray-600 mt-1">
                                Manage and monitor your data collection pipelines
                            </p>
                        </div>
                        <button
                            onClick={() => router.push('/')}
                            className="px-4 py-2 bg-white text-gray-700 rounded-lg shadow-sm hover:shadow-md transition-shadow border border-gray-200"
                        >
                            ← Dashboard
                        </button>
                    </div>
                    {workerHealth && !workerHealth.healthy && (
                        <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-2">
                            <AlertCircle className="w-4 h-4 text-amber-600" />
                            <span className="text-sm text-amber-700">
                                Warning: No workers are currently running. Crawlers cannot start without active workers.
                            </span>
                        </div>
                    )}
                </div>

                {/* Stats Overview */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                    <StatCard
                        icon={<Database className="w-5 h-5" />}
                        label="Total Crawlers"
                        value={crawlers.length}
                        color="blue"
                    />
                    <StatCard
                        icon={<Play className="w-5 h-5" />}
                        label="Running"
                        value={crawlers.filter(c => c.is_running).length}
                        color="green"
                    />
                    <StatCard
                        icon={<TrendingUp className="w-5 h-5" />}
                        label="Total Items"
                        value={crawlers.reduce((sum, c) => sum + (c.items_scraped || 0), 0).toLocaleString()}
                        color="purple"
                    />
                    <StatCard
                        icon={<CheckCircle className="w-5 h-5" />}
                        label="Unique Items"
                        value={stats?.total_items?.toLocaleString() || crawlers.reduce((sum, c) => sum + (c.unique_images_added || 0), 0).toLocaleString()}
                        color="indigo"
                    />
                </div>

                {error && (
                    <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
                        <AlertCircle className="w-5 h-5 text-red-600" />
                        <span className="text-red-700">{error}</span>
                        <button
                            onClick={() => setError('')}
                            className="ml-auto text-red-600 hover:text-red-800"
                        >
                            ×
                        </button>
                    </div>
                )}

                {loading ? (
                    <div className="text-center py-12 bg-white rounded-2xl shadow-sm">
                        <Loader2 className="w-12 h-12 animate-spin mx-auto text-blue-600" />
                        <p className="mt-4 text-gray-600">Loading crawlers...</p>
                    </div>
                ) : crawlers.length > 0 ? (
                    <div className="space-y-4">
                        {crawlers.map((crawler) => (
                            <CrawlerCard
                                key={crawler.id}
                                crawler={crawler}
                                jobStatus={jobStatuses[crawler.id]}
                                isStarting={startingCrawlers.has(crawler.id)}
                                expanded={expandedCrawlers.has(crawler.id)}
                                onToggleExpand={() => toggleExpanded(crawler.id)}
                                onStart={() => handleStartCrawler(crawler.id)}
                                onStop={() => handleStopCrawler(crawler.id)}
                                onSettings={() => handleSettings(crawler)}
                                getStatusColor={getStatusColor}
                                getStatusIcon={getStatusIcon}
                                getStatusText={getStatusText}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="text-center py-16 bg-white rounded-2xl shadow-sm">
                        <Database className="w-16 h-16 mx-auto text-gray-300 mb-4" />
                        <p className="text-gray-500 text-lg">No crawlers configured</p>
                        <button className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                            + Add Crawler
                        </button>
                    </div>
                )}
            </div>

            {/* Settings Modal */}
            {configModal && selectedCrawler && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
                        <div className="p-6 border-b border-gray-200">
                            <div className="flex items-center justify-between">
                                <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                                    <Settings className="w-6 h-6" />
                                    Crawler Settings
                                </h2>
                                <button
                                    onClick={() => setConfigModal(false)}
                                    className="text-gray-400 hover:text-gray-600 transition-colors"
                                >
                                    <XCircle className="w-6 h-6" />
                                </button>
                            </div>
                        </div>

                        <div className="p-6 space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Crawler Name
                                </label>
                                <input
                                    type="text"
                                    value={selectedCrawler.name}
                                    readOnly
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-600"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Website URL
                                </label>
                                <input
                                    type="text"
                                    value={selectedCrawler.website_url}
                                    readOnly
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-600"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Scraper Module
                                </label>
                                <input
                                    type="text"
                                    value={selectedCrawler.scraper_module || 'Auto-detect'}
                                    readOnly
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-600"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Uniqueness Threshold (%)
                                </label>
                                <input
                                    type="number"
                                    value={selectedCrawler.min_uniqueness_threshold || 30}
                                    onChange={(e) => setSelectedCrawler({ ...selectedCrawler, min_uniqueness_threshold: parseFloat(e.target.value) })}
                                    min="0"
                                    max="100"
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                />
                                <p className="text-xs text-gray-500 mt-1">
                                    Auto-stop crawler if uniqueness drops below this percentage
                                </p>
                            </div>

                            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                                <div>
                                    <p className="font-medium text-gray-900">Active</p>
                                    <p className="text-sm text-gray-600">Enable or disable this crawler</p>
                                </div>
                                <label className="relative inline-flex items-center cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={selectedCrawler.is_active}
                                        onChange={(e) => setSelectedCrawler({ ...selectedCrawler, is_active: e.target.checked })}
                                        className="sr-only peer"
                                    />
                                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                                </label>
                            </div>
                        </div>

                        <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
                            <button
                                onClick={() => setConfigModal(false)}
                                className="px-6 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors font-medium"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSaveConfig}
                                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
                            >
                                Save Changes
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function StatCard({ icon, label, value, color }) {
    const colors = {
        blue: 'from-blue-500 to-blue-600',
        green: 'from-green-500 to-green-600',
        purple: 'from-purple-500 to-purple-600',
        indigo: 'from-indigo-500 to-indigo-600',
    };

    return (
        <div className="bg-white rounded-xl shadow-sm p-6 border border-gray-100">
            <div className={`inline-flex p-3 rounded-lg bg-gradient-to-br ${colors[color]} text-white mb-4`}>
                {icon}
            </div>
            <p className="text-2xl font-bold text-gray-900">{value}</p>
            <p className="text-sm text-gray-600">{label}</p>
        </div>
    );
}

function CrawlerCard({ crawler, jobStatus, isStarting, expanded, onToggleExpand, onStart, onStop, onSettings, getStatusColor, getStatusIcon, getStatusText }) {
    // Get real-time progress from job status
    const progress = jobStatus?.progress;
    const heartbeat = jobStatus?.heartbeat;
    const isStalled = jobStatus?.heartbeat_stale === true;
    const errorDetails = jobStatus?.error_details;
    
    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-all">
            {/* Main Card Content */}
            <div className="p-6">
                <div className="flex items-start justify-between">
                    {/* Left: Info */}
                    <div className="flex-1">
                        <div className="flex items-center gap-3 mb-3">
                            <button
                                onClick={onToggleExpand}
                                className="text-gray-400 hover:text-gray-600"
                            >
                                {expanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                            </button>
                            <h3 className="text-xl font-semibold text-gray-900">
                                {crawler.name}
                            </h3>
                            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(crawler)}`}>
                                {getStatusIcon(crawler)}
                                {getStatusText(crawler)}
                            </span>
                            {isStalled && (
                                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium text-amber-600 bg-amber-50 border border-amber-200">
                                    <AlertCircle className="w-4 h-4" />
                                    Stalled
                                </span>
                            )}
                        </div>

                        <div className="ml-8 space-y-2">
                            <p className="text-sm text-gray-600 flex items-center gap-2">
                                <span className="font-medium">URL:</span>
                                <a href={crawler.website_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                                    {crawler.website_url}
                                </a>
                            </p>

                            <div className="flex items-center gap-6 text-sm">
                                <div className="flex items-center gap-2">
                                    <TrendingUp className="w-4 h-4 text-gray-400" />
                                    <span className="text-gray-600">
                                        <span className="font-semibold text-gray-900">{(crawler.items_scraped || 0).toLocaleString()}</span> total items
                                    </span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <CheckCircle className="w-4 h-4 text-green-500" />
                                    <span className="text-gray-600">
                                        <span className="font-semibold text-gray-900">{(crawler.unique_images_added || 0).toLocaleString()}</span> unique
                                    </span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Database className="w-4 h-4 text-purple-500" />
                                    <span className="text-gray-600">
                                        <span className="font-semibold text-gray-900">{crawler.uniqueness_percentage?.toFixed(1) || 0}%</span> uniqueness
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Right: Actions */}
                    <div className="flex items-center gap-2 ml-4">
                        {crawler.is_running || isStarting ? (
                            <>
                                <button
                                    onClick={onStop}
                                    disabled={isStarting}
                                    className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors shadow-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    <Pause className="w-4 h-4" />
                                    Cancel
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={onStart}
                                disabled={!crawler.is_active || isStarting}
                                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors shadow-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isStarting ? (
                                    <>
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Starting...
                                    </>
                                ) : (
                                    <>
                                        <Play className="w-4 h-4" />
                                        Start
                                    </>
                                )}
                            </button>
                        )}
                        <button
                            onClick={onSettings}
                            className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
                        >
                            <Settings className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Real-time Progress (from job status) */}
                {crawler.is_running && progress && (
                    <div className="ml-8 mt-4">
                        <div className="flex items-center justify-between text-sm mb-2">
                            <div className="flex items-center gap-2">
                                <span className="text-gray-600 font-medium">Progress</span>
                                {heartbeat && (
                                    <span className="flex items-center gap-1 text-xs text-green-600">
                                        <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                                        Live
                                    </span>
                                )}
                            </div>
                            <span className="text-gray-900 font-semibold">
                                {progress.current || 0} / {progress.total || 0} items • {progress.percentage || 0}%
                            </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden mb-2">
                            <div
                                className="bg-gradient-to-r from-blue-500 to-green-500 h-2.5 rounded-full transition-all duration-500"
                                style={{ width: `${Math.min(progress.percentage || 0, 100)}%` }}
                            />
                        </div>
                        {progress.message && (
                            <p className="text-xs text-gray-600 flex items-center gap-1.5">
                                <Loader2 className="w-3 h-3 animate-spin" />
                                {progress.message}
                            </p>
                        )}
                    </div>
                )}
                
                {/* Fallback progress bar (database values) */}
                {crawler.is_running && !progress && (
                    <div className="ml-8 mt-4">
                        <div className="flex items-center justify-between text-sm mb-2">
                            <span className="text-gray-600 font-medium">Progress</span>
                            <span className="text-gray-900 font-semibold">
                                {crawler.current_run_items || 0} items • Batch {crawler.current_batch || 0}
                            </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                            <div
                                className="bg-gradient-to-r from-blue-500 to-green-500 h-2.5 rounded-full transition-all duration-500 animate-pulse"
                                style={{ width: `${Math.min(crawler.progress_percentage || 0, 100)}%` }}
                            />
                        </div>
                    </div>
                )}
            </div>

            {/* Expanded Details */}
            {expanded && (
                <div className="border-t border-gray-200 bg-gray-50 p-6 space-y-4">
                    {/* Statistics Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <DetailItem label="Total Runs" value={crawler.total_runs || 0} />
                        <DetailItem label="Duplicates" value={(crawler.duplicate_count || 0).toLocaleString()} />
                        <DetailItem
                            label="Last Run"
                            value={crawler.last_completed_at ? new Date(crawler.last_completed_at).toLocaleString() : 'Never'}
                        />
                        <DetailItem
                            label="Duration"
                            value={crawler.last_run_duration_minutes ? `${crawler.last_run_duration_minutes.toFixed(1)}m` : 'N/A'}
                        />
                        <DetailItem
                            label="Uniqueness Threshold"
                            value={`${crawler.min_uniqueness_threshold || 30}%`}
                        />
                        <DetailItem label="Errors" value={crawler.consecutive_errors || 0} />
                        <DetailItem
                            label="Run Type"
                            value={crawler.run_type || 'N/A'}
                        />
                        <DetailItem
                            label="Module"
                            value={crawler.scraper_module || 'Auto'}
                        />
                    </div>

                    {/* Real-time Job Status Info */}
                    {jobStatus && (
                        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                            <div className="flex items-start gap-2">
                                <Clock className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                                <div className="flex-1">
                                    <p className="font-medium text-blue-900 mb-2">Job Status</p>
                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                                        <div>
                                            <span className="text-blue-600 font-medium">Job ID:</span>
                                            <p className="text-blue-900 font-mono text-xs">{jobStatus.job_id?.substring(0, 8)}...</p>
                                        </div>
                                        <div>
                                            <span className="text-blue-600 font-medium">Status:</span>
                                            <p className="text-blue-900 capitalize">{jobStatus.status}</p>
                                        </div>
                                        {jobStatus.attempt && (
                                            <div>
                                                <span className="text-blue-600 font-medium">Attempt:</span>
                                                <p className="text-blue-900">{jobStatus.attempt} / {jobStatus.max_attempts}</p>
                                            </div>
                                        )}
                                        {jobStatus.started_at && (
                                            <div>
                                                <span className="text-blue-600 font-medium">Started:</span>
                                                <p className="text-blue-900">{new Date(jobStatus.started_at).toLocaleTimeString()}</p>
                                            </div>
                                        )}
                                    </div>
                                    {heartbeat && (
                                        <div className="mt-2 pt-2 border-t border-blue-200">
                                            <span className="text-blue-600 font-medium text-sm flex items-center gap-2">
                                                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                                                Last Heartbeat: {new Date(heartbeat.last_beat).toLocaleTimeString()}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Error Details (from job status) */}
                    {errorDetails && (
                        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                            <div className="flex items-start gap-2">
                                <XCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                                <div className="flex-1">
                                    <p className="font-medium text-red-900 mb-2">Job Error Details</p>
                                    <div className="space-y-2 text-sm">
                                        {jobStatus.error_message && (
                                            <div>
                                                <span className="text-red-600 font-medium">Message:</span>
                                                <p className="text-red-900 mt-1">{jobStatus.error_message}</p>
                                            </div>
                                        )}
                                        {jobStatus.error_category && (
                                            <div className="flex items-center gap-4">
                                                <span className="text-red-600 font-medium">Category: <span className="text-red-900 font-normal capitalize">{jobStatus.error_category}</span></span>
                                                <span className="text-red-600 font-medium">Retryable: <span className="text-red-900 font-normal">{jobStatus.error_retryable === 'True' ? 'Yes' : 'No'}</span></span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Legacy Error (from database) */}
                    {crawler.last_error && !errorDetails && (
                        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                            <div className="flex items-start gap-2">
                                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                                <div>
                                    <p className="font-medium text-red-900">Last Error</p>
                                    <p className="text-sm text-red-700 mt-1">{crawler.last_error}</p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function DetailItem({ label, value }) {
    return (
        <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide font-medium mb-1">{label}</p>
            <p className="text-sm font-semibold text-gray-900">{value}</p>
        </div>
    );
}
