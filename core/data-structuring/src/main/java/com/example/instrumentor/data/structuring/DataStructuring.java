package com.example.instrumentor.data.structuring;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.stmt.BlockStmt;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;

public class DataStructuring {

    static class MethodNode {
        String className;
        String methodName;
        int paramCount;
        String sourceCode;
        String filePath;
        List<MethodNode> calls = new ArrayList<>();

        public MethodNode(String className, String methodName, int paramCount, String sourceCode, String filePath) {
            this.className = className;
            this.methodName = methodName;
            this.paramCount = paramCount;
            this.sourceCode = sourceCode;
            this.filePath = filePath;
        }

        public String getFullSignature() {
            return className + "." + methodName + " (params: " + paramCount + ")";
        }
    }

    public static void main(String[] args) {
        // 修改：现在仅需 1 个参数
        if (args.length < 1) {
            System.err.println("Usage: java ThreadDependencyAnalyzer <pruned_directory_path>");
            System.err.println("Example: java ThreadDependencyAnalyzer ./pruned");
            System.exit(1);
        }

        String prunedDirPath = args[0];
        // 修改：直接硬编码输出到当前工作目录下的 final-output-calltree.md
        String outputFilePath = "final-output-calltree.md";

        try {
            Path prunedDir = Paths.get(prunedDirPath);
            if (!Files.exists(prunedDir) || !Files.isDirectory(prunedDir)) {
                System.err.println("[ERROR] The directory does not exist: " + prunedDirPath);
                return;
            }

            StringBuilder md = new StringBuilder();
            md.append("# Thread Traces\n\n");
            md.append("> **Data Schema & Legend:**\n");
            md.append("> This section represents the execution call tree for each thread.\n");
            md.append("> - **Call Tree**: Hierarchical execution flow. Each node contains the source file and pruned source code.\n\n");

            List<Path> threadDirs = Files.list(prunedDir)
                    .filter(Files::isDirectory)
                    .sorted()
                    .collect(Collectors.toList());

            int order = 0;
            for (Path threadDir : threadDirs) {
                String threadName = threadDir.getFileName().toString();
                System.out.println("Processing thread: " + threadName);

                md.append("## ").append(threadName).append(" (Order: ").append(order++).append(")\n");

                List<Path> javaFiles = Files.walk(threadDir)
                        .filter(p -> p.toString().endsWith(".java"))
                        .collect(Collectors.toList());

                Map<String, MethodNode> methodMap = new HashMap<>();

                Map<MethodNode, List<MethodCallInfo>> rawCallsMap = new HashMap<>();

                for (Path javaFile : javaFiles) {
                    try {
                        CompilationUnit cu = StaticJavaParser.parse(javaFile);
                        String relativePath = prunedDir.relativize(javaFile).toString().replace("\\", "/");

                        cu.findAll(ClassOrInterfaceDeclaration.class).forEach(classDecl -> {
                            String className = classDecl.getNameAsString();

                            classDecl.findAll(MethodDeclaration.class).forEach(methodDecl -> {

                                if (isEmptyMethod(methodDecl)) {
                                    return;
                                }

                                String methodName = methodDecl.getNameAsString();
                                int paramCount = methodDecl.getParameters().size();
                                String sourceCode = methodDecl.toString();

                                MethodNode node = new MethodNode(className, methodName, paramCount, sourceCode, relativePath);
                                String signature = className + "." + methodName + "_" + paramCount;
                                methodMap.put(signature, node);

                                List<MethodCallInfo> callsInMethod = new ArrayList<>();
                                methodDecl.findAll(MethodCallExpr.class).forEach(call -> {
                                    callsInMethod.add(new MethodCallInfo(
                                            call.getScope().map(Object::toString).orElse(null),
                                            call.getNameAsString(),
                                            call.getArguments().size()
                                    ));
                                });
                                rawCallsMap.put(node, callsInMethod);
                            });
                        });
                    } catch (Exception e) {
                        System.err.println("Warning: Failed to parse file " + javaFile + " : " + e.getMessage());
                    }
                }

                Set<MethodNode> calledNodes = new HashSet<>();

                for (Map.Entry<MethodNode, List<MethodCallInfo>> entry : rawCallsMap.entrySet()) {
                    MethodNode caller = entry.getKey();
                    List<MethodCallInfo> calls = entry.getValue();

                    for (MethodCallInfo call : calls) {

                        MethodNode callee = findMatchingMethod(call, methodMap, caller.className);
                        if (callee != null && callee != caller) {
                            caller.calls.add(callee);
                            calledNodes.add(callee);
                        }
                    }
                }

                List<MethodNode> entryPoints = methodMap.values().stream()
                        .filter(node -> !calledNodes.contains(node))
                        .collect(Collectors.toList());

                if (entryPoints.isEmpty() && !methodMap.isEmpty()) {

                    entryPoints.addAll(methodMap.values());
                }

                for (MethodNode rootNode : entryPoints) {
                    renderCallNode(rootNode, md, 0);
                }

                md.append("\n---\n\n");
            }

            Files.writeString(Paths.get(outputFilePath), md.toString(), StandardCharsets.UTF_8);
            System.out.println("[SUCCESS] Markdown generated at: " + outputFilePath);

        } catch (IOException e) {
            System.err.println("[ERROR] File I/O Error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private static boolean isEmptyMethod(MethodDeclaration methodDecl) {

        if (methodDecl.getBody().isEmpty()) {
            return true;
        }

        BlockStmt body = methodDecl.getBody().get();

        return body.getStatements().isEmpty();
    }

    private static class MethodCallInfo {
        String scope;
        String name;
        int argCount;

        public MethodCallInfo(String scope, String name, int argCount) {
            this.scope = scope;
            this.name = name;
            this.argCount = argCount;
        }
    }

    private static MethodNode findMatchingMethod(MethodCallInfo call, Map<String, MethodNode> methodMap, String callerClassName) {

        if (call.scope == null || "this".equals(call.scope) || "super".equals(call.scope)) {
            String key = callerClassName + "." + call.name + "_" + call.argCount;
            if (methodMap.containsKey(key)) {
                return methodMap.get(key);
            }
        }

        if (call.scope != null) {
            String key = call.scope + "." + call.name + "_" + call.argCount;
            if (methodMap.containsKey(key)) {
                return methodMap.get(key);
            }
        }

        for (MethodNode node : methodMap.values()) {
            if (node.methodName.equals(call.name) && node.paramCount == call.argCount) {
                return node;
            }
        }

        return null;
    }

    private static void renderCallNode(MethodNode node, StringBuilder md, int level) {
        String indent = "    ".repeat(level);
        String contentIndent = indent + "    ";

        if (node.filePath != null) {
            md.append(indent).append("- *File:* `").append(node.filePath).append("`\n");
        } else {
            md.append(indent).append("- *(no file)*\n");
        }

        if (node.sourceCode != null) {
            String source = node.sourceCode.trim();

            source = source.replaceAll("//\\s*\\[Executed Block ID:.*?\\]", "").trim();

            md.append(contentIndent).append("```java\n");
            for (String line : source.split("\n")) {
                md.append(contentIndent).append(line).append("\n");
            }
            md.append(contentIndent).append("```\n");
        }

        if (!node.calls.isEmpty()) {
            md.append(contentIndent).append("*Calls:*\n");
            for (MethodNode child : node.calls) {
                renderCallNode(child, md, level + 1);
            }
        }
    }
}