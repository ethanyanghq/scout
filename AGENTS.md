# Coding Guidelines

Write code that a human can read and understand quickly. These rules are strong defaults: follow them unless doing so would clearly make the code harder to understand, and note any exception in your summary.

**The guiding question:** Could a new teammate understand what this code does and why, without running it or asking you?

## This repository

If a value is missing, find it in the README, Makefile, or package configuration rather than guessing.

- Build: `uv sync` (Python service), `cd bridge && bun install` (Photon bridge), `cd landing && bun install` (landing page)
- Fast tests: `uv run pytest`, `cd bridge && bun test` and `cd landing && bun run test`
- E2E tests: `cd bridge && bun run e2e` plays a console script for each critical user journey (`bridge/e2e/`; needs uv, and `ANTHROPIC_API_KEY` in `.env`). To try a conversation step by step without phones, use the developer console: `cd bridge && bun run devchat` (see [DEVELOPING.md](DEVELOPING.md)).
- Lint: `uv run ruff check src tests`, `cd bridge && bun run typecheck` and `cd landing && bun run typecheck`
- Format: `uv run ruff format src tests`
- Critical user journeys: scout joins a chat and introduces itself; members share preferences and scout confirms them; scout posts the summary and destination poll; members vote by number and scout announces the winner.

Formatting is the formatter's job. Run it; don't hand-format code.

### Group chats and real messages

- Read [DEVELOPING.md](DEVELOPING.md) before changing `bridge/` or testing a conversation. Its "What exists today" table says which developer tools are built. Never run a planned command (such as the demo group commands) as if it exists.
- A Linq or Photon line sends real iMessages to real people. Don't send messages, create chats, add contacts or change webhooks, whether through the `linq` CLI, Linq's API or a bridge connected to a real line, unless the user asked for that action. Test with the developer console, `scout-simulate`, `curl` or the test suites instead.
- Never commit real phone numbers, API keys, `.env` files or `scout.db`. Replace the numbers in recorded Linq webhooks with 555 numbers before committing them.
- When a pull request ships a tool from [scout-group-chat-plan.md](scout-group-chat-plan.md), it also checks the item off there and updates DEVELOPING.md.

## 1. Names reveal intent

- Name things by what they mean in the problem domain, not how they are implemented (`overdueInvoices`, not `filteredList`).
- If a name needs a comment to explain it, choose a better name.
- Avoid vague words like `data`, `info`, `manager`, `handler`, `util`, `process`, `temp`, and `obj` unless nothing more specific is true.
- Functions are verbs (`calculateTax`); types and classes are nouns (`TaxRate`); booleans read as yes/no questions (`isExpired`, `hasAccess`).
- Scale name length to scope: a loop index can be `i`; a module-level value needs a full, descriptive name.
- Use one word per concept across the codebase. Don't mix `fetch`, `get`, and `retrieve` for the same idea.
- Replace magic numbers and strings with named constants (`MAX_LOGIN_ATTEMPTS`, not `5`).

## 2. Functions do one thing

- A function should do one thing at one level of abstraction. Test: you can describe it in one sentence without using "and".
- Don't mix high-level steps with low-level details in the same function. Extract the details into well-named helpers so the top-level function reads like a summary.
- Prefer functions short enough to understand at a glance. Length is a symptom; mixed responsibilities are the actual problem.
- Keep nesting shallow. Use guard clauses and early returns instead of deep `if`/`else` pyramids.
- Order code top-down: a function's callers appear before its helpers, so the file reads like a narrative.
- Keep parameters few (three or fewer as a default). Group related values into an object or type.
- Avoid boolean flag parameters; they mean the function does two things. Split it into two functions.
- No hidden side effects. A function either changes state or returns information, not both. `getUser` must not also update a cache or write to a log the caller depends on.
- Don't over-fragment. A helper that is used once and has no more meaningful name than its body should stay inline. If following a simple flow requires jumping through many tiny functions, consolidate.

## 3. Modules and classes are cohesive

