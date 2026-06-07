package com.example.instrumentor;

/**
 * A single method/closure line range, aligned with the PHP/JS {@code MethodRangeVisitor} output.
 * {@code name} carries the {@code Class::method@startLine} signature; {@code start}/{@code end} are
 * the 1-based source line numbers.
 */
public class MethodRange {
    public final String file;
    public final String name;
    public final int start;
    public final int end;

    public MethodRange(String file, String name, int start, int end) {
        this.file = file;
        this.name = name;
        this.start = start;
        this.end = end;
    }
}
