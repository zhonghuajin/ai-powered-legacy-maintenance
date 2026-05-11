package com.instrumentor.enginerring.monitor;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;

import java.io.*;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;

public class RedisLogMonitorServer {

    private static final int DEFAULT_PORT = 19898;
    private static final DateTimeFormatter TS_FMT = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");
    private static final AtomicBoolean FLUSHED = new AtomicBoolean(false);

    // Manager info
    private static String managerIp = null;
    private static int managerPort = -1;

    // Redis Pool
    private static JedisPool jedisPool;

    public static void main(String[] args) {
        // Initialize Redis connection pool (default connects to local 6379)
        jedisPool = new JedisPool("127.0.0.1", 6379);
        
        RedisLogMonitorServer server = new RedisLogMonitorServer();
        server.startHttpServer(DEFAULT_PORT);
    }

    // ======================== HTTP Server ========================

    private void startHttpServer(int initialPort) {
        int port = initialPort;
        int maxTries = 100;
        HttpServer server = null;

        for (int i = 0; i < maxTries; i++) {
            try {
                server = HttpServer.create(new InetSocketAddress(port), 0);
                break;
            } catch (IOException e) {
                if (i == maxTries - 1) {
                    log("Exception occurred while starting HTTP service on port %d: %s", port, e.getMessage());
                    return;
                }
                port++;
            }
        }

        if (server == null) {
            log("Unable to start HTTP service, port range %d - %d all occupied.", initialPort, initialPort + maxTries - 1);
            return;
        }

        try {
            server.createContext("/clear", this::handleClear);
            server.createContext("/flush", this::handleFlush);
            server.createContext("/status", this::handleStatus);
            server.createContext("/setManager", this::handleSetManager);
            server.setExecutor(null);
            server.start();
            log("PHP Redis Instrumentor monitoring service started: http://localhost:%d", port);
        } catch (Exception e) {
            log("Unable to configure or start HTTP service: %s", e.getMessage());
        }
    }

    private void handleClear(HttpExchange exchange) throws IOException {
        clearNow(); // 复用提取出的 clearNow 方法
        sendTextResponse(exchange, 200, "[LogMonitor] Logs cleared from Redis.\n");
    }

    private void handleStatus(HttpExchange exchange) throws IOException {
        int totalThreads = 0;
        long totalLogs = 0;

        try (Jedis jedis = jedisPool.getResource()) {
            List<String> pids = jedis.lrange("instrumentor:pids_order", 0, -1);
            totalThreads = pids.size();
            for (String pid : pids) {
                totalLogs += jedis.llen("instrumentor:log:" + pid);
            }
        }

        StringBuilder sb = new StringBuilder();
        sb.append("[LogMonitor] Current Status (PHP Redis)\n");
        sb.append("  Total Threads (PIDs) : ").append(totalThreads).append("\n");
        sb.append("  Total Basic Log Entries: ").append(totalLogs).append("\n");
        sb.append("  Total Event Log Entries: 0 (Not supported in PHP yet)\n");
        if (managerIp != null) {
            sb.append("  Manager Address: http://").append(managerIp).append(":").append(managerPort).append("\n");
        }
        sendTextResponse(exchange, 200, sb.toString());
    }

    private void handleFlush(HttpExchange exchange) throws IOException {
        resetFlushState();
        flushNow("manual_http");
        sendTextResponse(exchange, 200, "[LogMonitor] Flush triggered. Files sent to manager or saved locally, and logs cleared.\n");
    }

    private void handleSetManager(HttpExchange exchange) throws IOException {
        Map<String, String> params = parseQuery(exchange.getRequestURI().getRawQuery());
        String ip = params.get("ip");
        String portStr = params.get("port");

        if (ip != null && portStr != null) {
            try {
                managerIp = ip;
                managerPort = Integer.parseInt(portStr);
                String msg = String.format("[LogMonitor] Manager set to %s:%d\n", managerIp, managerPort);
                log(msg.trim());
                sendTextResponse(exchange, 200, msg);
            } catch (NumberFormatException e) {
                sendTextResponse(exchange, 400, "[LogMonitor] Invalid port number.\n");
            }
        } else {
            sendTextResponse(exchange, 400, "[LogMonitor] Missing ip or port parameters.\n");
        }
    }

