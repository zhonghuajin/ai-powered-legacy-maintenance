package com.example.instrumentor;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.RecordDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.AssignExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.LambdaExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.List;

/**
 * Collects method/closure line ranges from a {@link CompilationUnit}, mirroring the PHP
 * ({@code MethodRangeVisitor}) and JS range-collection logic. The signatures produced here
 * ({@code Class::method@startLine}) are intentionally identical to those emitted by
 * {@code data-structuring}, so block-to-signature attribution stays consistent across the pipeline.
 */
public final class MethodRangeCollector {

    private MethodRangeCollector() {
    }

    public static List<MethodRange> collect(CompilationUnit cu, String absolutePath) {
        String packageName = cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse("");
        List<MethodRange> ranges = new ArrayList<>();
        Deque<Node> nodeStack = new ArrayDeque<>();
        Deque<String> classStack = new ArrayDeque<>();
        walk(cu, absolutePath, packageName, ranges, nodeStack, classStack);
        return ranges;
    }

    private static void walk(Node node, String absolutePath, String packageName,
                             List<MethodRange> ranges, Deque<Node> nodeStack, Deque<String> classStack) {
        boolean pushedClass = false;
        String typeName = typeNameOf(node);
        if (typeName != null) {
            classStack.push(typeName);
            pushedClass = true;
        }

        if (node instanceof MethodDeclaration || node instanceof ConstructorDeclaration
                || node instanceof LambdaExpr) {
            String closureName = (node instanceof LambdaExpr) ? computeClosureName(nodeStack) : null;
            addRange(node, closureName, absolutePath, packageName, classStack, ranges);
        }

        nodeStack.push(node);
        for (Node child : node.getChildNodes()) {
            walk(child, absolutePath, packageName, ranges, nodeStack, classStack);
        }
        nodeStack.pop();

        if (pushedClass) {
            classStack.pop();
        }
    }

    private static void addRange(Node node, String closureName, String absolutePath, String packageName,
                                 Deque<String> classStack, List<MethodRange> ranges) {
        String methodName;
        if (node instanceof MethodDeclaration md) {
            methodName = md.getNameAsString();
        } else if (node instanceof ConstructorDeclaration cd) {
            methodName = cd.getNameAsString();
        } else {
            methodName = closureName != null ? closureName : "lambda";
        }

        int start = node.getBegin().map(p -> p.line).orElse(-1);
        int end = node.getEnd().map(p -> p.line).orElse(-1);
        if (start < 0 || end < 0) {
            return;
        }

        String currentClass = currentClassName(packageName, classStack);
        String name = currentClass.isEmpty()
                ? methodName + "@" + start
                : currentClass + "::" + methodName + "@" + start;

        ranges.add(new MethodRange(absolutePath, name, start, end));
    }

    private static String currentClassName(String packageName, Deque<String> classStack) {
        if (classStack.isEmpty()) {
            return "";
        }
        List<String> names = new ArrayList<>(classStack);
        Collections.reverse(names);
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
}
