# Handoff: 3rd-eye UI redo + iPhone version + security suite (2026-11-25)

## Status
- DONE: Identified the design reference. `7a2w/Conquer-Terminal` (private) at `dccfbb5`
  holds the look to copy: `web/` (Vite + React/TS), `docs/design/design_tokens.json`,
  `docs/design/brand/` (Summit logo, viridis palette, sharp corners).
- NOT STARTED: Restyling 3rd-eye's UI. **Blocked: the 3rd-eye source code is not on GitHub.**
- NOT STARTED: iPhone version.
- NOT STARTED: Security suite.

## What the user asked for (verbatim intent)
1. "redo the ui similar to the conquer terminal"
2. "make an iphone version"
3. "run a security suite"

## Decisions
- iPhone version = **mobile web / PWA** (installable on the iOS home screen), not native
  SwiftUI or Capacitor. Why: the user picked it; it can be built and tested in Linux.
- Commits go on branch `claude/great-keller-ig0520` in `7a2w/3rd-eye`.

## Facts checked on 2026-11-25 (re-verify before you rely on them)
- `7a2w/3rd-eye` `main` = `63d8647`, containing only `README.md` ("# 3rd-eye").
  Re-verify: `git ls-remote https://github.com/7a2w/3rd-eye`
- `7a2w/other` is an empty repo with no commits.
- Nothing in Conquer-Terminal, past sessions or GitHub code search mentions "3rd-eye".
  What 3rd-eye actually does is **unknown**. Read the code once it lands.
- The 3rd-eye code lives only on the user's Windows laptop, `GBs_T14s`. Its two
  Remote Control folders ("Critical Line" and "Conquer-main-strat-fix-download") are
  listed but cannot be opened from a cloud session (reason "not_available"; the
  Claude app there likely needs updating). Neither is known to be 3rd-eye.

## Blockers
- **No source code.** Unblocked by either:
  (a) the user pushing the 3rd-eye code to `7a2w/3rd-eye`, or
  (b) the user running `claude remote-control` in the 3rd-eye folder on the laptop and
      continuing there.
  The user said they need it "local to add the file", so (b) is the likely route.

## Next action
1. Run `git fetch origin && git ls-tree -r --name-only origin/main`. If only
   `README.md` is listed, the code still isn't there: ask the user to push it, or
   work from their local folder.
2. Once the code is present: find the UI entry point and framework, then copy
   Conquer-Terminal's tokens (`docs/design/design_tokens.json`) and shell components
   (`web/src/components/shell/`, `web/src/lib/`).
3. iPhone: add a responsive layout, `manifest.webmanifest`, apple-touch-icon,
   safe-area insets and `viewport-fit=cover`. Test with Playwright's
   `devices['iPhone 15']`.
4. Security: run `/security-review`, `npm audit` / `pip-audit` (whichever applies),
   `gitleaks` or another secret scan, and `semgrep --config auto` if it is
   available. Write the results to `reports/security-<date>.md`.

## Verification
- Nothing has been built or tested yet. There is no code to test.

## Skills Review
- ⚠️ handoff: the session started from "read the handoff", but no handoff existed
  anywhere (repo, memory or past sessions). In future, write handoffs into the repo
  at `.ai/handoffs/` so they survive.
