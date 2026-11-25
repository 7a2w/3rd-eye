Resume the 3rd-eye UI redo in 7a2w/3rd-eye. main was 63d8647 at handoff (README only).
1. Clone or cd into 3rd-eye, then: git fetch origin && git checkout claude/great-keller-ig0520
   `git branch --show-current` must print claude/great-keller-ig0520. Only then read
   .ai/handoffs/3rd-eye-ui-redo.md
2. Blocker: the 3rd-eye source code was never pushed. It is on the user's laptop
   (GBs_T14s). If you are running locally in that folder, the code is right here: commit it first.
   In a cloud session with no code, ask the user to push it.
3. First action: confirm the code is present (git ls-tree -r --name-only HEAD), then
   restyle it like 7a2w/Conquer-Terminal (web/, docs/design/design_tokens.json),
   add an iPhone PWA layout, and run a security suite (see the handoff for the steps).
Recommended model: opus. It's a multi-part UI rebuild on an unseen codebase.
