package com.example.instrumentor;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class InstrumentationPipeline {

    private final List<InstrumentationStep> steps = List.of(
            new InstrumentStep(),
            new MethodRangeStep(),
            new EncodingStep(),
            new SignatureStep(),
            new ActivationStep()
    );

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("Usage: InstrumentationPipeline [--incremental] [--mapping mappingFile] "
                    + "[--range rangeFile] [--signature signatureFile] <target1> [target2 ...]");
            System.exit(1);
        }

        boolean incremental = false;
        Path mappingFile = null;
        Path rangeFile = null;
        Path signatureFile = null;
        List<Path> targets = new ArrayList<>();

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--incremental" -> incremental = true;
                case "-m", "--mapping" -> {
                    if (i + 1 < args.length) {
                        mappingFile = Paths.get(args[++i]).toAbsolutePath().normalize();
                    } else {
                        System.err.println("Missing value for " + args[i]);
                        System.exit(1);
                    }
                }
                case "--range" -> {
                    if (i + 1 < args.length) {
                        rangeFile = Paths.get(args[++i]).toAbsolutePath().normalize();
                    } else {
                        System.err.println("Missing value for --range");
                        System.exit(1);
                    }
                }
                case "--signature" -> {
                    if (i + 1 < args.length) {
                        signatureFile = Paths.get(args[++i]).toAbsolutePath().normalize();
                    } else {
                        System.err.println("Missing value for --signature");
                        System.exit(1);
                    }
                }
                default -> targets.add(Paths.get(args[i]).toAbsolutePath().normalize());
            }
        }

        if (targets.isEmpty()) {
            System.err.println("No target files or directories specified.");
            System.exit(1);
        }

        if (mappingFile == null) {
            mappingFile = Paths.get("block-line-mapping.txt").toAbsolutePath().normalize();
        }
        if (rangeFile == null) {
            rangeFile = Paths.get("method-range.txt").toAbsolutePath().normalize();
        }
        if (signatureFile == null) {
            signatureFile = Paths.get("block-signature.txt").toAbsolutePath().normalize();
        }

        if (incremental && !Files.exists(mappingFile)) {
            System.out.println("Warning: mapping file not found, falling back to full mode.");
            incremental = false;
        }

        PipelineContext context = new PipelineContext(incremental, mappingFile, rangeFile, signatureFile);
        InstrumentationPipeline pipeline = new InstrumentationPipeline();
        pipeline.run(targets, context);
    }

    public void run(List<Path> targets, PipelineContext context) throws Exception {
        String mode = context.isIncremental() ? "Incremental" : "Full";
        System.out.println("=== Instrumentation Pipeline (" + mode + " mode) ===");

        for (InstrumentationStep step : steps) {
            System.out.println("\n>> Step: " + step.name());
            long start = System.currentTimeMillis();
            int result = step.execute(targets, context);
            long elapsed = System.currentTimeMillis() - start;
            System.out.printf("   Done. Processed %d items in %d ms.%n", result, elapsed);
        }

        System.out.println("\n=== Pipeline complete ===");
    }
}