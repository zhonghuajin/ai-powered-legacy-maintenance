// Initialize global state to prevent duplicate initialization
if (!window.__stainingState) {
    window.__stainingState = {
        // A single Set to store unique IDs and maintain insertion order
        BLOCK_SET: new Set(),
        // Configuration for the Java Middleware Server
        MONITOR_URL: 'http://localhost:19899',
        POLL_INTERVAL_MS: 2000, // Poll every 2 seconds
        isPolling: false
    };
}

/**
 * Core instrumentation function.
 * @param {number} id - The unique identifier of the code block
 */
window.staining = function(id) {
    const state = window.__stainingState;
    // Set automatically guarantees uniqueness and maintains insertion order
    state.BLOCK_SET.add(id);
};

/**
 * Helper method: Clear the collected data.
 */
window.staining.clear = function() {
    const state = window.__stainingState;
    state.BLOCK_SET.clear();
};

/**
 * Push collected logs to the Java Middleware Server
 */
window.staining.pushLogs = function() {
    const state = window.__stainingState;
    if (state.BLOCK_SET.size === 0) return Promise.resolve();

    // Convert Set to comma-separated string to simplify Java parsing
    const logData = Array.from(state.BLOCK_SET).join(',');

    return fetch(`${state.MONITOR_URL}/push`, {
        method: 'POST',
        headers: {
            'Content-Type': 'text/plain'
        },
        body: logData
    }).then(response => {
        if (response.ok) {
            console.log('[InstrumentLog] Successfully pushed logs to monitor.');
        } else {
            console.error('[InstrumentLog] Failed to push logs.');
        }
    }).catch(err => {
        console.error('[InstrumentLog] Error pushing logs:', err);
    });
};

/**
 * Start polling the middleware for user intents (clear/flush)
 * And report the current log count while polling, so that the intermediate service's /status command can retrieve the latest status.
 */
window.staining.startPolling = function() {
    const state = window.__stainingState;
    if (state.isPolling) return;
    state.isPolling = true;

    setInterval(() => {
        const currentCount = state.BLOCK_SET.size;
        
        fetch(`${state.MONITOR_URL}/poll?count=${currentCount}`, {
            method: 'GET'
        })
        .then(response => response.json())
        .then(data => {
            if (data.flush) {
                console.log('[InstrumentLog] Received FLUSH intent. Pushing logs...');
                window.staining.pushLogs().then(() => {
                    window.staining.clear();
                });
            } else if (data.clear) {
                console.log('[InstrumentLog] Received CLEAR intent. Clearing local logs...');
                window.staining.clear();
            }
        })
        .catch(err => {
        });
    }, state.POLL_INTERVAL_MS);
};

// Start the polling mechanism automatically when the script loads
window.staining.startPolling();