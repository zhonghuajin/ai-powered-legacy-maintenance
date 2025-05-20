package com.example.instrumentor.block.wrapper;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.stmt.*;

import com.github.javaparser.ast.visitor.ModifierVisitor;
import com.github.javaparser.ast.visitor.Visitable;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class BlockWrapperTool {

    public static void main(String[] args) {
        String targetPath;
        if (args.length > 0) {
            targetPath = args[0];
            System.out.println("Using target path from arguments: " + targetPath);
        } else {
            targetPath = "src/main/java/com/example";
            System.out.println("No arguments provided. Using default path: " + targetPath);
        }

        try {
            processPath(Paths.get(targetPath));
            System.out.println("Processing completed!");
        } catch (IOException e) {
            System.err.println("Error processing file: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private static void processPath(Path path) throws IOException {
        if (!Files.exists(path)) {
            System.out.println("Path does not exist: " + path);
            return;
        }

        if (Files.isRegularFile(path) && path.toString().endsWith(".java")) {
            processJavaFile(path);
        } else if (Files.isDirectory(path)) {
            Files.walkFileTree(path, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                    if (file.toString().endsWith(".java")) {
                        processJavaFile(file);
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }

    private static void processJavaFile(Path javaFilePath) throws IOException {
        System.out.println("Processing: " + javaFilePath);

        CompilationUnit cu = StaticJavaParser.parse(javaFilePath);

        ModifierVisitor<Void> visitor = new BlockWrapperVisitor();
        visitor.visit(cu, null);

        Files.writeString(javaFilePath, cu.toString(), StandardOpenOption.TRUNCATE_EXISTING);
    }

    private static class BlockWrapperVisitor extends ModifierVisitor<Void> {

        @Override
        public Visitable visit(IfStmt n, Void arg) {
            super.visit(n, arg);

            if (!(n.getThenStmt() instanceof BlockStmt)) {
                n.setThenStmt(wrapInBlock(n.getThenStmt()));
            }

            if (n.getElseStmt().isPresent()) {
                Statement elseStmt = n.getElseStmt().get();

                if (!(elseStmt instanceof BlockStmt) && !(elseStmt instanceof IfStmt)) {
                    n.setElseStmt(wrapInBlock(elseStmt));
                }
            }
            return n;
        }

        @Override
        public Visitable visit(ForStmt n, Void arg) {
            super.visit(n, arg);
            if (!(n.getBody() instanceof BlockStmt)) {
                n.setBody(wrapInBlock(n.getBody()));
            }
            return n;
        }

        @Override
        public Visitable visit(ForEachStmt n, Void arg) {
            super.visit(n, arg);
            if (!(n.getBody() instanceof BlockStmt)) {
                n.setBody(wrapInBlock(n.getBody()));
            }
            return n;
        }

        @Override
        public Visitable visit(WhileStmt n, Void arg) {
            super.visit(n, arg);
            if (!(n.getBody() instanceof BlockStmt)) {
                n.setBody(wrapInBlock(n.getBody()));
            }
            return n;
        }

        @Override
        public Visitable visit(DoStmt n, Void arg) {
            super.visit(n, arg);
            if (!(n.getBody() instanceof BlockStmt)) {
                n.setBody(wrapInBlock(n.getBody()));
            }
            return n;
        }

        private BlockStmt wrapInBlock(Statement stmt) {
            BlockStmt block = new BlockStmt();
            block.addStatement(stmt.clone());
            return block;
        }
    }
}