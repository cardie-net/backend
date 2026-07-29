# Agent Directives & Project Standards

## 1. Code Style & Formatting Rules

- **Formatting & Types:**
  - Use double quotes (`"`) everywhere for strings; avoid single quotes (`'`).
  - Apply explicit type hints where they make sense to keep contracts clear.
  - Keep docstrings short and concise (single-line) for non-trivial functions.
- **Comments & Spacing:**
  - Keep inline comments sparse—let clean code self-document.

## 2. Modularity & Architecture

- **Single Responsibility:** Keep modules and functions tightly focused. If a file starts creeping past ~250–300 lines, break it down into smaller sub-modules.
- **Decoupled Architecture:** Separate core business logic, data structures/models, and external APIs or CLI layers. Avoid high coupling.
- **Explicit Imports:** Never use wildcard imports (`from module import *`). Keep imports clean, sorted, and explicit.

## 3. Refactoring & Code Modifications

- **Inspect First:** Read existing definitions and types before modifying or extending existing features.
- **Incremental Changes:** Refactor in small, self-contained steps rather than rewriting entire modules from scratch.
- **Consistency:** Always match existing pattern choices and folder structures within the codebase.
