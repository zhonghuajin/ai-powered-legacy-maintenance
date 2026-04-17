import os
import sys
import argparse
from openai import OpenAI
import anthropic
from dotenv import load_dotenv

# Core update: automatically load .env file from the current directory
load_dotenv()

PROVIDERS = {
    "gpt": {"env_key": "OPENAI_API_KEY", "base_url": None, "default_model": "gpt-4o"},
    "deepseek": {"env_key": "DEEPSEEK_API_KEY", "base_url": "https://api.deepseek.com", "default_model": "deepseek-reasoner"},
    "glm": {"env_key": "ZHIPU_API_KEY", "base_url": "https://open.bigmodel.cn/api/paas/v4", "default_model": "glm-4"},
    "kimi": {"env_key": "MOONSHOT_API_KEY", "base_url": "https://api.moonshot.cn/v1", "default_model": "moonshot-v1-8k"},
    "qwen": {"env_key": "DASHSCOPE_API_KEY", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "default_model": "qwen-max"},
    "claude": {"env_key": "ANTHROPIC_API_KEY", "base_url": None, "default_model": "claude-3-5-sonnet-20241022"}
}

def read_markdown_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def get_response(provider, model, prompt):
    config = PROVIDERS.get(provider)
    if not config:
        raise ValueError(f"Unsupported provider: {provider}")

    # Now the Key can be successfully read from .env
    api_key = os.environ.get(config["env_key"])
    if not api_key or api_key.strip() == "":
        raise ValueError(f"Missing API Key! Please set {config['env_key']} in the .env file or export it as an environment variable.")

    model_name = model if model else config["default_model"]
    print(f"[*] Requesting {provider} (model: {model_name})...")

    if provider == "claude":
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    else:
        client = OpenAI(api_key=api_key, base_url=config["base_url"])
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

def main():
    parser = argparse.ArgumentParser(description="Multi-provider LLM terminal request tool")
    parser.add_argument("-p", "--provider", type=str, required=True, choices=list(PROVIDERS.keys()), help="Choose LLM provider")
    parser.add_argument("-f", "--file", type=str, required=True, help="Path to the Markdown file as prompt")
    parser.add_argument("-m", "--model", type=str, default=None, help="Specify the model version")
    
    args = parser.parse_args()

    try:
        prompt_content = read_markdown_file(args.file)
        response = get_response(args.provider, args.model, prompt_content)
        
        print("\n" + "="*50 + " Response " + "="*50)
        print(response)
        print("="*110 + "\n")
        
        # 将响应直接保存到当前工作目录下的固定文件中（例如 output.md）
        output_filename = "output.md"
        with open(output_filename, 'w', encoding='utf-8') as out_file:
            out_file.write(response)
            
        print(f"[*] Response successfully saved to: {os.path.abspath(output_filename)}\n")
        
    except Exception as e:
        print(f"\n[Error]: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()