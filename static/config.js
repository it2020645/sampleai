/**
 * Frontend Configuration
 * This file loads the API configuration from the backend
 * and makes it available to the frontend
 */

(async function() {
    try {
        // Try to load config from backend first
        const response = await fetch('/api/config', { credentials: 'include' });
        if (response.ok) {
            const config = await response.json();
            window.API_BASE = config.api_base;
            window.ENVIRONMENT = config.environment;
            window.GOOGLE_CLIENT_ID = config.google_client_id;
            console.log('✅ Config loaded from backend:', config);
        }
    } catch (error) {
        // Fall back to relative path if backend config unavailable
        console.warn('⚠️ Could not load config from backend, using defaults:', error.message);
        window.API_BASE = '';
        window.ENVIRONMENT = 'development';
        window.GOOGLE_CLIENT_ID = '';
    }
    
    // Ensure API_BASE is always set
    if (window.API_BASE === undefined || window.API_BASE === null) {
        window.API_BASE = '';
    }
    
    console.log(`🔧 API Base URL: ${window.API_BASE}`);
    console.log(`🔧 Environment: ${window.ENVIRONMENT}`);
    if (window.GOOGLE_CLIENT_ID) {
        console.log(`🔧 Google OAuth configured`);
    } else {
        console.warn(`⚠️ Google Client ID not configured - OAuth sign-in will fail`);
    }
})();
