# 0005. Structured CLI Harness with Command Registry and View Separation

## Context
As the MusicMatch agent and tooling ecosystem expand, relying on an ad-hoc while-loop inside `cli.py` with hardcoded string checks creates tight coupling between presentation, system control, and AI reasoning. Modern agent harnesses (such as Claude Code, Aider, and Antigravity) cleanly separate administrative system commands (`/help`, `/status`, `/scan`, `/exit`) from natural language agent prompts, while decoupling terminal rendering from the event loop. Furthermore, as an educational codebase, the architecture must clearly illustrate foundational software design patterns (Command Pattern, Single Responsibility Principle, and Event Loop boundaries).

## Decision
1. **Separation of Presentation (UI)**: Introduce `ConsoleUI` (`musicmatch.ui.renderer`) responsible solely for terminal formatting, banners, observability logs, and tables.
2. **Command Pattern (`musicmatch.commands`)**: Implement a strongly-typed `Command` base class, `CommandContext`, and `CommandRegistry`. Slash commands (`/help`, `/status`, `/scan`, `/clear`, `/exit`) are registered as isolated objects.
3. **Ergonomic Exit Aliases**: Strictly restrict non-slash keyword aliases (`sair`, `exit`, `quit`, `q`) to the exit operation, ensuring all other system controls follow the explicit `/` convention.
4. **Interactive Harness Event Loop (`musicmatch.harness.loop`)**: Introduce `Harness` to manage the read-route-dispatch lifecycle, maintaining a resilient error boundary that prevents unhandled exceptions from terminating user sessions.
5. **Thin Bootstrap**: Reduce `musicmatch.cli` to a lightweight entrypoint that initializes and boots the harness.

## Consequences
- **Extensibility**: Adding new harness commands requires creating a new `Command` subclass and registering it, leaving the event loop untouched (Open/Closed Principle).
- **Testability**: UI, commands, and routing can be tested independently with mock contexts without launching a live terminal session or invoking Gemini.
- **Portability**: Transitioning to advanced terminal libraries (`rich`, `prompt_toolkit`, `Textual`) or graphical/web interfaces only requires swapping the UI renderer and event driver.
