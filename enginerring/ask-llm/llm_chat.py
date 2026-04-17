"""
llm_chat.py  —  Multi-provider LLM CLI (2026 edition)

Usage:
    python llm_chat.py -p claude                        # 进入交互式多轮对话
    python llm_chat.py -p gpt -f prompt.md              # 单轮：读文件作为 prompt
    python llm_chat.py -p deepseek -r high              # 指定 reasoning 强度
    python llm_chat.py -p qwen -m qwen3-max --no-stream # 关闭流式
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Iterator, Optional

from openai import OpenAI
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------
# `sdk`:  "openai" (兼容 OpenAI SDK) 或 "anthropic"
# `reasoning_style`:
#     - "none"           : 不支持思考链
#     - "openai_effort"  : OpenAI GPT-5.x 风格，使用 reasoning_effort
#     - "anthropic"      : Claude extended thinking，使用 thinking={"type":"enabled","budget_tokens":N}
#     - "deepseek"       : deepseek-reasoner，返回流里带 reasoning_content delta
#     - "qwen"           : enable_thinking + thinking_budget（通过 extra_body 传递）
#     - "glm"            : thinking={"type":"enabled"}（通过 extra_body 传递）
PROVIDERS = {
    "gpt": {
        "sdk": "openai",
        "env_key": "OPENAI_API_KEY",
        "base_url": None,
        "default_model": "gpt-5.4",
        "reasoning_style": "openai_effort",
        "max_tokens": 8192,
    },
    "deepseek": {
        "sdk": "openai",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-reasoner",
        "reasoning_style": "deepseek",
        "max_tokens": 8192,
    },
    "glm": {
        "sdk": "openai",
        "env_key": "ZHIPU_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4.6",
        "reasoning_style": "glm",
        "max_tokens": 8192,
    },
    "kimi": {
        "sdk": "openai",
        "env_key": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k2",           # 按官方文档调整
        "reasoning_style": "none",
        "max_tokens": 8192,
    },
    "qwen": {
        "sdk": "openai",
        "env_key": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen3-max",
        "reasoning_style": "qwen",
        "max_tokens": 8192,
    },
    "claude": {
        "sdk": "anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": None,
        "default_model": "claude-opus-4-7",
        "reasoning_style": "anthropic",
        "max_tokens": 16384,
    },
}

REASONING_BUDGETS = {      # 映射 low/medium/high 到 token 预算
    "low":    2048,
    "medium": 8192,
    "high":   24576,
}

# ---------------------------------------------------------------------------
# ANSI colors (简单版，不引入额外依赖)
# ---------------------------------------------------------------------------
class C:
    RESET  = "\033[0m"
    DIM    = "\033[2m"
    BOLD   = "\033[1m"
    CYAN   = "\033[36m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    RED    = "\033[31m"
    MAGENTA= "\033[35m"

# ---------------------------------------------------------------------------
# Core client abstraction
# ---------------------------------------------------------------------------
class LLMClient:
    def __init__(self, provider: str, model: Optional[str] = None,
                 reasoning: str = "off", system: Optional[str] = None):
        if provider not in PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")
        self.provider = provider
        self.cfg = PROVIDERS[provider]
        self.model = model or self.cfg["default_model"]
        self.reasoning = reasoning     # "off" | "low" | "medium" | "high"
        self.system = system
        self.history: list[dict] = []  # 存 user/assistant 轮次（不含 system）

        api_key = os.environ.get(self.cfg["env_key"], "").strip()
        if not api_key:
            raise ValueError(
                f"Missing {self.cfg['env_key']}. "
                f"Please set it in .env or environment."
            )

        if self.cfg["sdk"] == "anthropic":
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            self.client = OpenAI(api_key=api_key, base_url=self.cfg["base_url"])

    # --------------------------- public API --------------------------------
    def chat(self, user_msg: str, stream: bool = True) -> str:
        """发送一条用户消息，返回最终 assistant 文本，并更新 history。"""
        self.history.append({"role": "user", "content": user_msg})

        if self.cfg["sdk"] == "anthropic":
            answer = self._anthropic_stream() if stream else self._anthropic_once()
        else:
            answer = self._openai_stream() if stream else self._openai_once()

        self.history.append({"role": "assistant", "content": answer})
        return answer

    def reset(self):
        self.history.clear()

    def save(self, path: str):
        data = {
            "provider": self.provider,
            "model": self.model,
            "reasoning": self.reasoning,
            "system": self.system,
            "messages": self.history,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # --------------------------- OpenAI-compatible ------------------------
    def _openai_messages(self):
        msgs = []
        if self.system:
            msgs.append({"role": "system", "content": self.system})
        msgs.extend(self.history)
        return msgs

    def _openai_kwargs(self):
        kwargs = {
            "model": self.model,
            "messages": self._openai_messages(),
            "max_tokens": self.cfg["max_tokens"],
        }
        style = self.cfg["reasoning_style"]
        if self.reasoning == "off":
            if style == "qwen":
                kwargs.setdefault("extra_body", {})["enable_thinking"] = False
            elif style == "glm":
                kwargs.setdefault("extra_body", {})["thinking"] = {"type": "disabled"}
            return kwargs

        # reasoning enabled
        budget = REASONING_BUDGETS.get(self.reasoning, REASONING_BUDGETS["medium"])
        if style == "openai_effort":
            kwargs["reasoning_effort"] = self.reasoning   # low/medium/high
        elif style == "qwen":
            kwargs.setdefault("extra_body", {})
            kwargs["extra_body"]["enable_thinking"] = True
            kwargs["extra_body"]["thinking_budget"] = budget
        elif style == "glm":
            kwargs.setdefault("extra_body", {})
            kwargs["extra_body"]["thinking"] = {"type": "enabled"}
        # deepseek-reasoner 不需要额外参数；模型本身就思考
        return kwargs

    def _openai_once(self) -> str:
        resp = self.client.chat.completions.create(**self._openai_kwargs())
        msg = resp.choices[0].message
        # DeepSeek-reasoner: message 里会带 reasoning_content
        rc = getattr(msg, "reasoning_content", None)
        if rc:
            print(f"{C.DIM}--- reasoning ---\n{rc}\n--- answer ---{C.RESET}")
        return msg.content or ""

    def _openai_stream(self) -> str:
        kwargs = self._openai_kwargs()
        kwargs["stream"] = True
        stream = self.client.chat.completions.create(**kwargs)

        answer_parts, thinking_parts = [], []
        in_thinking_block = False

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # DeepSeek & 部分兼容 provider 会有 reasoning_content 字段
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                if not in_thinking_block:
                    print(f"{C.DIM}{C.MAGENTA}[thinking]{C.RESET}{C.DIM} ", end="", flush=True)
                    in_thinking_block = True
                print(f"{C.DIM}{rc}{C.RESET}", end="", flush=True)
                thinking_parts.append(rc)
            if delta.content:
                if in_thinking_block:
                    print(f"\n{C.GREEN}[answer]{C.RESET} ", end="", flush=True)
                    in_thinking_block = False
                print(delta.content, end="", flush=True)
                answer_parts.append(delta.content)
        print()  # newline
        return "".join(answer_parts)

    # --------------------------- Anthropic --------------------------------
    def _anthropic_kwargs(self):
        kwargs = {
            "model": self.model,
            "max_tokens": self.cfg["max_tokens"],
            "messages": self.history,
        }
        if self.system:
            kwargs["system"] = self.system
        if self.reasoning != "off":
            budget = REASONING_BUDGETS.get(self.reasoning, REASONING_BUDGETS["medium"])
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            # 启用 thinking 时 max_tokens 必须 > budget
            kwargs["max_tokens"] = max(kwargs["max_tokens"], budget + 4096)
            # 官方要求 thinking 开启时 temperature 为默认
        return kwargs

    def _anthropic_once(self) -> str:
        resp = self.client.messages.create(**self._anthropic_kwargs())
        text_out = []
        for block in resp.content:
            if block.type == "thinking":
                print(f"{C.DIM}{C.MAGENTA}[thinking]{C.RESET}{C.DIM} {block.thinking}{C.RESET}")
            elif block.type == "text":
                text_out.append(block.text)
        return "".join(text_out)

    def _anthropic_stream(self) -> str:
        answer_parts = []
        current_block_type = None

        with self.client.messages.stream(**self._anthropic_kwargs()) as stream:
            for event in stream:
                et = event.type
                if et == "content_block_start":
                    current_block_type = event.content_block.type
                    if current_block_type == "thinking":
                        print(f"{C.DIM}{C.MAGENTA}[thinking]{C.RESET}{C.DIM} ",
                              end="", flush=True)
                    elif current_block_type == "text":
                        print(f"{C.GREEN}[answer]{C.RESET} ", end="", flush=True)
                elif et == "content_block_delta":
                    d = event.delta
                    if d.type == "thinking_delta":
                        print(f"{C.DIM}{d.thinking}{C.RESET}", end="", flush=True)
                    elif d.type == "text_delta":
                        print(d.text, end="", flush=True)
                        answer_parts.append(d.text)
                elif et == "content_block_stop":
                    print()    # newline per block
        return "".join(answer_parts)


# ---------------------------------------------------------------------------
# CLI / REPL
# ---------------------------------------------------------------------------
HELP_TEXT = f"""
{C.BOLD}Commands{C.RESET}
  /help                   显示帮助
  /reset                  清空对话历史
  /history                查看历史消息
  /save [path]            保存对话为 JSON（默认 chat_<time>.json）
  /system <text>          设置 system prompt（会清空历史）
  /reasoning off|low|medium|high   切换推理强度
  /model <name>           切换模型（保留历史）
  /file <path>            把文件内容作为下一条 user message 发送
  /exit  或  /quit        退出
