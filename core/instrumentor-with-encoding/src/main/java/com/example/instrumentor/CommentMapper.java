package com.example.instrumentor;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.regex.*;
import java.util.stream.Stream;

public class CommentMapper {
    private static final Pattern ORIGINAL_COMMENT_PATTERN = Pattern.compile("^(\\s*)//\\s*(.+\\.java:\\d+)\\s*$");
    private static final Pattern MAPPED_COMMENT_PATTERN = Pattern.compile("^(\\s*)//\\s*INST#(\\d+)\\s*$");

    private final Map<Integer, String> idToComment = new LinkedHashMap<>();
    private final Map<String, Integer> commentToId = new LinkedHashMap<>();

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("Usage: CommentMapper [-o mappingOutput] [-m existingMapping] <target1> [target2 ...]");
            System.exit(1);
        }

        List<Path> targets = new ArrayList<>();
        Path mappingOutput = null;
        Path existingMapping = null;

        for (int i = 0; i < args.length; i++) {
            if ("-o".equals(args[i])) {
                if (i + 1 < args.length) {
                    mappingOutput = Paths.get(args[++i]).toAbsolutePath().normalize();
                } else {
                    System.err.println("Missing value for -o");
                    System.exit(1);
                }
            } else if ("-m".equals(args[i])) {
                if (i + 1 < args.length) {
                    existingMapping = Paths.get(args[++i]).toAbsolutePath().normalize();
                } else {
                    System.err.println("Missing value for -m");
                    System.exit(1);
                }
            } else {
                targets.add(Paths.get(args[i]).toAbsolutePath().normalize());
            }
        }

        if (targets.isEmpty()) {
            System.err.println("No target files or directories specified.");
            System.exit(1);
        }

        if (mappingOutput == null) {
            mappingOutput = Paths.get(System.getProperty("user.dir")).resolve("comment-mapping.txt");
        }

        CommentMapper mapper = new CommentMapper();

        if (existingMapping != null && Files.exists(existingMapping)) {
            // Incremental mode: load existing mapping, update only targets
            mapper.buildIncrementalMapping(targets, existingMapping);
        } else {
            // Full mode: build mapping from scratch
            mapper.buildFullMapping(targets);
        }

        if (mapper.size() == 0) return;

        for (Path target : targets) {
            mapper.replaceCommentsInSource(target);
        }
        mapper.writeMappingFile(mappingOutput);
    }

    // ==============================
    // Full Mapping (unchanged logic)
    // ==============================

    public void buildFullMapping(List<Path> targets) throws IOException {
        idToComment.clear();
        commentToId.clear();

        List<Path> files = new ArrayList<>();
        for (Path target : targets) {
            files.addAll(collectJavaFiles(target));
        }
        List<String> allComments = scanOriginalComments(files);
        sortCommentsByPathAndLine(allComments);

        int id = 1;
        for (String comment : allComments) {
            idToComment.put(id, comment);
            commentToId.put(comment, id);
            id++;
        }
    }

    public void buildFullMapping(Path target) throws IOException {
        buildFullMapping(List.of(target));
    }

    // ==============================
    // Incremental Mapping (new)
    // ==============================

    /**
     * Builds an incremental mapping by:
     * 1. Loading the existing mapping file.
     * 2. Removing entries that belong to the target files (which are being re-instrumented).
     * 3. Scanning new comments from the target files.
     * 4. Assigning new IDs to the new comments starting after the max preserved ID.
     *
     * This preserves IDs for non-target files so their source (which still contains
     * // INST#id or staining(id) calls) remains consistent with the mapping.
     */
    public void buildIncrementalMapping(List<Path> targets, Path existingMappingFile) throws IOException {
        idToComment.clear();
        commentToId.clear();

        // Step 1: Load existing mapping
        Map<Integer, String> existingMap = loadRawMapping(existingMappingFile);

        // Step 2: Collect target file paths
        List<Path> targetFiles = new ArrayList<>();
        for (Path target : targets) {
            targetFiles.addAll(collectJavaFiles(target));
        }

        Set<String> targetFilePaths = new HashSet<>();
        for (Path file : targetFiles) {
            targetFilePaths.add(file.toAbsolutePath().normalize().toString());
        }

        // Step 3: Keep entries for non-target files, discard entries for target files
        for (Map.Entry<Integer, String> entry : existingMap.entrySet()) {
            String comment = entry.getValue();
            String filePath = extractFilePathFromComment(comment);
            if (filePath != null && targetFilePaths.contains(filePath)) {
                // Entry belongs to a target file being re-instrumented - discard
                continue;
            }
            // Preserve this entry with its original ID
            idToComment.put(entry.getKey(), comment);
            commentToId.put(comment, entry.getKey());
        }

        // Step 4: Scan new comments from target files
        List<String> newComments = scanOriginalComments(targetFiles);
        sortCommentsByPathAndLine(newComments);

        // Step 5: Determine next available ID (max preserved ID + 1)
        int nextId = idToComment.isEmpty() ? 1 : Collections.max(idToComment.keySet()) + 1;

        // Step 6: Assign new IDs to new comments
        for (String comment : newComments) {
            if (!commentToId.containsKey(comment)) {
                idToComment.put(nextId, comment);
                commentToId.put(comment, nextId);
                nextId++;
            }
        }
    }

    public void buildIncrementalMapping(Path target, Path existingMappingFile) throws IOException {
        buildIncrementalMapping(List.of(target), existingMappingFile);
    }

    /**
     * Extracts the file path portion from a comment string like "/path/to/File.java:123".
     * Returns null if the format doesn't match.
     */
    private String extractFilePathFromComment(String comment) {
        int lastColon = comment.lastIndexOf(':');
        if (lastColon <= 0) return null;
        String afterColon = comment.substring(lastColon + 1);
        try {
            Integer.parseInt(afterColon);
        } catch (NumberFormatException e) {
            return null;
        }
        return comment.substring(0, lastColon);
    }

    // ==============================
    // Replace comments in source
    // ==============================

    public void replaceCommentsInSource(Path target) throws IOException {
        replaceCommentsInSource(collectJavaFiles(target));
    }

    public void replaceCommentsInSource(List<Path> files) throws IOException {
        if (commentToId.isEmpty()) return;

        for (Path file : files) {
            if (!Files.exists(file)) continue;

            List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
            boolean modified = false;

            for (int i = 0; i < lines.size(); i++) {
                String line = lines.get(i);
                Matcher m = ORIGINAL_COMMENT_PATTERN.matcher(line);
                if (m.matches()) {
                    String indent = m.group(1);
                    String content = m.group(2);
                    Integer id = commentToId.get(content);
                    if (id != null) {
                        lines.set(i, indent + "// INST#" + id);
                        modified = true;
                    }
                }
            }

            if (modified) {
                Files.write(file, lines, StandardCharsets.UTF_8);
            }
        }
    }

    // ==============================
    // Write / Load mapping file
    // ==============================

    public void writeMappingFile(Path outputFile) throws IOException {
        List<Map.Entry<Integer, String>> sorted = new ArrayList<>(idToComment.entrySet());
        sorted.sort(Comparator.comparingInt(Map.Entry::getKey));

        List<String> output = new ArrayList<>();
        output.add("# ================================================");
        output.add("# Instrumentation Comment -> Integer ID Mapping Table");
        output.add("# Generation Time: " + LocalDateTime.now()
                .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        output.add("# Total Entries: " + sorted.size());
        output.add("# ================================================");
        output.add("# Format: Integer ID = File Absolute Path:Code Block Start Line Number");
        output.add("# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.");
        output.add("");

        for (Map.Entry<Integer, String> entry : sorted) {
            output.add(entry.getKey() + " = " + entry.getValue());
        }

        Files.createDirectories(outputFile.getParent());
        Files.write(outputFile, output, StandardCharsets.UTF_8);
    }

    public void loadMappingFile(Path mappingFile) throws IOException {
        idToComment.clear();
        commentToId.clear();
        Map<Integer, String> raw = loadRawMapping(mappingFile);
        for (Map.Entry<Integer, String> entry : raw.entrySet()) {
            idToComment.put(entry.getKey(), entry.getValue());
            commentToId.put(entry.getValue(), entry.getKey());
        }
    }

    // ==============================
    // Clean instrumentation
    // ==============================

    public static int cleanInstrumentation(Path target) throws IOException {
        List<Path> files = collectJavaFiles(target);
        int totalRemoved = 0;

        for (Path file : files) {
            List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
            List<String> cleaned = new ArrayList<>(lines.size());
            int removedInFile = 0;

            for (String line : lines) {
                boolean isOriginal = ORIGINAL_COMMENT_PATTERN.matcher(line).matches();
                boolean isMapped = MAPPED_COMMENT_PATTERN.matcher(line).matches();

                if (isOriginal || isMapped) {
                    removedInFile++;
                } else {
                    cleaned.add(line);
                }
            }

            if (removedInFile > 0) {
                Files.write(file, cleaned, StandardCharsets.UTF_8);
                totalRemoved += removedInFile;
            }
        }
        return totalRemoved;
    }

    // ==============================
    // Accessors
    // ==============================

    public int size() { return idToComment.size(); }
    public String getCommentById(int id) { return idToComment.get(id); }
    public Integer getIdByComment(String comment) { return commentToId.get(comment); }
    public Map<Integer, String> getIdToCommentMap() { return Collections.unmodifiableMap(idToComment); }
    public Map<String, Integer> getCommentToIdMap() { return Collections.unmodifiableMap(commentToId); }

    // ==============================
    // Internal helpers
    // ==============================

    private List<String> scanOriginalComments(List<Path> files) throws IOException {
        Set<String> seen = new LinkedHashSet<>();
        for (Path file : files) {
            if (!Files.exists(file)) continue;
            List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
            for (String line : lines) {
                Matcher m = ORIGINAL_COMMENT_PATTERN.matcher(line);
                if (m.matches()) {
                    seen.add(m.group(2));
                }
            }
        }
        return new ArrayList<>(seen);
    }

    private void sortCommentsByPathAndLine(List<String> comments) {
        comments.sort((a, b) -> {
            int colonA = a.lastIndexOf(':');
            int colonB = b.lastIndexOf(':');
            String pathA = a.substring(0, colonA);
            String pathB = b.substring(0, colonB);
            int cmp = pathA.compareTo(pathB);
            if (cmp != 0) return cmp;
            int lineA = Integer.parseInt(a.substring(colonA + 1));
            int lineB = Integer.parseInt(b.substring(colonB + 1));
            return Integer.compare(lineA, lineB);
        });
    }

    private Map<Integer, String> loadRawMapping(Path mappingFile) throws IOException {
        Map<Integer, String> result = new LinkedHashMap<>();
        List<String> lines = Files.readAllLines(mappingFile, StandardCharsets.UTF_8);
        Pattern entryPattern = Pattern.compile("^(\\d+)\\s*=\\s*(.+)$");

        for (String line : lines) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("#")) continue;
            Matcher m = entryPattern.matcher(trimmed);
            if (m.matches()) {
                int id = Integer.parseInt(m.group(1));
                String comment = m.group(2).trim();
                result.put(id, comment);
            }
        }
        return result;
    }

    private static List<Path> collectJavaFiles(Path target) throws IOException {
        List<Path> result = new ArrayList<>();
        if (Files.isDirectory(target)) {
            try (Stream<Path> walk = Files.walk(target)) {
                walk.filter(p -> p.toString().endsWith(".java"))
                    .sorted()
                    .forEach(result::add);
            }
        } else if (target.toString().endsWith(".java")) {
            result.add(target);
        }
        return result;
    }
}