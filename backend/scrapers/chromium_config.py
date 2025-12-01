"""
Centralized Chromium Configuration for Docker Environment

This module provides standardized Chromium launch arguments optimized for
running Playwright in Docker containers with limited resources.
"""

# Docker-optimized Chromium launch arguments
DOCKER_CHROMIUM_ARGS = [
    # Security & Sandbox
    '--no-sandbox',                          # Disable sandbox (required in Docker)
    '--disable-setuid-sandbox',              # Disable setuid sandbox
    
    # Memory & Performance
    '--disable-dev-shm-usage',               # Use /tmp instead of /dev/shm (prevents crashes)
    '--disable-gpu',                         # Disable GPU hardware acceleration
    '--disable-software-rasterizer',         # Disable software rasterizer
    
    # Features & Extensions
    '--disable-extensions',                  # Disable all extensions
    '--disable-features=VizDisplayCompositor',  # Disable compositor
    '--disable-accelerated-2d-canvas',       # Disable 2D canvas acceleration
    '--disable-features=IsolateOrigins,site-per-process',  # Disable site isolation
    
    # Automation & Detection
    '--disable-blink-features=AutomationControlled',  # Hide automation
    
    # Additional Stability
    '--disable-background-networking',        # Prevent background requests
    '--disable-background-timer-throttling',  # Prevent throttling
    '--disable-backgrounding-occluded-windows',
    '--disable-breakpad',                     # Disable crash reporter
    '--disable-component-extensions-with-background-pages',
    '--disable-default-apps',
    '--disable-hang-monitor',
    '--disable-ipc-flooding-protection',
    '--disable-prompt-on-repost',
    '--disable-sync',
    '--metrics-recording-only',
    '--no-first-run',
    '--safebrowsing-disable-auto-update',
]


def get_chromium_launch_config(headless=True, extra_args=None):
    """
    Get Chromium launch configuration for Playwright.
    
    Args:
        headless: Whether to run in headless mode (default: True)
        extra_args: Additional arguments to append (optional)
    
    Returns:
        dict: Configuration dictionary for playwright.chromium.launch()
    """
    args = DOCKER_CHROMIUM_ARGS.copy()
    
    if extra_args:
        args.extend(extra_args)
    
    return {
        'headless': headless,
        'args': args
    }

