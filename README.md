### ⚡ Why This Project Exists

**The Problem:** When AI analyzes code, it only sees static structure — files, symbols, and call graphs across the entire codebase. It cannot know which code paths _actually executed_ for a specific scenario. So it guesses. This guessing is hallucination — AI reasoning built on assumption rather than fact.

**The Problem in Legacy Systems:** This challenge is amplified in brownfield and legacy environments. The harder problem is not changing code, but understanding what the system actually does, why it behaves the way it does, and where change is safe. Static analysis alone cannot reliably answer these questions — but runtime evidence can.

**The Solution:** This project captures **runtime evidence** from real executions and uses it to build **zero-noise, scenario-specific code context** for AI. Instead of flooding the model with the whole codebase, it gives the model only what actually happened — making AI reasoning grounded in facts, not speculation.

_Note: The approach is particularly valuable for legacy systems, but applies equally to any scenario where understanding actual runtime behavior reduces risk and improves AI accuracy._

### Static Analysis vs. Runtime Evidence

| Traditional (Static Analysis) | This Project (Runtime Evidence) |
|---|---|
| **What AI sees** | Entire codebase — hundreds of files, most irrelevant to the scenario | Only the code paths that _actually executed_ for the specific scenario |
| **Context quality** | High noise, low relevance — AI must guess what matters | Zero noise, high relevance — every line in context actually ran |
| **AI reasoning** | Speculative: "This code might be related..." | Factual: "These are the exact paths that executed" |
| **Hallucination risk** | High — AI fills gaps with plausible-sounding but wrong answers | Low — AI reasons from verified runtime facts |

> **In short:** Runtime evidence turns AI from a guesser into a witness.

### 🔬 From POC to Production

This project originates from **[scenario-based-runtime-context-for-ai](https://github.com/zhonghuajin/scenario-based-runtime-context-for-ai)** — a proof-of-concept that demonstrated how runtime evidence can be captured and organized to build cleaner, scenario-specific code context for AI reasoning. The POC explored a simple but important question: _Can runtime evidence help construct more relevant context than static structure alone?_

**This project takes that concept into production.** We are engineering a robust, reusable toolkit designed specifically for real-world brownfield maintenance scenarios:

- **Legacy system maintenance** — Understand and safely modify codebases where documentation is sparse and original authors are gone
- **Secondary development** — Extend existing systems without breaking them, guided by actual runtime behavior
- **Bug fixing & troubleshooting** — Trace bugs through the exact execution paths that trigger them
- **Code modernization** — Identify what actually matters before refactoring or rewriting

### ⚙️ Key Differentiators

This project focuses on:

- **Scenario-first understanding** — Start from a concrete behavior, not from the whole system
- **Runtime-grounded relevance** — Use execution evidence to identify which code actually mattered
- **Context reduction** — Remove theoretically related but behaviorally irrelevant code
- **AI-oriented context building** — Organize context in a form that is easier for models to reason about

### ⚠️ Important Usage Notes

To ensure the accurate collection of runtime evidence and prevent conflicts, please adhere to the following guidelines:

1. **First-Time Initialization**  
   Before running the tool for the first time, you must initialize the environment. Run the initialization script by executing:
   ```bash
   python init.py
   ```

2. **No Manual Intervention During Execution**  
   While the tool is running, **do not manually modify any code** and **do not manually start or restart the project**. All code modifications, environment setups, and project executions must be handled entirely by this tool.

### 🚀 Getting Started

Follow these steps to set up and run the automated instrumentation and bug-fixing workflow.

#### 📋 Prerequisites

Before running the tool, ensure you have the following installed and configured:
- **Python 3.8+**
- **Java JDK** (required for instrumentation of Java-based target codebases)
- **Git** (installed and configured in your system path)
- **LLM API Credentials** (an active API key for your preferred LLM provider, e.g., OpenAI, Anthropic, or DeepSeek)

---

#### 🛠️ Step 1: Initialize the Environment

Before executing the workflow for the first time, you must run the initialization script to set up configurations, dependencies, and your LLM environment:

```bash
python init.py
```
*Follow the on-screen prompts to configure your LLM provider and save your API keys.*

---

#### 🏃 Step 2: Run the Workflow

Launch the interactive quickstart workflow by running `startup.py`:

```bash
python startup.py
```

##### Command-Line Options

You can customize the execution of the workflow using the following optional flags:

*   **`--pause`**: Enables manual pauses between workflow steps. This is highly recommended for first-time users who want to inspect the intermediate outputs (such as instrumented code, generated prompts, and logs) before proceeding to the next step.
    ```bash
    python startup.py --pause
    ```
*   **`--interactive-ip`**: Prompts you interactively to input target IP addresses. If omitted, the tool will automatically simulate pressing `Enter` to use default network configurations.
    ```bash
    python startup.py --interactive-ip
    ```

---

### 📄 License

This project is licensed under the [Apache License 2.0](LICENSE).

### 🔗 Related Work

- Original POC: [scenario-based-runtime-context-for-ai](https://github.com/zhonghuajin/scenario-based-runtime-context-for-ai) — The foundational proof-of-concept that inspired this production implementation

### 📧 Contact

For questions or discussions, please open an issue in this repository.
