package com.example.instrumentor;

import java.nio.file.Path;

public class PipelineContext {
    private final boolean incremental;
    private final Path mappingFile;

    public PipelineContext(boolean incremental, Path mappingFile) {
        this.incremental = incremental;
        this.mappingFile = mappingFile;
    }

    public boolean isIncremental() { return incremental; }
    public Path getMappingFile() { return mappingFile; }
}