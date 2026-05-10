package com.example.instrumentor.data.structuring;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

public class MarkdownGenerator {

    public static void generate(String jsonContent, String outputPath) throws IOException {
        JsonObject root = JsonParser.parseString(jsonContent).getAsJsonObject();
        StringBuilder md = new StringBuilder();

        if (root.has("threads")) {
            md.append("# Thread Traces\n\n");
            md.append("> **Data Schema & Legend:**\n");
            md.append("> This section represents the execution call tree for each thread.\n");
            md.append("> - **Call Tree**: Hierarchical execution flow. Each node contains the source file and pruned source code.\n\n");

            for (JsonElement tElem : root.getAsJsonArray("threads")) {
                JsonObject thread = tElem.getAsJsonObject();
                md.append("## ").append(thread.get("name").getAsString())
                  .append(" (Order: ").append(thread.get("order").getAsInt()).append(")\n");

                // block_trace / Trace output has been removed as requested.

                if (thread.has("call_tree") && !thread.get("call_tree").isJsonNull()) {
                    JsonElement callTreeElem = thread.get("call_tree");
                    if (callTreeElem.isJsonArray()) {
                        for (JsonElement callElem : callTreeElem.getAsJsonArray()) {
                            processCallNode(callElem.getAsJsonObject(), md, 0);
                        }
                    } else if (callTreeElem.isJsonObject()) {
                        processCallNode(callTreeElem.getAsJsonObject(), md, 0);
                    }
                }
                md.append("\n---\n\n");
            }
        }

        Files.writeString(Paths.get(outputPath), md.toString(), StandardCharsets.UTF_8);
    }

    private static void processCallNode(JsonObject node, StringBuilder md, int level) {
        String indent = "    ".repeat(level);
        String contentIndent = indent + "    ";

        if (node.has("file")) {
            md.append(indent).append("- *File:* `").append(node.get("file").getAsString()).append("`\n");
        } else {
            md.append(indent).append("- *(no file)*\n");
        }

        // executed_blocks is completely ignored here, as requested.

        if (node.has("source")) {
            String source = node.get("source").getAsString();
            source = source.replaceAll("//\\s*\\[Executed Block ID:.*?\\]", "").trim();
            
            md.append(contentIndent).append("```java\n");
            for (String line : source.split("\n")) {
                md.append(contentIndent).append(line).append("\n");
            }
            md.append(contentIndent).append("```\n");
        }

        if (node.has("calls")) {
            md.append(contentIndent).append("*Calls:*\n");
            for (JsonElement child : node.getAsJsonArray("calls")) {
                processCallNode(child.getAsJsonObject(), md, level + 1);
            }
        }
    }
}