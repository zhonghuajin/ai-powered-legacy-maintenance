def generate_prompt(dependency_files, whitelist_paths, dependency_snippet):
    """
    Generate a prompt for analyzing where to add an instrumentation dependency.

    :param dependency_files: list of str, paths to dependency management files
    :param whitelist_paths: list of str, whitelist directories needing instrumentation
    :param dependency_snippet: str, the dependency XML snippet to be added
    :return: str, the assembled prompt
    """

    # 1. Format dependency management file list
    formatted_files = "\n".join([f"- {file}" for file in dependency_files])

    # 2. Format instrumentation whitelist list
    formatted_whitelist = "\n".join([f"- {path}" for path in whitelist_paths])

    # 3. Prompt template (English only)
    prompt_template = f"""You are an experienced software development engineer and build tool expert.
I need to add an instrumentation dependency in a multi-module project. Based on the provided "Instrumentation Whitelist Directories", analyze and infer which "Dependency Management Files" should include this dependency.

### 1. Candidate Dependency Management Files:
{formatted_files}

### 2. Instrumentation Whitelist Directories (directories where instrumentation should take effect):
{formatted_whitelist}

### 3. Instrumentation Dependency to Add:
```xml
{dependency_snippet}
```

### Task Requirements:
Analyze which module(s) the whitelist directories belong to, matching them to the dependency management files above.
Output the path(s) of the dependency management file(s) you determine need modification, strictly in the following format without any extra commentary:

[file_path1]
[file_path2]
"""
    return prompt_template


# ==========================================
# Test input
# ==========================================
if __name__ == "__main__":
    # 1) Dependency management file list
    files_input = [
        r"D:\temp\scenario-based-runtime-context-for-ai\evidence\spring-boot-49854\reproducer\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\evidence\spring-boot-49951\reproducer\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\evidence\spring-boot-50021\reproducer\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\block-pruner\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\data-structuring\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\instrumentor\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\instrumentor-activator\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\instrumentor-log-monitor\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\Instrumentor-log-recorder\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\instrumentor-test\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\instrumentor-with-encoding\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\log-deduplicator\pom.xml",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\trace-visualizer\package.json"
    ]

    # 2) Instrumentation whitelist directories
    whitelist_input = [
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\instrumentor-test\src\main\java\com\example\instrumentor\happens\before",
        r"D:\temp\scenario-based-runtime-context-for-ai\poc\log-deduplicator"
    ]

    # 3) Instrumentation dependency snippet
    dependency_input = """<dependency>
    <groupId>com.example</groupId>
    <artifactId>instrumentor-log-monitor</artifactId>
    <version>1.0-SNAPSHOT</version>
</dependency>"""

    # Generate and print the prompt
    final_prompt = generate_prompt(files_input, whitelist_input, dependency_input)
    print(final_prompt)