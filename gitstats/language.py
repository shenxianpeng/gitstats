import os
from collections import defaultdict

# Define common extensions and their corresponding languages
LANGUAGE_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".html": "HTML",
    ".css": "CSS",
    ".java": "Java",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".sh": "Shell",
    ".md": "Markdown",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".ts": "TypeScript",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".xml": "XML",
    ".sql": "SQL",
    ".txt": "Text",
    ".ini": "INI",
    ".conf": "Configuration",
    ".log": "Log",
    ".csv": "CSV",
    ".rst": "reStructuredText",
}


def language_data(repo_path):
    language_stats = defaultdict(int)
    total_lines = 0

    for root, _, files in os.walk(repo_path):
        for file in files:
            file_path = os.path.join(root, file)
            _, ext = os.path.splitext(file)
            if ext in LANGUAGE_EXTENSIONS:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = sum(1 for _ in f)
                        language = LANGUAGE_EXTENSIONS[ext]
                        language_stats[language] += lines
                        total_lines += lines
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

    # Return both the raw line counts and percentages
    language_data = {
        lang: {
            "lines": count,
            "percentage": (count / total_lines) * 100 if total_lines > 0 else 0,
        }
        for lang, count in language_stats.items()
    }
    return language_data
