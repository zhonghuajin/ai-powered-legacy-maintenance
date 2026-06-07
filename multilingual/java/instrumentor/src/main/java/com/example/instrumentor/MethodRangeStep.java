package com.example.instrumentor;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Writes {@code method-range.txt}, mirroring the PHP/JS {@code updateMethodRanges}/{@code writeRangeFile}.
 * Ranges are sorted by file then start line, and the output uses the shared
 * {@code file | name = start-end} format.
 */
public class MethodRangeStep implements InstrumentationStep {

    @Override
    public String name() { return "Updating Method Ranges"; }

    @Override
    public int execute(List<Path> targets, PipelineContext context) throws Exception {
        List<MethodRange> ranges = new ArrayList<>(context.getCollectedRanges());
        ranges.sort(Comparator.comparing((MethodRange r) -> r.file).thenComparingInt(r -> r.start));

        Path outputFile = context.getRangeFile();
        if (context.isIncremental()) {
            outputFile = PipelineContext.incrementalPath(outputFile);
        }
        writeRangeFile(outputFile, ranges);
        return ranges.size();
    }

    private void writeRangeFile(Path filePath, List<MethodRange> ranges) throws Exception {
        List<String> lines = new ArrayList<>();
        lines.add("# ================================================");
        lines.add("# Method Line Range Mapping Table");
        lines.add("# Generation Time: " + LocalDateTime.now()
                .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
        lines.add("# Total Entries: " + ranges.size());
        lines.add("# ================================================");
        lines.add("# Format: File Absolute Path | Method Name = Start Line-End Line");
        lines.add("# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.");
        lines.add("");

        for (MethodRange r : ranges) {
            lines.add(r.file + " | " + r.name + " = " + r.start + "-" + r.end);
        }

        if (filePath.getParent() != null) {
            Files.createDirectories(filePath.getParent());
        }
        Files.write(filePath, lines, StandardCharsets.UTF_8);
    }
}
