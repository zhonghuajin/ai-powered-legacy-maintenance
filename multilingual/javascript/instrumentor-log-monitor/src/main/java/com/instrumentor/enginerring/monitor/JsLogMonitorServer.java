package com.instrumentor.enginerring.monitor;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

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

public class JsLogMonitorServer {

    private static final int DEFAULT_PORT = 19899;
    private static final DateTimeFormatter TS_FMT = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");

    private static String managerIp = null;
    private static int managerPort = -1;

    private static final AtomicBoolean INTENT_CLEAR = new AtomicBoolean(false);
    private static final AtomicBoolean INTENT_FLUSH = new AtomicBoolean(false);

    private static volatile int lastKnownLogCount = 0;
    private static volatile long lastHeartbeatTime = 0;

    public static void main(String[] args) {
        JsLogMonitorServer server = new JsLogMonitorServer();
        server.startHttpServer(DEFAULT_PORT);
    }

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

            server.createContext("/poll", this::handlePoll);
            server.createContext("/push", this::handlePush);

            server.setExecutor(null);
            server.start();
            log("JS Instrumentor monitoring service started: http://localhost:%d", port);
        } catch (Exception e) {
            log("Unable to configure or start HTTP service: %s", e.getMessage());
        }
    }

    private void handleClear(HttpExchange exchange) throws IOException {
        INTENT_CLEAR.set(true);
        sendTextResponse(exchange, 200, "[JsLogMonitor] Clear intent recorded. Waiting for JS client to poll.\n");
    }

    private void handleFlush(HttpExchange exchange) throws IOException {
        INTENT_FLUSH.set(true);
        sendTextResponse(exchange, 200, "[JsLogMonitor] Flush intent recorded. Waiting for JS client to push logs.\n");
    }

    private void handleStatus(HttpExchange exchange) throws IOException {
        StringBuilder sb = new StringBuilder();
        sb.append("[JsLogMonitor] Current Status (JS Browser)\n");

        boolean isOnline = (System.currentTimeMillis() - lastHeartbeatTime) < 10000;

        sb.append("  Client Status: ").append(isOnline ? "Online" : "Offline").append("\n");
        sb.append("  Total Threads (PIDs) : ").append(isOnline ? 1 : 0).append(" (Browser Main Thread)\n");
        sb.append("  Total Basic Log Entries: ").append(lastKnownLogCount).append("\n");
        sb.append("  Total Event Log Entries: 0 (Not supported in JS yet)\n");
        sb.append("  Pending Clear Intent: ").append(INTENT_CLEAR.get()).append("\n");
        sb.append("  Pending Flush Intent: ").append(INTENT_FLUSH.get()).append("\n");

        if (managerIp != null) {
            sb.append("  Manager Address: http://").append(managerIp).append(":").append(managerPort).append("\n");
        } else {
            sb.append("  Manager Address: Not set\n");
        }

        sendTextResponse(exchange, 200, sb.toString());
    }

    private void handleSetManager(HttpExchange exchange) throws IOException {
        Map<String, String> params = parseQuery(exchange.getRequestURI().getRawQuery());
        String ip = params.get("ip");
        String portStr = params.get("port");

        if (ip != null && portStr != null) {
            try {
                managerIp = ip;
                managerPort = Integer.parseInt(portStr);
                String msg = String.format("[JsLogMonitor] Manager set to %s:%d\n", managerIp, managerPort);
                log(msg.trim());
                sendTextResponse(exchange, 200, msg);
            } catch (NumberFormatException e) {
                sendTextResponse(exchange, 400, "[JsLogMonitor] Invalid port number.\n");
            }
        } else {
            sendTextResponse(exchange, 400, "[JsLogMonitor] Missing ip or port parameters.\n");
        }
    }

    private void handlePoll(HttpExchange exchange) throws IOException {
        addCorsHeaders(exchange);
        if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
            exchange.sendResponseHeaders(204, -1);
            return;
        }

        Map<String, String> params = parseQuery(exchange.getRequestURI().getRawQuery());
        if (params.containsKey("count")) {
            try {
                lastKnownLogCount = Integer.parseInt(params.get("count"));
                lastHeartbeatTime = System.currentTimeMillis();
            } catch (NumberFormatException ignored) {}
        }

        boolean clear = INTENT_CLEAR.getAndSet(false);
        boolean flush = INTENT_FLUSH.getAndSet(false);

        String response = String.format("{\"clear\": %b, \"flush\": %b}", clear, flush);
        sendTextResponse(exchange, 200, response);
    }

    private void handlePush(HttpExchange exchange) throws IOException {
        addCorsHeaders(exchange);
        if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
            exchange.sendResponseHeaders(204, -1);
            return;
        }

        if ("POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            try (InputStream is = exchange.getRequestBody();
                 BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8))) {

                String body = reader.lines().collect(Collectors.joining());
                List<Integer> logs = new ArrayList<>();

                if (!body.trim().isEmpty()) {
                    String[] parts = body.split(",");
                    for (String part : parts) {
                        try {
                            logs.add(Integer.parseInt(part.trim()));
                        } catch (NumberFormatException ignored) {}
                    }
                }

                LinkedHashMap<Long, List<Integer>> snapshot = new LinkedHashMap<>();
                snapshot.put(1L, logs);

                processAndFlushLogs(snapshot, "js_browser");

                lastKnownLogCount = 0;

                sendTextResponse(exchange, 200, "{\"status\": \"success\"}");
            } catch (Exception e) {
                log("Error processing push: %s", e.getMessage());
                sendTextResponse(exchange, 500, "{\"status\": \"error\"}");
            }
        } else {
            sendTextResponse(exchange, 405, "Method Not Allowed");
        }
    }

    private void processAndFlushLogs(LinkedHashMap<Long, List<Integer>> snapshot, String source) {
        try {
            String ts = LocalDateTime.now().format(TS_FMT);
            String logFileName = "instrumentor-log-" + ts + "-" + source + ".txt";

            if (!snapshot.isEmpty() && !snapshot.get(1L).isEmpty()) {
                String logContent = formatLogSnapshotStatic(snapshot);
                handleFileOutput(logFileName, logContent, source);
            } else {
                log("flushNow(%s): no logs to flush.", source);
            }
        } catch (Exception e) {
            log("flushNow(%s) failed: %s", source, e.getMessage());
            e.printStackTrace(System.err);
        }
    }

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

    private static void log(String fmt, Object... args) {
        System.err.printf("[JsLogMonitor] " + fmt + "%n", args);
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

    private void addCorsHeaders(HttpExchange exchange) {
        exchange.getResponseHeaders().add("Access-Control-Allow-Origin", "*");
        exchange.getResponseHeaders().add("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        exchange.getResponseHeaders().add("Access-Control-Allow-Headers", "Content-Type");
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