package com.example.instrumentor;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class EncodingStep implements InstrumentationStep {

    @Override
    public String name() { return "Encoding Mapping"; }

    @Override
    public int execute(List<Path> targets, PipelineContext context) throws Exception {
        CommentMapper mapper = new CommentMapper();

        if (context.isIncremental() && context.getMappingFile() != null
                && Files.exists(context.getMappingFile())) {
            mapper.buildIncrementalMapping(targets, context.getMappingFile());
        } else {
            mapper.buildFullMapping(targets);
        }

        if (mapper.size() == 0) return 0;

        for (Path target : targets) {
            mapper.replaceCommentsInSource(target);
        }

        Path outputFile = context.getMappingFile() != null
                ? context.getMappingFile()
                : Path.of("comment-mapping.txt").toAbsolutePath();
        mapper.writeMappingFile(outputFile);

        return mapper.size();
    }
}