    // ======================== Core Logic (Reused) ========================

    public static void flushNow(String source) {
        if (!FLUSHED.compareAndSet(false, true)) {
            log("flushNow(%s) skipped — already flushed.", source);
            return;
        }

        try {
            String ts = LocalDateTime.now().format(TS_FMT);
            String logFileName = "instrumentor-log-" + ts + "-" + source + ".txt";

            // 1. Build Snapshot from Redis
            LinkedHashMap<Long, List<Integer>> logSnapshot = buildSnapshotFromRedis();

            // 2. Reuse the original formatting and output logic
            if (!logSnapshot.isEmpty()) {
                String logContent = formatLogSnapshotStatic(logSnapshot);
                handleFileOutput(logFileName, logContent, source);
            } else {
                log("flushNow(%s): no logs to flush.", source);
            }

            // 3. 在 flush 之后执行 clear 操作
            clearNow();

        } catch (Exception e) {
            log("flushNow(%s) failed: %s", source, e.getMessage());
            e.printStackTrace(System.err);
        }
    }

    /**
     * 提取出的清理 Redis 数据的公共方法
     */
    public static void clearNow() {
        try (Jedis jedis = jedisPool.getResource()) {
            Set<String> keys = jedis.keys("instrumentor:*");
            if (keys != null && !keys.isEmpty()) {
                jedis.del(keys.toArray(new String[0]));
                log("clearNow: successfully cleared %d keys from Redis.", keys.size());
            } else {
                log("clearNow: no keys found to clear.");
            }
        } catch (Exception e) {
            log("clearNow failed: %s", e.getMessage());
        }
    }

    private static LinkedHashMap<Long, List<Integer>> buildSnapshotFromRedis() {
        LinkedHashMap<Long, List<Integer>> snapshot = new LinkedHashMap<>();
        try (Jedis jedis = jedisPool.getResource()) {
            List<String> pids = jedis.lrange("instrumentor:pids_order", 0, -1);
            for (String pidStr : pids) {
                try {
                    long pid = Long.parseLong(pidStr);
                    List<String> logStrs = jedis.lrange("instrumentor:log:" + pidStr, 0, -1);
                    if (!logStrs.isEmpty()) {
                        // Convert to Integer and deduplicate (consistent with Java side logic)
                        List<Integer> logs = logStrs.stream()
                                .map(Integer::parseInt)
                                .distinct()
                                .collect(Collectors.toList());
                        snapshot.put(pid, logs);
                    }
                } catch (NumberFormatException e) {
                    log("Invalid PID in Redis: " + pidStr);
                }
            }
        }
        return snapshot;
    }

    public static void resetFlushState() {
        FLUSHED.set(false);
    }

    // Reuse: Format Snapshot
    private static String formatLogSnapshotStatic(LinkedHashMap<Long, List<Integer>> snapshot) {
        StringBuilder sb = new StringBuilder();

        LinkedHashMap<String, List<Map.Entry<Long, List<Integer>>>> groups = new LinkedHashMap<>();
        for (Map.Entry<Long, List<Integer>> entry : snapshot.entrySet()) {
            String canonicalKey = entry.getValue().stream()
                    .distinct()
                    .sorted()
                    .map(String::valueOf)
                    .collect(Collectors.joining(","));
            groups.computeIfAbsent(canonicalKey, k -> new ArrayList<>()).add(entry);
        }

        int originalCount = snapshot.size();
        int dedupedCount = groups.size();
        sb.append("# InstrumentLog (Deduplicated) @ ")
                .append(LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)).append("\n");
        sb.append("# Original thread (PID) count: ").append(originalCount)
                .append(", Deduplicated group count: ").append(dedupedCount).append("\n\n");

