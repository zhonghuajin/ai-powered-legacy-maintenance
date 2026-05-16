import os
import subprocess
from collections import Counter

LANGUAGE_RULES = {
    "Python": {
        "manifests": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
        "extensions": [".py"]
    },
    "Java": {
        "manifests": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "extensions": [".java"]
    },
    "PHP": {
        "manifests": ["composer.json"],
        "extensions": [".php"]
    },
    "JavaScript/Node": {
        "manifests": ["package.json", "yarn.lock", "pnpm-workspace.yaml"],
        "extensions": [".js", ".jsx", ".ts", ".tsx"]
    },
    "Go": {
        "manifests": ["go.mod"],
        "extensions": [".go"]
    },
    "Rust": {
        "manifests": ["Cargo.toml"],
        "extensions": [".rs"]
    },
    "C/C++": {
        "manifests": ["CMakeLists.txt", "Makefile"],
        "extensions": [".c", ".cpp", ".h", ".hpp", ".cc"]
    },
    "C#": {
        "manifests": [],
        "extensions": [".cs"]
    },
    "Ruby": {
        "manifests": ["Gemfile"],
        "extensions": [".rb"]
    }
}

IGNORE_DIRS = {'.git', 'node_modules', 'vendor', 'venv', '.venv', 'target', 'build', 'dist', 'out', 'bin'}

MANIFEST_TO_LANG = {}
EXT_TO_LANG = {}

for lang, rules in LANGUAGE_RULES.items():
    for manifest in rules.get("manifests", []):
        MANIFEST_TO_LANG[manifest] = lang
    for ext in rules.get("extensions", []):
        EXT_TO_LANG[ext] = lang

def detect_project_languages(root_dir, noise_threshold=3):
    """
    智能项目语言检测
    :param root_dir: 项目根目录
    :param noise_threshold: 噪声阈值，某语言文件数大于此值才被认定为有效语言
    :return: 包含检测到的语言名称的 set
    """
    if not root_dir or not os.path.exists(root_dir):
        return set()

    detected = set()

    try:
        root_files = os.listdir(root_dir)
        for file in root_files:

            if file in MANIFEST_TO_LANG:
                detected.add(MANIFEST_TO_LANG[file])

            elif file.endswith('.sln') or file.endswith('.csproj'):
                detected.add("C#")

        if detected:
            return detected
    except Exception:
        pass

    lang_counter = Counter()

    try:

        result = subprocess.run(
            ['git', 'ls-files'],
            cwd=root_dir,
            capture_output=True,
            text=True,
            check=True
        )
        files = result.stdout.splitlines()

        for file in files:
            _, ext = os.path.splitext(file)
            if ext in EXT_TO_LANG:
                lang_counter[EXT_TO_LANG[ext]] += 1

    except subprocess.CalledProcessError:

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for file in files:
                _, ext = os.path.splitext(file)
                if ext in EXT_TO_LANG:
                    lang_counter[EXT_TO_LANG[ext]] += 1

    for lang, count in lang_counter.items():
        if count > noise_threshold:
            detected.add(lang)

    if not detected and lang_counter:
        detected.add(lang_counter.most_common(1)[0][0])

    return detected