- Give each module or class one responsibility: one reason to change. If you can't name it without "and" or a generic word like `Manager` or `Helper`, split it.
- Put code where its concept lives. Avoid catch-all `utils`, `helpers`, or `common` modules.
- Keep things that change together close together, and keep data next to the behavior that operates on it.
- Expose a small public surface and keep internals private. Callers should need to know *what* a module does, not *how*.
- Don't reach through objects to get what you need (`order.getCustomer().getAddress().getCity()`). Ask the nearest collaborator directly, or pass in what's needed.

## 4. Keep it simple

- Solve the problem in front of you. Don't build for hypothetical future requirements.
- Don't introduce an abstraction (interface, base class, factory, generic parameter, plugin point, config option) without a present, concrete need for it.
- Tolerate a little duplication before extracting. Extract shared code when the cases genuinely represent the same concept, not merely similar-looking lines. The wrong abstraction costs more than duplication.
- Prefer plain functions and simple data structures over class hierarchies and design patterns.
- Don't add a dependency without a clear need. Prefer the standard library and dependencies the project already uses.
- Choose the solution with the fewest moving parts that a reader must hold in their head.

## 5. Comments explain why

- Code shows *what* and *how*; comments explain *why*: intent, constraints, trade-offs, non-obvious decisions, and workarounds (with a link or reason).
- Don't write comments that restate the code.
- Don't leave commented-out code or change-log comments ("changed X to Y"). Version control handles history.
- Keep comments accurate. A wrong comment is worse than none; update or delete comments when code changes.

## 6. Handle errors clearly

- Never silently swallow errors. Handle them where something useful can be done; otherwise let them propagate.
- Error messages state what went wrong and include the context needed to diagnose it.
- Keep error handling from burying the main logic; extract it when the happy path becomes hard to follow.

## 7. Tests verify behavior

- Test what the code does, not how it does it. Assert observable outcomes, not internal calls. Mock only true external boundaries (third-party APIs, payment providers, the clock).
- Every user-visible change is covered by a test of that behavior. When a change touches a critical user journey, add or update its E2E test.
- Use fast, focused tests for dense logic (rules, calculations, parsing), and run them while you iterate.
- Every bug fix includes a test that fails without the fix.
- Never delete, skip, or weaken a test to make it pass. If a test is wrong, say so and explain why.
- Name tests after the behavior, in domain language (`rejects payment when card is expired`). Test one behavior per test.
- Each test sets up its own data and passes regardless of order. Wait for conditions, never for fixed time.

## 8. Stay in scope

- Change only what the task requires. Don't rename, reformat, or restructure code you are only passing through.
- Small cleanups inside code you are already changing are fine. Suggest anything broader in your summary instead of doing it.
- Apply these guidelines to code you write or modify; they are not a mandate to rewrite existing code.

## 9. Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <description>

<optional body>

<optional footer>
```

- Use one of these types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `style`, `build`, `ci`, `chore`, `revert`.
- Write the description in the imperative mood, in lowercase, with no trailing period: `fix(auth): reject expired refresh tokens`.
- Mark breaking changes with `!` after the type or scope (`feat(api)!: ...`), and explain them in a `BREAKING CHANGE:` footer.
- Use the body to explain *why* the change was made, not to repeat the diff.
- Make each commit one logical change. Don't mix a refactor with a behavior change; commit them separately.
- Commit on `main` by default. Don't create a branch unless the teammate asks for one or there's a clear, strong reason, such as work that must stay out of `main` while it's reviewed.
- Don't attribute commits to an AI agent. Claude, Codex and other coding agents add no `Co-Authored-By` trailer for themselves and no "Generated with" line. The teammate who asked for the change is the author.

## Before you finish

- Run the formatter, linter, and tests. Fix failures; don't silence them.
- Reread your diff as a reviewer seeing it for the first time. Does it contain only what the task requires?
- Check new names, functions, and modules: is each specific, honest, and responsible for one thing?
- Check new abstractions and dependencies: is each needed now, or only "someday"?
- Remove dead code, debug output, and unused imports.
- Make sure each commit is one logical change with a Conventional Commits message.