"""

def interactive_loop(client: LLMClient, stream: bool):
    print(f"{C.CYAN}{C.BOLD}LLM Chat{C.RESET}  "
          f"provider={C.YELLOW}{client.provider}{C.RESET}  "
          f"model={C.YELLOW}{client.model}{C.RESET}  "
          f"reasoning={C.YELLOW}{client.reasoning}{C.RESET}  "
          f"stream={C.YELLOW}{stream}{C.RESET}")
    print(f"{C.DIM}Type /help for commands, /exit to quit.{C.RESET}\n")

    while True:
        try:
            user = input(f"{C.BOLD}{C.CYAN}You>{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue

        # ---- commands ----
        if user.startswith("/"):
            parts = user.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ("/exit", "/quit"):
                break
            elif cmd == "/help":
                print(HELP_TEXT)
            elif cmd == "/reset":
                client.reset()
                print(f"{C.YELLOW}History cleared.{C.RESET}")
            elif cmd == "/history":
                for m in client.history:
                    role = m["role"]
                    color = C.CYAN if role == "user" else C.GREEN
                    print(f"{color}[{role}]{C.RESET} {m['content'][:200]}"
                          f"{'...' if len(m['content'])>200 else ''}")
            elif cmd == "/save":
                path = arg or f"chat_{datetime.now():%Y%m%d_%H%M%S}.json"
                client.save(path)
                print(f"{C.YELLOW}Saved to {os.path.abspath(path)}{C.RESET}")
            elif cmd == "/system":
                client.system = arg
                client.reset()
                print(f"{C.YELLOW}System prompt set, history cleared.{C.RESET}")
            elif cmd == "/reasoning":
                if arg not in ("off", "low", "medium", "high"):
                    print(f"{C.RED}Usage: /reasoning off|low|medium|high{C.RESET}")
                else:
                    client.reasoning = arg
                    print(f"{C.YELLOW}Reasoning -> {arg}{C.RESET}")
            elif cmd == "/model":
                if not arg:
                    print(f"{C.RED}Usage: /model <name>{C.RESET}")
                else:
                    client.model = arg
                    print(f"{C.YELLOW}Model -> {arg}{C.RESET}")
            elif cmd == "/file":
                if not os.path.exists(arg):
                    print(f"{C.RED}File not found: {arg}{C.RESET}")
                    continue
                with open(arg, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"{C.DIM}[loaded {len(content)} chars from {arg}]{C.RESET}")
                _do_turn(client, content, stream)
            else:
                print(f"{C.RED}Unknown command. /help for list.{C.RESET}")
            continue

        _do_turn(client, user, stream)


def _do_turn(client: LLMClient, user_msg: str, stream: bool):
    print(f"{C.BOLD}{C.GREEN}{client.provider}>{C.RESET} ", end="", flush=True)
    try:
        client.chat(user_msg, stream=stream)
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}[interrupted]{C.RESET}")
        # 回滚最后的 user 消息（因为没得到完整回复）
        if client.history and client.history[-1]["role"] == "user":
            client.history.pop()
    except Exception as e:
        print(f"\n{C.RED}[Error] {e}{C.RESET}")
        if client.history and client.history[-1]["role"] == "user":
            client.history.pop()


def one_shot(client: LLMClient, file_path: str, stream: bool, output: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        prompt = f.read()

    print(f"{C.DIM}[*] {client.provider}/{client.model}  "
          f"reasoning={client.reasoning}{C.RESET}")
    print(f"{C.BOLD}{C.GREEN}{client.provider}>{C.RESET} ", end="", flush=True)
    answer = client.chat(prompt, stream=stream)

    with open(output, "w", encoding="utf-8") as f:
        f.write(answer)
    print(f"\n{C.DIM}[*] Saved to {os.path.abspath(output)}{C.RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="Multi-provider LLM CLI with streaming, multi-turn, "
                    "and reasoning support.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-p", "--provider", required=True,
                        choices=list(PROVIDERS.keys()))
    parser.add_argument("-m", "--model", default=None)
    parser.add_argument("-f", "--file", default=None,
                        help="One-shot mode: read this file as the prompt.")
    parser.add_argument("-r", "--reasoning", default="off",
                        choices=["off", "low", "medium", "high"],
                        help="Reasoning effort (if supported).")
    parser.add_argument("-s", "--system", default=None,
                        help="System prompt.")
    parser.add_argument("-o", "--output", default="output.md",
                        help="Output file for one-shot mode.")
    parser.add_argument("--no-stream", action="store_true",
                        help="Disable streaming.")
    args = parser.parse_args()

    try:
        client = LLMClient(
            provider=args.provider,
            model=args.model,
            reasoning=args.reasoning,
            system=args.system,
        )
        stream = not args.no_stream

        if args.file:
            one_shot(client, args.file, stream, args.output)
        else:
            interactive_loop(client, stream)

    except Exception as e:
        print(f"{C.RED}[Error] {e}{C.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()