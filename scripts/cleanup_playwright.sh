#!/bin/bash
# Cleanup Playwright and Chrome zombie processes

echo "🧹 Cleaning up Playwright and Chrome..."

# Kill processes
pkill -9 -f "chrome"
pkill -9 -f "chromium"
pkill -9 -f "playwright"

# Remove lock files
find chrome_custom_profile -name "SingletonLock" -delete
find chrome_social_profile -name "SingletonLock" -delete
find /var/folders -name "SingletonSocket" -delete 2>/dev/null
find /var/folders -name "SingletonCookie" -delete 2>/dev/null

echo "✅ Cleanup complete."
