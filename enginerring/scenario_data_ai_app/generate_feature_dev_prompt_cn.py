#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# ==========================================
# 1. 定义 Prompt 模板
# ==========================================
PROMPT_TEMPLATE = """# 代码二次开发与功能扩展指导任务

你是一位资深软件架构师和代码开发专家。请根据现有的代码执行轨迹数据，指导并帮助我实现新的功能需求。

---

## 📋 需求定义

**🎯 目标新功能**：
{target_feature}

**💬 补充说明（选填）**：
{additional_info}

---

## 🔍 场景调用链数据说明

以下数据来自真实系统运行时的追踪日志，包含以下核心信息：
1. **Trace Sequence**：线程执行的基本代码块的线性序列。
2. **Call Tree**：包含方法签名、源文件、执行的 Block ID，以及**经过修剪的源码**。
3. **重要前提**：数据中仅包含**实际执行过**的代码。如果某段代码没有出现在数据中，说明它在该场景下没有执行。请完全基于这些事实数据进行推理，**切勿捏造**不存在的代码结构。

### ✅ [参考场景] 完整调用链数据
=========================================
{trace_data}
=========================================

---

## 🎯 开发分析要求

请深度分析上述场景的完整执行链，并基于此说明如何实现新功能：

1. **Hook 点（切入点）识别**：
   - 根据新功能需求，分析应该在现有流程的**哪一个确切步骤**进行修改或扩展。
   - 精确指定代码插入的文件、函数名和位置。
2. **逻辑复用分析**：
   - 当前调用链中的哪些现有函数或模块可以直接被复用？
3. **并发安全**：
   - 评估添加新功能是否会破坏当前的执行逻辑（如死锁、可见性失效、资源竞争等）。

---

## ⚠️ 重要约束

- **仅基于事实**：分析必须仅基于提供的调用链数据。
- **完整代码**：在提供修改后的代码时，你**必须提供完整的类或完整的方法代码**。严禁使用 `...` 省略原有逻辑，以确保代码可以直接复制并运行。
- **代码精度**：必须明确指出正在修改的**文件名**和**函数名**。

---

## 📋 输出格式要求

请在提供指导方案时严格遵守以下模板：

# 新功能开发指导方案

## 1. 核心思路
[简要解释如何利用现有架构来实现新功能]

## 2. 关键切入点 (在哪里修改)
- **文件**：[具体文件名]
- **函数**：[具体函数名]
- **理由**：[解释为什么选择这个位置]

## 3. 代码实现 (如何修改)
[使用 Markdown 代码块提供完整的修改后代码，并在新增/修改的部分添加醒目的注释，如 `// [Added]` 或 `// [Modified]`]

## 4. 潜在风险与注意事项
[列出开发过程中需要注意的副作用、并发隐患或性能问题]

## 5. 需要修改的文件（机器可读总结）

总结基于上述关键切入点**所有**需要修改的文件。此部分用于自动化解析，因此必须严格遵守以下规则：

- 将列表包含在下方所示的两个精确标记行之间。
- 每行一个文件路径，该行不能有其他任何内容。
- **仅输出原始文件路径**。不要添加项目符号（`-`, `*`）、编号（`1.`）、反引号、引号、注释、描述或尾随标点符号。
- 使用关键切入点中出现的精确路径（优先使用追踪数据中可用的最完整的相对路径）。
- 不要包含重复项。不要包含仅被引用但不需要修改的文件。
- 如果不需要修改任何文件，请输出仅包含 `NONE` 的单行。

输出格式（不要更改标记行）：

<!-- FILES_TO_MODIFY_START -->
path/to/first/file.ext
path/to/second/file.ext
<!-- FILES_TO_MODIFY_END -->
"""

# ==========================================
# 2. 交互式引导逻辑
# ==========================================
def generate_prompt(cli_file_path=None):
    print("="*50)
    print("🚀 AI 二次开发 Prompt 自动生成器")
    print("="*50)
    print("请根据提示输入所需信息（直接按回车跳过选填项）\n")

    # 1. 收集目标功能
    target_feature = input("🎯 1. 请输入【目标新功能】（例如：添加一个基于 Semaphore 的测试场景）：\n> ").strip()
    if not target_feature:
        target_feature = "[未提供具体需求，请 AI 分析当前场景中可能的扩展点]"

    # 2. 收集补充说明
    additional_info = input("\n💬 2. 请输入【补充说明】（选填，例如：必须使用 JDK 8，不允许引入外部依赖）：\n> ").strip()
    if not additional_info:
        additional_info = "无特殊补充说明。请遵循通用的最佳实践。"

    # 3. 读取追踪数据文件
    trace_data = ""
    while True:
        if cli_file_path:
            file_path = cli_file_path
            print(f"\n📁 3. 使用参数传入的调用链数据文件：{file_path}")
            cli_file_path = None
        else:
            file_path = input("\n📁 3. 请输入【调用链数据文件】的路径（例如：final-output-calltree.md）：\n> ").strip()
            # 移除可能存在的引号（从终端拖拽文件时常见）
            file_path = file_path.strip('\'"')
        
        if not file_path:
            print("❌ 文件路径不能为空，请重新输入！")
            continue
            
        if not os.path.exists(file_path):
            print(f"❌ 找不到文件：{file_path}。请检查路径是否正确！")
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                trace_data = f.read()
            print("✅ 成功加载调用链数据！")
            break
        except Exception as e:
            print(f"❌ 读取文件失败：{e}")
            continue

    # 4. 组装最终 Prompt
    final_prompt = PROMPT_TEMPLATE.format(
        target_feature=target_feature,
        additional_info=additional_info,
        trace_data=trace_data
    )

    # 5. 写入文件
    # [修改] 统一输出文件名以便下游处理
    output_filename = "AI_Task_Prompt.md"
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_prompt)
        print("\n" + "="*50)
        print(f"🎉 成功！完整的 Prompt 已生成并保存在当前目录下：{output_filename}")
        print("👉 你现在可以直接打开此文件，复制所有内容并发送给 AI！")
        print("="*50)
    except Exception as e:
        print(f"\n❌ 保存文件失败：{e}")

def main():
    cli_file_path = sys.argv[1] if len(sys.argv) > 1 else None
    generate_prompt(cli_file_path)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 用户取消了操作。")
        sys.exit(0)