        int order = 1;
        for (Map.Entry<String, List<Map.Entry<Long, List<Integer>>>> groupEntry : groups.entrySet()) {
            List<Map.Entry<Long, List<Integer>>> group = groupEntry.getValue();
            Map.Entry<Long, List<Integer>> representative = group.get(0);
            long threadId = representative.getKey();
            List<Integer> logs = representative.getValue();

            sb.append(String.format("[Thread-%d] (Group Order: #%d, Count: %d)", threadId, order++, logs.size()));

            if (group.size() > 1) {
                String mergedThreads = group.stream()
                        .map(e -> "Thread-" + e.getKey())
                        .collect(Collectors.joining(", "));
                sb.append(String.format("  # Merged from %d threads: %s", group.size(), mergedThreads));
            }
            sb.append("\n");

            if (!logs.isEmpty()) {
                sb.append("  ");
                for (int i = 0; i < logs.size(); i++) {
                    if (i > 0) sb.append(" -> ");
                    sb.append(logs.get(i));
                }
                sb.append("\n");
            }
        }
        return sb.toString();
    }

    // Reuse: Send to Manager or save locally
    private static void handleFileOutput(String fileName, String content, String source) throws IOException {
        if (managerIp != null && managerPort > 0) {
            String targetUrl = "http://" + managerIp + ":" + managerPort + "/upload";
            try {
                URL url = new URL(targetUrl);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setDoOutput(true);
                conn.setRequestMethod("POST");
                
                String boundary = "----WebKitFormBoundary" + System.currentTimeMillis();
                conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

                byte[] data = content.getBytes(StandardCharsets.UTF_8);

                try (OutputStream os = conn.getOutputStream();
                     PrintWriter writer = new PrintWriter(new OutputStreamWriter(os, StandardCharsets.UTF_8), true)) {
                    
                    writer.append("--").append(boundary).append("\r\n");
                    writer.append("Content-Disposition: form-data; name=\"file\"; filename=\"").append(fileName).append("\"\r\n");
                    writer.append("Content-Type: application/octet-stream\r\n\r\n");
                    writer.flush();
                    
                    os.write(data);
                    os.flush();
                    
                    writer.append("\r\n").append("--").append(boundary).append("--\r\n");
                    writer.flush();
                }

                int responseCode = conn.getResponseCode();
                if (responseCode == 200) {
                    log("flushNow(%s): successfully sent %s to Manager at %s", source, fileName, targetUrl);
                } else {
                    log("flushNow(%s): failed to send %s to Manager. Response code: %d", source, fileName, responseCode);
                    saveLocally(fileName, content, source);
                }
            } catch (Exception e) {
                log("flushNow(%s): exception sending %s to Manager: %s", source, fileName, e.getMessage());
                saveLocally(fileName, content, source);
            }
        } else {
            saveLocally(fileName, content, source);
        }
    }

    private static void saveLocally(String fileName, String content, String source) throws IOException {
        Files.write(Paths.get(fileName), content.getBytes(StandardCharsets.UTF_8));
        log("flushNow(%s): log written locally to %s", source, Paths.get(fileName).toAbsolutePath());
    }

    // ======================== Utility ========================

    private static void log(String fmt, Object... args) {
        System.err.printf("[LogMonitor] " + fmt + "%n", args);
    }

    private Map<String, String> parseQuery(String rawQuery) throws UnsupportedEncodingException {
        Map<String, String> params = new LinkedHashMap<>();
        if (rawQuery == null || rawQuery.isEmpty()) return params;
        for (String pair : rawQuery.split("&")) {
            String[] kv = pair.split("=", 2);
            params.put(URLDecoder.decode(kv[0], "UTF-8"),
                    kv.length > 1 ? URLDecoder.decode(kv[1], "UTF-8") : "");
        }
        return params;
    }

    private void sendTextResponse(HttpExchange exchange, int statusCode, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }
}