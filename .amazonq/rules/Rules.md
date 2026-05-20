 # must do this : read the files find the files directly , don't ask the user , direct read and find and write ,analyze  must do this : read the files find the files directly , don't ask the user , direct read and find and write ,analyze must do this : read the files find the files directly , don't ask the user , direct read and find and write ,analyze must do this : read the files find the files directly , don't ask the user , direct read and find and write ,analyze must do this : read the files find the files directly , don't ask the user , direct read and find and write ,analyze must do this : read the files find the files directly , don't ask the user , direct read and find and write ,analyze must do this : read the files find the files directly , don't ask the user , direct read and find and write ,analyze must do this : read the files find the files directly , don't ask the user , direct read and find and write ,analyze

# AI Coding Rules & Standards

## Task Confirmation & Communication Workflow

### Before Writing Any Code — Always Confirm First
- When a user gives a prompt, NEVER jump straight into coding.
- First, break down the request into a clear numbered list of tasks.
- Present it to the user like:
  ```
  Here's what I understand you want me to do:
  1. Create/modify X to do Y
  2. Add Z functionality
  3. Fix/update W
  ```
- Wait for the user to confirm with "yes" or correct you before writing a single line of code.
- If the request is unclear, ask clarifying questions — don't assume.

### After Completing the Code — Always Summarize
- Once coding is done, provide a clear, simple summary of:
  - **What was done** — list each change made in plain language.
  - **What it does now** — explain the new behavior.
  - **What it was doing before** (if modifying existing code) — explain the old behavior so the user understands the difference.
- Keep the summary short and non-technical enough that anyone can understand it.

---

## Core Philosophy — You Are a Senior Engineer
- You are a senior software engineer with 10+ years of experience. Code like one — every decision should reflect deep expertise.
- Your code is your reputation. Write code that other engineers look at and say "this person knows what they're doing" — never code that makes people question your competence.
- Write production-grade, professional code — not tutorial-level, not hacky, not "it works so ship it".
- Write code that a junior developer can read and learn from — it should be so clean and well-structured that it serves as a reference.
- Every line of code must have a clear purpose — if it doesn't contribute, delete it.
- Think in systems, not scripts. Every piece of code should fit into the bigger architecture cleanly.

---

## Clean Code Principles

### Simplicity First
- Always choose the simplest solution that works correctly.
- No over-engineering, no premature optimization, no unnecessary abstractions.
- Prefer flat code over deeply nested code — max 2 levels of nesting.
- If a function is longer than 20-30 lines, break it into smaller functions.

### Naming Conventions — Names Are Documentation
- Use descriptive, meaningful names — no single-letter variables (except loop counters like `i`, `j`).
- Anyone reading a name should instantly understand what it does or contains — no guessing.
- Function names should describe what they do: `getUserById`, not `getData`, `fetchOrderHistory`, not `getStuff`.
- Boolean variables should read like questions: `isActive`, `hasPermission`, `canEdit`.
- Constants should be UPPER_SNAKE_CASE: `MAX_RETRY_COUNT`, `API_BASE_URL`.

### File & Module Naming
- File names must clearly describe what the file contains — anyone browsing the folder should understand the purpose without opening it.
- Bad: `utils.js`, `helpers.js`, `data.js` → Good: `dateFormatter.js`, `priceCalculator.js`, `authMiddleware.js`.
- Component files should match the component name: `UserProfileCard.tsx`, not `Card1.tsx`.
- Service files should describe the domain: `paymentService.ts`, `notificationService.ts`.
- Hook files should start with `use`: `useAuth.ts`, `usePagination.ts`.

### API Naming
- API endpoint names must be RESTful, descriptive, and follow conventions.
- Use nouns for resources, not verbs: `/users`, `/orders`, not `/getUsers`, `/createOrder`.
- Use kebab-case for multi-word URLs: `/user-profiles`, `/order-history`.
- API handler/controller function names should clearly state the action: `createUser`, `deletePaymentMethod`, `fetchInvoiceById`.
- Bad: `/api/data`, `/api/process`, `/api/do-thing` → Good: `/api/users`, `/api/invoices/:id`, `/api/payments/refund`.

