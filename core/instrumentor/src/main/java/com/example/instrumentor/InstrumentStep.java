package com.example.instrumentor;

import java.nio.file.Path;
import java.util.List;

public class InstrumentStep implements InstrumentationStep {

    @Override
    public String name() { return "Code Instrumentation"; }

    @Override
    public int execute(List<Path> targets, PipelineContext context) throws Exception {
        // 复用 UnifiedInstrumentor 的逻辑
        com.github.javaparser.ParserConfiguration config = new com.github.javaparser.ParserConfiguration();
        config.setLanguageLevel(com.github.javaparser.ParserConfiguration.LanguageLevel.JAVA_17);
        config.setAttributeComments(true);
        com.github.javaparser.StaticJavaParser.setConfiguration(config);

        int count = 0;
        for (Path target : targets) {
            if (java.nio.file.Files.isDirectory(target)) {
                count += processDirectory(target);
            } else if (target.toString().endsWith(".java")) {
                instrumentFile(target);
                count++;
            }
        }
        return count;
    }

    private int processDirectory(Path dir) throws Exception {
        int[] count = {0};
        java.nio.file.Files.walkFileTree(dir, new java.nio.file.SimpleFileVisitor<Path>() {
            @Override
            public java.nio.file.FileVisitResult visitFile(Path file, java.nio.file.attribute.BasicFileAttributes attrs) {
                if (file.toString().endsWith(".java")) {
                    try {
                        instrumentFile(file);
                        count[0]++;
                    } catch (Exception e) {
                        System.err.println("Error processing: " + file + " - " + e.getMessage());
                    }
                }
                return java.nio.file.FileVisitResult.CONTINUE;
            }
        });
        return count[0];
    }

    private void instrumentFile(Path file) throws Exception {
        String absolutePath = file.toAbsolutePath().normalize().toString();
        com.github.javaparser.ast.CompilationUnit cu = com.github.javaparser.StaticJavaParser.parse(file);
        CodeBlockInstrumentor.normalizeBraces(cu);
        CodeBlockInstrumentor.instrumentCU(cu, absolutePath);
        java.nio.file.Files.writeString(file, cu.toString());
    }
}