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

### 🚀 Getting Started

_Coming soon — installation and quickstart instructions._

### 📄 License

This project is licensed under the [Apache License 2.0](LICENSE).

### 🔗 Related Work

- Original POC: [scenario-based-runtime-context-for-ai](https://github.com/zhonghuajin/scenario-based-runtime-context-for-ai) — The foundational proof-of-concept that inspired this production implementation

### 📧 Contact

For questions or discussions, please open an issue in this repository.