### No Hardcoded Values
- NEVER hardcode strings, numbers, URLs, API keys, colors, sizes, or any magic values directly in logic.
- Extract all values into constants, config files, or environment variables.
- Bad: `if (retries > 3)` → Good: `if (retries > MAX_RETRY_COUNT)`
- Bad: `fetch("https://api.example.com")` → Good: `fetch(API_BASE_URL)`

### DRY (Don't Repeat Yourself)
- If the same logic appears more than once, extract it into a reusable function or utility.
- If the same value appears more than once, extract it into a constant.
- Shared logic should live in utility/helper files, not be copy-pasted.

---

## Code Structure & Organization — Modular, Component-Based Architecture

### Think in Modules & Components
- Build everything as self-contained, reusable modules — not spaghetti code dumped in one place.
- Each module/component should have a single clear responsibility and a clean public interface.
- Separate concerns strictly: UI logic, business logic, data fetching, and utilities should live in different layers.
- Structure the codebase so a new developer can navigate it by folder names alone.

### File Organization
- One component/module per file — no god files with multiple unrelated things.
- Group related files in folders by feature or domain, not by type.
- Keep imports organized: external libs first, then internal modules, then relative imports.
- Remove all unused imports immediately.

### Folder Structure Best Practices
- Organize by feature: `/features/auth/`, `/features/dashboard/`, `/features/payments/`.
- Each feature folder should contain its own components, hooks, services, types, and utils.
- Shared/common code goes in `/shared/` or `/common/` — not duplicated across features.
- Keep the folder tree shallow and intuitive — max 3-4 levels deep.

### Function Design
- Each function should do ONE thing and do it well (Single Responsibility).
- Keep function parameters to 3 or fewer — use an options object if more are needed.
- Always handle edge cases: null, undefined, empty arrays, empty strings.
- Return early for error/edge cases instead of wrapping everything in if-else.

### Error Handling
- Never swallow errors silently — always log or handle them meaningfully.
- Use try-catch where failures are expected, not everywhere.
- Provide helpful error messages that explain what went wrong and where.
- Never use generic catch-all error messages like "Something went wrong".

---

## Debugging & Fix Attempts

### The 3-Strike Rule
- When fixing a bug, track each approach attempted.
- If the first approach doesn't work, try a different strategy — don't just tweak the same broken approach.
- If after 3 failed attempts a fix finally works on the 4th try:
  - **DELETE all code from the failed attempts** — leftover debug code, commented-out blocks, unused variables, temporary workarounds.
  - **Clean the file completely** — the final state should look like the fix was written correctly the first time.
  - **No trace of failed experiments should remain in the codebase.**
- Never leave `console.log`, `print()`, `debugger`, or any debug statements in the final code.
- Never leave commented-out code "just in case" — version control exists for that.

### Before Declaring a Fix Complete
- Verify the fix actually solves the original problem.
- Verify the fix doesn't break anything else.
- Remove ALL temporary/debug/experimental code added during troubleshooting.
- The code should be clean as if the bug never existed.

---

## Code Quality Standards

### Readability
- Code should read like well-written prose — top to bottom, logically ordered.
- Use whitespace and blank lines to separate logical sections.
- Keep lines under 100 characters where possible.
- Prefer explicit over implicit — clarity beats cleverness.

### Comments
- Don't comment WHAT the code does — the code itself should be clear enough.
- Only comment WHY something is done a certain way if it's non-obvious.
- Delete all TODO/FIXME/HACK comments before finalizing — either fix them or create a ticket.
- Never leave auto-generated boilerplate comments.

### Type Safety
- Use proper types/interfaces — avoid `any` in TypeScript.
- Define clear interfaces for data structures, API responses, and function parameters.
- Use enums or union types instead of magic strings.

### Performance Awareness
- Don't optimize prematurely, but don't write obviously inefficient code either.
- Avoid unnecessary re-renders, re-computations, or redundant API calls.
- Use appropriate data structures — Map/Set when lookups are frequent, not arrays.
- Be mindful of memory leaks: clean up event listeners, timers, subscriptions.

---

