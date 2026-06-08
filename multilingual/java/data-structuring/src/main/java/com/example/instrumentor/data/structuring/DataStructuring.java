package com.example.instrumentor.data.structuring;

import com.github.javaparser.Position;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.RecordDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.comments.Comment;
import com.github.javaparser.ast.expr.AssignExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.LambdaExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.expr.SuperExpr;
import com.github.javaparser.ast.expr.ThisExpr;
import com.github.javaparser.ast.stmt.BlockStmt;
import com.github.javaparser.ast.stmt.Statement;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Structures pruned source code into a per-file "Call Tree" Markdown document.
 *
 * <p>This implementation is aligned with the PHP ({@code DataStructuring.php}) and
 * JavaScript ({@code DataStructuring.js}) versions: it shares the same data model,
 * signature scheme ({@code name@line} / {@code Class::method@line}), original-line
 * recovery via the injected {@code // line: N} comments, closure/lambda naming
 * heuristics, adjacency-list call tree rendering (with a {@code visited} set and
 * {@code *(See above)*} de-duplication) and the same Markdown header/legend.</p>
 */
public class DataStructuring {

    private static final Pattern LINE_COMMENT_PATTERN = Pattern.compile("line:\\s*(\\d+)");
    private static final Set<String> SPECIAL_SCOPES =
            Set.of("this", "super", "self", "static", "parent");

    static class MethodNode {
        final String signature;
        final String className;
        final String methodName;
        final int paramCount;
        final String sourceCode;
        final String filePath;
        final int startLine;
        List<MethodCallInfo> calls = new ArrayList<>();

        MethodNode(String signature, String className, String methodName, int paramCount,
                   String sourceCode, String filePath, int startLine) {
            this.signature = signature;
            this.className = className;
            this.methodName = methodName;
            this.paramCount = paramCount;
            this.sourceCode = sourceCode;
            this.filePath = filePath;
            this.startLine = startLine;
        }
    }

    static class MethodCallInfo {
        final String scope;
        final String name;
        final int argCount;

        MethodCallInfo(String scope, String name, int argCount) {
            this.scope = scope;
            this.name = name;
            this.argCount = argCount;
        }
    }

    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("Usage: java DataStructuring <pruned_directory_path>");
            System.err.println("Example: java DataStructuring ./pruned");
            System.exit(1);
        }

        String prunedDirPath = args[0];
        String outputFilePath = "final-output-calltree.md";

        try {
            Path prunedDir = Paths.get(prunedDirPath);
            if (!Files.exists(prunedDir) || !Files.isDirectory(prunedDir)) {
                System.err.println("[ERROR] The directory does not exist: " + prunedDirPath);
                return;
            }

            StringBuilder md = new StringBuilder();
            md.append("# File-Internal Method Index (Call Tree View)\n\n");
            md.append("> **Description & Legend:**\n");
            md.append("> This document lists every function/method extracted via AST analysis, organized as a Call Tree.\n");
            md.append("> - Indentation represents the file-internal calling hierarchy.\n");
            md.append("> - Each method is emitted with a signature identical to the instrumentation pipeline (`name@line`, or `Class::method@line`).\n");
            md.append("> - The line numbers and signatures are mapped back to the **original source code** using the injected comments.\n");
            md.append("> - `*Calls:*` lists direct call expressions for reference only; it does not affect signature matching.\n\n");

            List<Path> threadDirs;
            try (var stream = Files.list(prunedDir)) {
                threadDirs = stream.filter(Files::isDirectory).sorted().collect(Collectors.toList());
            }

            int order = 0;
            for (Path threadDir : threadDirs) {
                String threadName = threadDir.getFileName().toString();
                System.out.println("Processing thread: " + threadName);

                md.append("# Thread: ").append(threadName).append(" (Order: ").append(order++).append(")\n\n");

                List<Path> javaFiles;
                try (var stream = Files.walk(threadDir)) {
                    javaFiles = stream.filter(p -> p.toString().endsWith(".java"))
                            .filter(Files::isRegularFile)
                            .sorted()
                            .collect(Collectors.toList());
                }

                for (Path javaFile : javaFiles) {
                    try {
                        String code = Files.readString(javaFile, StandardCharsets.UTF_8);
                        String relativePath = threadDir.relativize(javaFile).toString().replace("\\", "/");

                        Map<String, MethodNode> methods = analyzeFile(code, relativePath);
                        if (methods.isEmpty()) {
                            continue;
                        }

                        md.append("## File: `").append(relativePath).append("`\n\n");
                        md.append(renderCallTree(methods));
                    } catch (Exception e) {
                        System.err.println("Warning: Failed to parse file " + javaFile + " : " + e.getMessage());
                    }
                }
            }

            Files.writeString(Paths.get(outputFilePath), md.toString(), StandardCharsets.UTF_8);
            System.out.println("[SUCCESS] Markdown generated at: " + outputFilePath);

        } catch (IOException e) {
            System.err.println("[ERROR] File I/O Error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    // ==============================
    // AST analysis
    // ==============================

    private static Map<String, MethodNode> analyzeFile(String code, String filePath) {
        CompilationUnit cu = StaticJavaParser.parse(code);
        String[] lines = code.split("\n", -1);
        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");

        Map<String, MethodNode> methods = new LinkedHashMap<>();
        Deque<Node> nodeStack = new ArrayDeque<>();
        Deque<String> classStack = new ArrayDeque<>();

        collectMethods(cu, lines, filePath, packageName, methods, nodeStack, classStack);
        return methods;
    }

    private static void collectMethods(Node node, String[] lines, String filePath, String packageName,
                                       Map<String, MethodNode> methods,
                                       Deque<Node> nodeStack, Deque<String> classStack) {

        boolean pushedClass = false;
        String typeName = typeNameOf(node);
        if (typeName != null) {
            classStack.push(typeName);
            pushedClass = true;
        }

        if (node instanceof MethodDeclaration || node instanceof LambdaExpr) {
            // computeClosureName must observe the stack *before* this node is pushed.
            String closureName = (node instanceof LambdaExpr) ? computeClosureName(nodeStack) : null;

            if (!isEmptyMethod(node)) {
                addMethod(node, closureName, lines, filePath, packageName, classStack, methods);
            }
        }

        nodeStack.push(node);
        for (Node child : node.getChildNodes()) {
            collectMethods(child, lines, filePath, packageName, methods, nodeStack, classStack);
        }
        nodeStack.pop();

        if (pushedClass) {
            classStack.pop();
        }
    }

    private static void addMethod(Node node, String closureName, String[] lines, String filePath,
                                  String packageName, Deque<String> classStack,
                                  Map<String, MethodNode> methods) {
        String methodName;
        int paramCount;
        if (node instanceof MethodDeclaration md) {
            methodName = md.getNameAsString();
            paramCount = md.getParameters().size();
        } else {
            LambdaExpr lambda = (LambdaExpr) node;
            methodName = closureName != null ? closureName : "lambda";
            paramCount = lambda.getParameters().size();
        }

        int startLine = getOriginalLine(node);
        String sourceCode = extractSource(lines, node);
        String currentClass = currentClassName(packageName, classStack);

        String signature;
        String className;
        if (!currentClass.isEmpty()) {
            signature = currentClass + "::" + methodName + "@" + startLine;
            className = currentClass;
        } else {
            signature = methodName + "@" + startLine;
            className = "";
        }

        MethodNode methodNode = new MethodNode(signature, className, methodName, paramCount,
                sourceCode, filePath, startLine);
        methodNode.calls = collectCalls(node);
        methods.put(signature, methodNode);
    }

    private static String currentClassName(String packageName, Deque<String> classStack) {
        if (classStack.isEmpty()) {
            return "";
        }
        // classStack is a stack (most recent first); render outermost-first.
        List<String> names = new ArrayList<>(classStack);
        java.util.Collections.reverse(names);
        String joined = String.join(".", names);
        return packageName.isEmpty() ? joined : packageName + "." + joined;
    }

    private static String typeNameOf(Node node) {
        if (node instanceof ClassOrInterfaceDeclaration cid) {
            return cid.getNameAsString();
        }
        if (node instanceof EnumDeclaration ed) {
            return ed.getNameAsString();
        }
        if (node instanceof RecordDeclaration rd) {
            return rd.getNameAsString();
        }
        if (node instanceof ObjectCreationExpr oce && oce.getAnonymousClassBody().isPresent()) {
            return "anonymous";
        }
        return null;
    }

    private static boolean isEmptyMethod(Node node) {
        if (node instanceof LambdaExpr lambda) {
            if (lambda.getExpressionBody().isPresent()) {
                return false;
            }
            return lambda.getBody() instanceof BlockStmt block && block.getStatements().isEmpty();
        }
        if (node instanceof MethodDeclaration md) {
            if (md.getBody().isEmpty()) {
                return true;
            }
            return md.getBody().get().getStatements().isEmpty();
        }
        return false;
    }

    /**
     * Recovers the original source line from the {@code // line: N} comment injected by the
     * block-pruner, falling back to the node's own start line when no comment is present.
     */
    private static int getOriginalLine(Node node) {
        // 1. First statement of the body.
        Optional<BlockStmt> body = blockBodyOf(node);
        if (body.isPresent() && !body.get().getStatements().isEmpty()) {
            Statement first = body.get().getStatement(0);
            Integer line = lineFromComment(first.getComment().orElse(null));
            if (line != null) {
                return line;
            }
        }

        // 2. Expression body of a lambda.
        if (node instanceof LambdaExpr lambda && lambda.getExpressionBody().isPresent()) {
            Integer line = lineFromComment(lambda.getExpressionBody().get().getComment().orElse(null));
            if (line != null) {
                return line;
            }
        }

        // 3. Fall back to the node's own leading comment.
        Integer line = lineFromComment(node.getComment().orElse(null));
        if (line != null) {
            return line;
        }

        return node.getBegin().map(p -> p.line).orElse(0);
    }

    private static Optional<BlockStmt> blockBodyOf(Node node) {
        if (node instanceof MethodDeclaration md) {
            return md.getBody().map(b -> (BlockStmt) b);
        }
        if (node instanceof LambdaExpr lambda && lambda.getBody() instanceof BlockStmt block) {
            return Optional.of(block);
        }
        return Optional.empty();
    }

    private static Integer lineFromComment(Comment comment) {
        if (comment == null) {
            return null;
        }
        Matcher matcher = LINE_COMMENT_PATTERN.matcher(comment.getContent());
        if (matcher.find()) {
            return Integer.parseInt(matcher.group(1));
        }
        return null;
    }

    private static String computeClosureName(Deque<Node> nodeStack) {
        Node parent = nodeStack.peek();
        if (parent instanceof VariableDeclarator vd) {
            return vd.getNameAsString();
        }
        if (parent instanceof AssignExpr assign) {
            Expression target = assign.getTarget();
            if (target instanceof NameExpr ne) {
                return ne.getNameAsString();
            }
            if (target instanceof FieldAccessExpr fa) {
                return fa.getNameAsString();
            }
        }
        if (parent instanceof MethodCallExpr mc) {
            return mc.getNameAsString() + "$cb";
        }
        if (parent instanceof ObjectCreationExpr oce) {
            return oce.getType().getNameAsString() + "$cb";
        }
        return "lambda";
    }

    private static List<MethodCallInfo> collectCalls(Node functionNode) {
        List<MethodCallInfo> calls = new ArrayList<>();
        for (Node child : functionNode.getChildNodes()) {
            collectCallsRecursive(child, calls);
        }
        return calls;
    }

    private static void collectCallsRecursive(Node node, List<MethodCallInfo> calls) {
        // Do not descend into nested function-likes; they are emitted as their own nodes.
        if (node instanceof LambdaExpr
                || node instanceof MethodDeclaration
                || node instanceof ClassOrInterfaceDeclaration
                || node instanceof EnumDeclaration
                || node instanceof RecordDeclaration) {
            return;
        }

        if (node instanceof MethodCallExpr call) {
            String scope = null;
            if (call.getScope().isPresent()) {
                Expression scopeExpr = call.getScope().get();
                if (scopeExpr instanceof NameExpr ne) {
                    scope = ne.getNameAsString();
                } else if (scopeExpr instanceof ThisExpr) {
                    scope = "this";
                } else if (scopeExpr instanceof SuperExpr) {
                    scope = "super";
                }
            }
            calls.add(new MethodCallInfo(scope, call.getNameAsString(), call.getArguments().size()));
        }

        for (Node child : node.getChildNodes()) {
            collectCallsRecursive(child, calls);
        }
    }

    private static String extractSource(String[] lines, Node node) {
        Optional<Position> beginOpt = node.getBegin();
        Optional<Position> endOpt = node.getEnd();
        if (beginOpt.isEmpty() || endOpt.isEmpty()) {
            return node.toString();
        }
        Position begin = beginOpt.get();
        Position end = endOpt.get();

        int beginLine = begin.line - 1;
        int endLine = end.line - 1;
        if (beginLine < 0 || endLine >= lines.length || beginLine > endLine) {
            return node.toString();
        }

        if (beginLine == endLine) {
            String line = lines[beginLine];
            int from = Math.max(0, Math.min(begin.column - 1, line.length()));
            int to = Math.max(from, Math.min(end.column, line.length()));
            return line.substring(from, to);
        }

        StringBuilder sb = new StringBuilder();
        String firstLine = lines[beginLine];
        int from = Math.max(0, Math.min(begin.column - 1, firstLine.length()));
        sb.append(firstLine.substring(from));
        sb.append('\n');
        for (int i = beginLine + 1; i < endLine; i++) {
            sb.append(lines[i]).append('\n');
        }
        String lastLine = lines[endLine];
        int to = Math.max(0, Math.min(end.column, lastLine.length()));
        sb.append(lastLine, 0, to);
        return sb.toString();
    }

    // ==============================
    // Call tree rendering
    // ==============================

    private static String renderCallTree(Map<String, MethodNode> methods) {
        StringBuilder md = new StringBuilder();

        Map<String, List<String>> adjacencyList = new LinkedHashMap<>();
        Set<String> calledSignatures = new LinkedHashSet<>();

        for (MethodNode node : methods.values()) {
            List<String> children = new ArrayList<>();
            for (MethodCallInfo call : node.calls) {
                for (MethodNode target : methods.values()) {
                    if (!target.methodName.equals(call.name)) {
                        continue;
                    }
                    boolean isMatch;
                    if (call.scope == null || SPECIAL_SCOPES.contains(call.scope)) {
                        isMatch = true;
                    } else {
                        isMatch = call.scope.equals(target.className)
                                || target.className.endsWith("." + call.scope);
                    }
                    if (isMatch) {
                        children.add(target.signature);
                        calledSignatures.add(target.signature);
                    }
                }
            }
            adjacencyList.put(node.signature, new ArrayList<>(new LinkedHashSet<>(children)));
        }

        List<String> rootSignatures = new ArrayList<>();
        for (String sig : methods.keySet()) {
            if (!calledSignatures.contains(sig)) {
                rootSignatures.add(sig);
            }
        }
        if (rootSignatures.isEmpty()) {
            rootSignatures = new ArrayList<>(methods.keySet());
        }

        Set<String> visited = new LinkedHashSet<>();
        for (String rootSig : rootSignatures) {
            dfsRender(rootSig, methods, adjacencyList, 0, visited, md);
        }

        for (String sig : methods.keySet()) {
            if (!visited.contains(sig)) {
                dfsRender(sig, methods, adjacencyList, 0, visited, md);
            }
        }

        return md.toString();
    }

    private static void dfsRender(String sig, Map<String, MethodNode> methods,
                                  Map<String, List<String>> adjacencyList, int depth,
                                  Set<String> visited, StringBuilder md) {
        String indent = "    ".repeat(depth);

        if (visited.contains(sig)) {
            md.append(indent).append("- **Method:** `").append(sig).append("` *(See above)*\n")
                    .append(indent).append("---\n\n");
            return;
        }

        visited.add(sig);
        MethodNode node = methods.get(sig);
        if (node == null) {
            return;
        }

        md.append(renderMethod(node, depth));
        md.append(indent).append("---\n\n");

        List<String> children = adjacencyList.get(sig);
        if (children != null) {
            for (String childSig : children) {
                dfsRender(childSig, methods, adjacencyList, depth + 1, visited, md);
            }
        }
    }

    private static String renderMethod(MethodNode node, int depth) {
        String indent = "    ".repeat(depth);
        StringBuilder md = new StringBuilder();

        md.append(indent).append("- **Method:** `").append(node.signature)
                .append("` (Params: ").append(node.paramCount).append(")\n");
        md.append(indent).append("- **File Path:** `").append(node.filePath).append("`\n");
        md.append(indent).append("- **Original Line:** `").append(node.startLine).append("`\n\n");

        if (node.sourceCode != null && !node.sourceCode.isEmpty()) {
            String source = node.sourceCode.trim();
            String indentedSource = String.join("\n" + indent, Arrays.asList(source.split("\n", -1)));
            md.append(indent).append("```java\n");
            md.append(indent).append(indentedSource).append("\n");
            md.append(indent).append("```\n");
        }

        if (!node.calls.isEmpty()) {
            md.append("\n").append(indent).append("*Calls:*\n");
            for (MethodCallInfo call : node.calls) {
                String scopeStr = (call.scope != null && !call.scope.isEmpty()) ? call.scope + "." : "";
                md.append(indent).append("    - `").append(scopeStr).append(call.name)
                        .append("(").append(call.argCount).append(" args)`\n");
            }
        }

        md.append("\n");
        return md.toString();
    }
}
