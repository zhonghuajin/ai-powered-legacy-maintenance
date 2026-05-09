<?php

/**
 * Standalone Log Monitor Server
 * Usage: php LogMonitorServer.php
 */

// ======================== Launcher Logic (Port Discovery) ========================
// If running via standard CLI instead of php -S, execute port discovery logic
if (php_sapi_name() === 'cli' && !isset($_SERVER['SERVER_SOFTWARE'])) {
    $host = '0.0.0.0';
    $initialPort = 19898;
    $maxTries = 100;
    $started = false;

    for ($i = 0; $i < $maxTries; $i++) {
        $port = $initialPort + $i;
        
        // Try connecting to the port; if successful, it means the port is occupied
        $connection = @fsockopen($host, $port, $errno, $errstr, 0.1);
        if (is_resource($connection)) {
            fclose($connection);
            continue; // Port occupied, try the next one
        }

        // Port is available, start the built-in server
        echo "[LogMonitor] Instrumentor monitoring service started: http://localhost:{$port}\n";
        
        // Build the startup command, using the current file as the router script
        $command = sprintf('php -S %s:%d %s', $host, $port, escapeshellarg(__FILE__));
        
        // Use passthru to take over I/O and block execution
        passthru($command);
        $started = true;
        break;
    }

    if (!$started) {
        echo "[LogMonitor] Unable to start HTTP service, port range {$initialPort} - " . ($initialPort + $maxTries - 1) . " all occupied.\n";
    }
    exit(0);
}

// ======================== Routing & Business Logic ========================
// The following logic only executes when handling HTTP requests after starting via php -S

$uri = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);

// If requesting an existing static file, let the built-in server handle it
if ($uri !== '/' && file_exists(__DIR__ . $uri)) {
    return false;
}

// Include Composer autoloader for Predis
require __DIR__ . '/../vendor/autoload.php';

// Initialize Predis connection
try {
    $redis = new \Predis\Client([
        'scheme' => 'tcp',
        'host'   => '127.0.0.1',
        'port'   => 6379,
    ]);
    // Test connection
    $redis->ping();
} catch (Exception $e) {
    http_response_code(500);
    die("[LogMonitor] Failed to connect to Redis: " . $e->getMessage() . "\n");
}

header("Content-Type: text/plain; charset=UTF-8");

switch ($uri) {
    case '/clear':
        handleClear($redis);
        break;
    case '/flush':
        handleFlush($redis);
        break;
    case '/status':
        handleStatus($redis);
        break;
    default:
        echo "[LogMonitor] Available endpoints: /clear, /flush, /status\n";
        break;
}

// ======================== Handlers ========================

function handleClear($redis) {
    // Predis keys() returns an array
    $keys = $redis->keys('instrumentor:*');
    if (!empty($keys)) {
        $redis->del($keys);
    }
    echo "[LogMonitor] Logs cleared from Redis.\n";
}

function handleStatus($redis) {
    $pids = $redis->lrange('instrumentor:pids_order', 0, -1);
    $totalLogs = 0;
    
    foreach ($pids as $pid) {
        $totalLogs += $redis->llen('instrumentor:log:' . $pid);
    }

    echo "[LogMonitor] Current Status\n";
    echo "  Total Threads (PIDs) : " . count($pids) . "\n";
    echo "  Total Basic Log Entries: " . $totalLogs . "\n";
}

function handleFlush($redis) {
    $pids = $redis->lrange('instrumentor:pids_order', 0, -1);
    $snapshot = [];

    foreach ($pids as $pid) {
        $logs = $redis->lrange('instrumentor:log:' . $pid, 0, -1);
        if (!empty($logs)) {
            $snapshot[$pid] = array_values(array_unique($logs));
        }
    }

    if (empty($snapshot)) {
        echo "[LogMonitor] flushNow(manual_http): no logs to flush.\n";
        return;
    }

    $ts = date('Ymd_His');
    $fileName = "instrumentor-log-" . $ts . "-manual_http.txt";
    $content = formatLogSnapshotStatic($snapshot);

    file_put_contents(__DIR__ . '/' . $fileName, $content);
    echo "[LogMonitor] Flush triggered. Files saved locally to " . realpath(__DIR__ . '/' . $fileName) . "\n";
}

function formatLogSnapshotStatic($snapshot) {
    $groups = [];
    foreach ($snapshot as $pid => $logs) {
        $canonicalKey = implode(',', $logs);
        if (!isset($groups[$canonicalKey])) {
            $groups[$canonicalKey] = [];
        }
        $groups[$canonicalKey][] = ['pid' => $pid, 'logs' => $logs];
    }

    $originalCount = count($snapshot);
    $dedupedCount = count($groups);

    $sb = "# InstrumentLog (Deduplicated) @ " . date('Y-m-d\TH:i:s') . "\n";
    $sb .= "# Original thread count: {$originalCount}, Deduplicated group count: {$dedupedCount}\n\n";

    $order = 1;
    foreach ($groups as $canonicalKey => $group) {
        $representative = $group[0];
        $pid = $representative['pid'];
        $logs = $representative['logs'];

        $sb .= sprintf("[Thread-%s] (Group Order: #%d, Count: %d)", $pid, $order++, count($logs));

        if (count($group) > 1) {
            $mergedPids = implode(', ', array_map(function($e) { return "Thread-" . $e['pid']; }, $group));
            $sb .= sprintf("  # Merged from %d threads: %s", count($group), $mergedPids);
        }
        $sb .= "\n";

        if (!empty($logs)) {
            $sb .= "  " . implode(' -> ', $logs) . "\n";
        }
    }

    return $sb;
}