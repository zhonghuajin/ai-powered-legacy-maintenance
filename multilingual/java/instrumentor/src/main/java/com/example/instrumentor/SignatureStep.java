package com.example.instrumentor;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Generates {@code block-signature.txt}, mirroring the PHP/JS {@code generateBlockSignatures}.
 * For each instrumented block (identified by its {@code path:line} comment in the mapping file),
 * it finds the innermost enclosing method range and emits {@code id = signature}, falling back to
 * {@code [Global]} when no range encloses the line.
 */
public class SignatureStep implements InstrumentationStep {

    private static final Pattern MAPPING_PATTERN = Pattern.compile("^(\\d+)\\s*=\\s*(.+)$");
    private static final Pattern RANGE_PATTERN = Pattern.compile("^(.+?)\\s*\\|\\s*(.+?)\\s*=\\s*(\\d+)-(\\d+)$");

    @Override
    public String name() { return "Generating Block to Signature Mapping"; }

    @Override
    public int execute(List<Path> targets, PipelineContext context) throws Exception {
        Path mappingToLoad = context.getMappingFile();
        Path rangesToLoad = context.getRangeFile();
        Path outputFile = context.getSignatureFile();
        if (context.isIncremental()) {
            mappingToLoad = PipelineContext.incrementalPath(mappingToLoad);
            rangesToLoad = PipelineContext.incrementalPath(rangesToLoad);
            outputFile = PipelineContext.incrementalPath(outputFile);
        }

        Map<Integer, String> commentMap = loadRawMapping(mappingToLoad);
        List<MethodRange> ranges = loadRawRanges(rangesToLoad);

        Map<String, List<MethodRange>> rangesByFile = new LinkedHashMap<>();
        for (MethodRange r : ranges) {
            rangesByFile.computeIfAbsent(r.file, k -> new ArrayList<>()).add(r);
        }

        Map<Integer, String> blockToSignature = new TreeMap<>();
        for (Map.Entry<Integer, String> entry : commentMap.entrySet()) {
            String comment = entry.getValue();
            String filePath = extractFilePathFromComment(comment);
            if (filePath == null) continue;
            Integer line = extractLineFromComment(comment);
            if (line == null) continue;

            String matchedSignature = "[Global]";
            List<MethodRange> fileRanges = rangesByFile.get(filePath);
            if (fileRanges != null) {
                MethodRange best = null;
                for (MethodRange r : fileRanges) {
                    if (line >= r.start && line <= r.end) {
                        if (best == null
                                || r.start > best.start
                                || (r.start == best.start && r.end < best.end)) {
                            best = r;
                        }
                    }
                }
                if (best != null) {
                    matchedSignature = best.name;
                }
            }
            blockToSignature.put(entry.getKey(), matchedSignature);
        }

        writeSignatureFile(outputFile, blockToSignature);
        return blockToSignature.size();
    }

    private Map<Integer, String> loadRawMapping(Path mappingFile) throws Exception {
        Map<Integer, String> result = new LinkedHashMap<>();
        if (!Files.exists(mappingFile)) return result;
        for (String line : Files.readAllLines(mappingFile, StandardCharsets.UTF_8)) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.charAt(0) == '#') continue;
            Matcher m = MAPPING_PATTERN.matcher(trimmed);
            if (m.matches()) {
                result.put(Integer.parseInt(m.group(1)), m.group(2).trim());
            }
        }
        return result;
    }

    private List<MethodRange> loadRawRanges(Path rangeFile) throws Exception {
        List<MethodRange> result = new ArrayList<>();
        if (!Files.exists(rangeFile)) return result;
        for (String line : Files.readAllLines(rangeFile, StandardCharsets.UTF_8)) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.charAt(0) == '#') continue;
            Matcher m = RANGE_PATTERN.matcher(trimmed);
            if (m.matches()) {
                result.add(new MethodRange(
                        m.group(1).trim(),
                        m.group(2).trim(),
                        Integer.parseInt(m.group(3)),
                        Integer.parseInt(m.group(4))));
            }
        }
        return result;
    }

    private String extractFilePathFromComment(String comment) {
        int lastColon = comment.lastIndexOf(':');
        if (lastColon <= 0) return null;
        String afterColon = comment.substring(lastColon + 1);
        if (afterColon.isEmpty() || !afterColon.chars().allMatch(Character::isDigit)) {
            return null;
        }
        return comment.substring(0, lastColon);
    }

    private Integer extractLineFromComment(String comment) {
        int lastColon = comment.lastIndexOf(':');
        if (lastColon <= 0) return null;
        String afterColon = comment.substring(lastColon + 1);
        try {
            return Integer.parseInt(afterColon.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private void writeSignatureFile(Path filePath, Map<Integer, String> signatures) throws Exception {
        List<String> lines = new ArrayList<>();
        lines.add("# ================================================");
        lines.add("# Block ID -> Method Signature Mapping Table");
        lines.add("# Generation Time: " + LocalDateTime.now()
                .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        lines.add("# Total Entries: " + signatures.size());
        lines.add("# ================================================");
        lines.add("# Format: Block ID = Method Signature");
        lines.add("# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.");
        lines.add("");

        for (Map.Entry<Integer, String> entry : signatures.entrySet()) {
            lines.add(entry.getKey() + " = " + entry.getValue());
        }

        if (filePath.getParent() != null) {
            Files.createDirectories(filePath.getParent());
        }
        Files.write(filePath, lines, StandardCharsets.UTF_8);
    }
}