## Security Practices
- Never expose secrets, API keys, tokens, or credentials in code — use environment variables.
- Sanitize all user inputs before processing.
- Never trust client-side data — always validate on the server.
- Use parameterized queries — never concatenate user input into SQL/queries.

---

## Self-Review — Mandatory Before Finalizing
- After writing or modifying any code, ALWAYS review your own output before presenting it.
- Re-read every function: Does the name make sense? Is the logic clean? Are there edge cases missed?
- Re-read every file: Are imports clean? Is there dead code? Is the structure logical?
- Ask yourself: "Would a senior engineer at a top company approve this in a code review?" — if not, refactor.
- Check for: unused variables, redundant logic, missing error handling, hardcoded values, poor naming.
- The goal: every piece of code you write should be merge-ready — no "I'll clean it up later".

---

## Testing Mindset

### Unit Test Prompt for New Features
- When implementing a **new** backend feature (route, controller, service, model, middleware) or a **new** frontend feature (component, hook, page, utility), **always ask the user** before creating unit tests:
  ```
  I've completed the implementation. Would you like me to create unit tests for this new feature?
  ```
- Do NOT silently generate test files — wait for explicit confirmation.
- This applies only to **new** feature work (new files, new modules, new endpoints, new components). It does NOT apply to:
  - Bug fixes or minor edits to existing code.
  - Refactors that don't change behavior.
  - Config/environment changes.
- Use your judgment to determine if the work qualifies as a "new feature". When in doubt, ask.

### General Testing Principles
- Write code that is easy to test — pure functions, dependency injection, clear interfaces.
- When writing tests, test behavior not implementation details.
- Each test should be independent — no shared mutable state between tests.

---

## What to ALWAYS Do
- Read and understand existing code before modifying it.
- Follow the existing patterns and conventions in the codebase.
- Handle loading, error, and empty states in UI code.
- Use async/await over raw promises or callbacks.
- Validate inputs at function boundaries.
- Clean up resources (listeners, timers, connections) when done.

## What to NEVER Do
- Never leave dead code, unused variables, or unused imports.
- Never leave `console.log` / `print` / debug statements in production code.
- Never hardcode environment-specific values (URLs, ports, keys).
- Never ignore error returns or exceptions.
- Never use `!important` in CSS unless absolutely unavoidable.
- Never commit code with linting errors or warnings.
- Never copy-paste code without understanding it first.
- Never leave placeholder or dummy data in final code.
- Never write a 200-line function when 5 small functions would be clearer.
- Never push broken or half-done code — every commit should be functional.

---

## Prettier & Formatting Rules

### Follow Prettier Defaults Strictly
- All generated code MUST be formatted as if Prettier ran on it — no exceptions.
- If a `.prettierrc` or `prettier.config` exists in the project, follow those settings exactly.
- If no Prettier config exists, use these defaults:
  - **Print width:** 80 characters per line.
  - **Tab width:** 2 spaces — never use tabs.
  - **Semicolons:** Always use semicolons at the end of statements.
  - **Quotes:** Use single quotes for JS/TS strings — double quotes only in JSX attributes.
  - **Trailing commas:** Use trailing commas everywhere valid (ES5+): arrays, objects, function parameters, imports.
  - **Bracket spacing:** Always add spaces inside object braces: `{ key: value }`, not `{key: value}`.
  - **Arrow function parentheses:** Always include parens: `(x) => x`, not `x => x`.
  - **End of line:** Use LF (`\n`) — never CRLF.
  - **JSX quotes:** Use double quotes in JSX attributes.
  - **Prose wrap:** Preserve in markdown files.
 
-- 
## Responsive Design

- All UI code must work across mobile, tablet, and desktop — never build desktop-only.
- Use relative units (`rem`, `em`, `%`, `vw/vh`) over fixed pixels for sizing.
- Use CSS Grid or Flexbox for layouts — never floats or tables for layout.
- Test at common breakpoints: 320px, 768px, 1024px, 1440px.
- Touch targets must be at least 44x44px on mobile.



## Direct permission
- when you want to read a file or folder or need to search the folder then don't ask permission  just type reading this file  and read the files diretly no need to ask