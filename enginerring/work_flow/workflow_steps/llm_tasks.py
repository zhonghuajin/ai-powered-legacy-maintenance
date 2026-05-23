import os
import sys
import importlib
from print_utils.utils import Colors, print_color
from ..prechecks import setup_windows_proxy

def ask_llm_for_localization(ask_llm_dir):
    print_color("\n>>> Asking LLM for Task Analysis...", Colors.CYAN)
    setup_windows_proxy()

    if ask_llm_dir not in sys.path:
        sys.path.insert(0, ask_llm_dir)

    try:
        import run as ask_llm_run

        original_cwd = os.getcwd()

        file_path = os.path.join(original_cwd, "AI_Task_Prompt.md")
        output_path = os.path.join(original_cwd, "output.md")

        os.chdir(ask_llm_dir)

        ask_llm_run.run_api(
            file_path=file_path,
            output_path=output_path
        )

        os.chdir(original_cwd)
        print_color(f"[+] LLM response saved to {output_path}", Colors.GREEN)

    except ImportError as e:
        print_color(
            f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error during LLM API call: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)


def generate_fix_prompt(work_dir, proj_path=None):
    print_color("\n>>> Generating Fix Prompt...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix_bug")

    if fix_bug_dir not in sys.path:
        sys.path.insert(0, fix_bug_dir)

    try:
        import generate_fix_prompt as fix_prompt_gen

        importlib.reload(fix_prompt_gen)

        original_cwd = os.getcwd()
        os.chdir(work_dir)

        report_path = os.path.join(work_dir, "output.md")

        fix_prompt_gen.generate_prompt(
            proj_path=proj_path, report_path=report_path)

        os.chdir(original_cwd)
    except ImportError as e:
        print_color(
            f"[!] Failed to import generate_fix_prompt from {fix_bug_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error generating fix prompt: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)


def ask_llm_for_code_fix(ask_llm_dir):
    print_color("\n>>> Asking LLM for Code Fix...", Colors.CYAN)

    if ask_llm_dir not in sys.path:
        sys.path.insert(0, ask_llm_dir)

    try:
        import run as ask_llm_run

        original_cwd = os.getcwd()

        file_path = os.path.join(original_cwd, "AI_Apply_Fix_Prompt.md")
        output_path = os.path.join(original_cwd, "output.md")

        os.chdir(ask_llm_dir)

        print_color(f"[+] Using prompt file: {file_path}", Colors.GREEN)

        ask_llm_run.run_api(
            file_path=file_path,
            output_path=output_path
        )

        os.chdir(original_cwd)
        print_color(f"[+] LLM response saved to {output_path}", Colors.GREEN)

    except ImportError as e:
        print_color(
            f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error during LLM API call: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)