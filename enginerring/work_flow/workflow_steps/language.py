import os
import json
from print_utils.utils import Colors, print_color

from ..language_detector import detect_project_languages

def ensure_language_selected(proj_path):
    """
    Ensure the target programming language is selected and saved in config.json.
    Returns the selected language.
    """
    target_language = 'java'
    config = {}
    config_file = ""

    if proj_path:
        config_file = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except Exception as e:
                print_color(f"[WARN] Could not read config for language selection: {e}", Colors.YELLOW)

        target_language = config.get('language')

        if not target_language:
            detect_dir = config.get('original_git_root', proj_path)
            print_color(f"\n>>> Auto-detecting project language in {detect_dir}...", Colors.CYAN)

            detected_langs = detect_project_languages(detect_dir)

            if len(detected_langs) == 1:
                auto_lang = detected_langs.pop().lower()
                if '/' in auto_lang:
                    auto_lang = auto_lang.split('/')[0]

                target_language = auto_lang
                config['language'] = target_language
                try:
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=4)
                    print_color(f"[Auto-Detect] Successfully identified and set language to {target_language.upper()}.", Colors.GREEN)
                except Exception as e:
                    print_color(f"[WARN] Could not save auto-detected language to config: {e}", Colors.YELLOW)
                return target_language

            elif len(detected_langs) > 1:
                print_color(f"[Auto-Detect] Multiple languages detected: {', '.join(detected_langs)}. Falling back to manual selection.", Colors.YELLOW)
            else:
                print_color("[Auto-Detect] Could not confidently detect language. Falling back to manual selection.", Colors.YELLOW)

            print_color("\n========================================", Colors.CYAN)
            print_color("       Select Programming Language      ", Colors.CYAN)
            print_color("========================================", Colors.CYAN)
            print("  1. Java\n  2. PHP\n  3. Python\n  4. JavaScript")
            print_color("========================================", Colors.CYAN)
            lang_choice = input("Enter your choice [1]: ").strip() or "1"
            lang_map = {'1': 'java', '2': 'php', '3': 'python', '4': 'javascript'}
            target_language = lang_map.get(lang_choice, 'java')

            config['language'] = target_language
            try:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4)
                print_color(f"[Info] Language set to {target_language.upper()} and saved to config.", Colors.GREEN)
            except Exception as e:
                print_color(f"[WARN] Could not save language to config: {e}", Colors.YELLOW)
        else:
            print_color(f"[Info] Using configured language: {target_language.upper()}", Colors.GREEN)

    return target_language