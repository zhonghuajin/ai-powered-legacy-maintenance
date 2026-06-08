package com.example.instrumentor;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class PipelineContext {
    private final boolean incremental;
    private final Path mappingFile;
    private final Path rangeFile;
    private final Path signatureFile;

    // Method ranges collected during the instrumentation step, consumed by MethodRangeStep/SignatureStep.
    private final List<MethodRange> collectedRanges = new ArrayList<>();

    public PipelineContext(boolean incremental, Path mappingFile, Path rangeFile, Path signatureFile) {
        this.incremental = incremental;
        this.mappingFile = mappingFile;
        this.rangeFile = rangeFile;
        this.signatureFile = signatureFile;
    }

    public boolean isIncremental() { return incremental; }
    public Path getMappingFile() { return mappingFile; }
    public Path getRangeFile() { return rangeFile; }
    public Path getSignatureFile() { return signatureFile; }

    public List<MethodRange> getCollectedRanges() { return collectedRanges; }
    public void addRanges(List<MethodRange> ranges) { collectedRanges.addAll(ranges); }

    /**
     * Mirrors the PHP/JS {@code getIncrementalPath}: {@code foo.txt -> foo.incremental.txt}.
     */
    public static Path incrementalPath(Path filePath) {
        Path dir = filePath.getParent();
        String fileName = filePath.getFileName().toString();
        int dot = fileName.lastIndexOf('.');
        String base = dot >= 0 ? fileName.substring(0, dot) : fileName;
        String ext = dot >= 0 ? fileName.substring(dot + 1) : "";
        String incremental = base + ".incremental" + (ext.isEmpty() ? "" : "." + ext);
        return dir == null ? Paths.get(incremental) : dir.resolve(incremental);
    }
}
