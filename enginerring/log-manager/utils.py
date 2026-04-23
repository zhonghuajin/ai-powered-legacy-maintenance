# utils.py
import sys

class Colors:
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    DARKGRAY = '\033[90m'
    RESET = '\033[0m'

def print_color(text, color, end='\n'):
    print(f"{color}{text}{Colors.RESET}", end=end)

def pause_for_next_step(completed_step, next_step):
    print()
    print_color("*****************************************************************", Colors.YELLOW)
    if completed_step:
        print_color(f"   {completed_step} completed!", Colors.GREEN)
    print_color(f"   👉 Press [Enter] to continue to {next_step} ...", Colors.YELLOW)
    print_color("*****************************************************************", Colors.YELLOW)
    input()