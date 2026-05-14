#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# ==========================================
# 1. 定义 Prompt 模板 (用于代码审计)
# ==========================================
PROMPT_TEMPLATE = """# 基于零噪音执行轨迹的代码审计与漏洞挖掘任务

你是一位资深软件安全审计专家和 Java 并发编程大师。请根据提供给你的真实系统运行时的零噪音代码执行轨迹数据，帮我进行深度的代码审计，以挖掘潜在的并发漏洞、逻辑缺陷或安全问题。

---

## 📋 审计任务定义

**🎯 重点审计方向**：
{audit_focus}

**💬 补充说明（选填）**：
{additional_info}

---

## 🔍 场景调用链与运行时状态数据

以下数据来自真实系统运行时的追踪日志，包含了该场景下**绝对真实且无噪音**的执行上下文：
1. **Trace Sequence**：线程执行的基本代码块 (Basic Block) 的线性序列。
2. **Call Tree**：包含方法签名、源文件、执行的 Block ID，以及**经过修剪（仅包含实际执行部分）的源码**。
3. **Happens-Before**：线程之间的同步边（左侧操作对右侧操作的内存可见性）。
4. **Data Races**：未同步的并发共享变量访问冲突（读写或写写冲突）。
5. **Taint Flows**：跨线程或线程内的数据/污点传播路径。

**⚠️ 重要前提**：数据中仅包含**实际执行过**的代码。如果某段代码没有出现，说明它在该场景下绝对没有执行。请完全基于这些事实数据进行推理，**切勿捏造**不存在的代码逻辑。

### ✅ [审计目标数据] 完整执行轨迹与并发状态
=========================================
{trace_data}
=========================================

---

## 🎯 深度审计与分析要求

请深度分析上述场景的完整执行链，特别是 `Data Races` 和 `Taint Flows` 部分，完成以下审计任务：

1. **漏洞/缺陷识别**：
   - 结合 Data Races 数据，识别哪些共享变量在并发访问时缺乏适当的同步机制（例如：未加锁、错误使用 volatile 等）。
   - 结合 Happens-Before 关系，分析是否存在内存可见性问题或指令重排导致的潜在 Bug。
2. **根因分析**：
   - 追踪 Taint Flows，解释问题是如何沿着调用链和跨线程传播的。
   - 精确指出引发问题的源文件、类名和具体函数。
3. **修复方案设计**：
   - 基于现有代码架构，提供修复该漏洞的最佳实践代码。
   - 修复方案必须保证并发安全（无死锁、保证可见性、解决数据竞争），并尽量降低性能开销。

---

## 📋 审计报告输出格式要求

请严格按照以下模板输出你的代码审计报告：

# 🛡️ 代码审计与修复报告

## 1. 漏洞/缺陷摘要
[用一两句话简述发现的核心问题，例如：“发现 `SyncTest` 类中 `sharedData` 存在多线程未同步读写，具有严重的数据竞争和内存可见性漏洞”]

## 2. 详细缺陷分析 (根因)
- **风险等级**：[高/中/低]
- **缺陷类型**：[例如：数据竞争 / 内存可见性失效 / 死锁风险]
- **触发路径**：[结合 Trace 数据和 Taint Flows，详细描述漏洞在多线程间是如何被触发的]
- **受影响位置**：[具体文件名和函数名]

## 3. 修复代码实现
[提供完整的修复后代码。**必须提供完整的类或完整的方法代码**，绝不能使用 `...` 省略现有逻辑，确保代码可以直接复制执行。在修改或新增的部分添加醒目的注释，例如 `// 🛠️ [修复：添加同步锁以解决数据竞争]`]

## 4. 修复原理分析与回归建议
[解释为什么此修复是有效的（例如引入了哪些 Happens-Before 规则），以及在回归测试中需要注意什么]
"""

# ==========================================
# 2. 交互式引导逻辑
# ==========================================


def generate_prompt(cli_file_path=None):
    print("="*50)
    print("🛡️  AI 零噪音代码审计 Prompt 生成器")
    print("="*50)
    print("请根据提示输入审计任务信息（直接按回车跳过选填项并使用默认值）\n")

    # 1. 收集审计重点
    audit_focus = input(
        "🎯 1. 请输入【重点审计方向】（例如：重点排查数据竞争、死锁或跨线程污点传播）：\n> ").strip()
    if not audit_focus:
        audit_focus = "全面排查并发安全漏洞（数据竞争）、内存可见性问题（缺失 Happens-Before）以及潜在的业务逻辑缺陷。"

    # 2. 收集补充说明
    additional_info = input(
        "\n💬 2. 请输入【补充说明】（选填，例如：修复时只能使用 JDK 原生库，不能改变原有方法签名）：\n> ").strip()
    if not additional_info:
        additional_info = "无特殊补充限制。请遵循 Java 并发编程的最佳实践（例如：优先使用 java.util.concurrent 包下的工具）。"

    # 3. 读取追踪数据文件
    trace_data = ""
    while True:
        if cli_file_path:
            file_path = cli_file_path
            print(f"\n📁 3. 使用参数传入的执行轨迹数据文件：{file_path}")
            cli_file_path = None  # 失败时重置
        else:
            file_path = input(
                "\n📁 3. 请输入【执行轨迹数据文件】的路径（例如：final-output-combined.md）：\n> ").strip()
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
            print("✅ 成功加载执行轨迹与并发状态数据！")
            break
        except Exception as e:
            print(f"❌ 读取文件失败：{e}")
            continue

    # 4. 组装最终 Prompt
    final_prompt = PROMPT_TEMPLATE.format(
        audit_focus=audit_focus,
        additional_info=additional_info,
        trace_data=trace_data
    )

    # 5. 写入文件
    output_filename = "AI_Task_Prompt.md"
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_prompt)
        print("\n" + "="*50)
        print(f"🎉 成功！完整的代码审计 Prompt 已生成并保存在当前目录下：{output_filename}")
        print("👉 你现在可以直接打开此文件，复制所有内容并发送给大语言模型（如 Claude 3.5 Sonnet / GPT-4o）进行深度审计！")
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
