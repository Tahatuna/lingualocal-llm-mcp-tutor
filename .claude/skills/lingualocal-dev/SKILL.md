---
name: lingualocal-dev
description: Engineering and QA rules for LinguaLocal (web app, Language Services, MCP server). Covers acceptance criteria before code, test design, the regression and retest workflow, LLM evaluation, the MCP tool contract, security, clean code, the code review checklist and how to report results. Use it for every change, bug fix or review in this repository.
---

# LinguaLocal: engineering and QA rules

Quality here means **a learner can trust what the app teaches**. Work is planned, built, tested and reviewed as one
flow. No step is skipped because a change "looks small". The test plan, test cases and defect log live in
[`docs/TESTING.md`](../../../docs/TESTING.md). This skill tells you how to use them.

| Part | Folder | Port |
|---|---|---|
| Web app + data | `/` (`index.html`, `app.js`, `chat.js`, `mouth.js`, `app.css`, `server.py`, `store.py`) | 8767 |
| Language Services API | `language-services/` (`server.py`, `services/`) | 8770 |
| MCP server | `language-services/mcp_server.py` (stdio, calls the API) | — |

---

## 1. Workflow: from request to accepted change

```
Request → acceptance criteria → test design → code → tests green → manual retest → review → report
              (Given/When/Then)    (cases + data)        (unit, contract) (running app)  (checklist)
```

1. **Write acceptance criteria first**, in Given/When/Then form, including at least one negative case. Add them to
   `docs/TESTING.md` §8 with an ID (`TC-<AREA>-NN`), a priority (P1/P2/P3) and the requirement they trace to (§7).
2. **Design the tests before the code** (§3). Decide what is automated and what is manual, and what data is needed.
3. **Implement** following the existing code (§6). Do not add a new pattern, framework or dependency without asking.
4. **Run the automated suites.** Both must be green.
5. **Retest in the running app** on macOS: restart the LaunchAgents, reload without cache, and run the affected manual
   cases. Check what the user *sees*; correct data with an unchanged screen is a failure.
6. **Review** your own change with the checklist in §8 before you call it done.
7. **Report** in the format in §9, including what was not verified.

## 2. Gates (all must hold)

| Gate | Pass condition |
|---|---|
| G1 Unit / integration / contract | `python3 -m unittest discover tests` and `cd language-services && .venv/bin/python -m unittest discover tests` pass with 0 failures. Skips are allowed only for the documented licensed fixture. |
| G2 Regression | Every bug fix adds a test that **fails on the old code** (run it before the fix and see it fail). If automation is impossible, add a manual case and a row in "Known test gaps". |
| G3 Manual E2E | The affected TC-* cases pass in Chrome on macOS against an isolated copy |
| G4 Responsive | New or changed UI at 320, 375, 768, 1280 and 1440 px, with overlay **and** classic scrollbars: `scrollWidth − clientWidth = 0`, no clipped text, no CSP errors in the console |
| G5 LLM evaluation | After a prompt or model change, run `tests/quality/run_translation.py`; triage every miss as paraphrase or defect; median ≤ 2 s |
| G6 Review | The §8 checklist passes |
| G7 Running copy | The LaunchAgents were restarted and the real URL serves the new code (check a changed line with `curl`) |

## 3. Test design rules

- **Cover the classes and the boundaries.** For every input check:
  - empty, whitespace only, the maximum, maximum + 1;
  - Turkish characters (`İ ı ş ğ ü ö ç`) and mixed case;
  - markup (`<b>`, `</saved>`) and control characters;
  - a very long single word.
- **Write a negative test for every guard**: a foreign `Host`, a missing `X-LL` header, a non-JSON body, an origin
  that is not allowed, path traversal, an unknown MCP tool, the service down, the model down.
- **Test states as transitions.** Quiz: start → question → answer → stop → score. Chats: create → rename → switch →
  delete. Test the edges: stop while no quiz is running, delete the active chat.
- **Use decision tables** when behaviour depends on several flags (language detection, **Say words**: word vs sentence,
  dictation, page restore).
- **Guess errors from history.** Re-run the cases behind past defects (§9 of the test plan) whenever you touch the
  same area.
- **One behaviour per test**, named as the expected behaviour (`test_translation_cuts_off_a_running_check`), with no
  sleeps where an event or a fake clock can be used.

### Test isolation (never broken)

- Tests never reach the network and never touch the user's data:
  - temporary `LL_DATA_DIR` and `LS_DATA_DIR`;
  - port 0;
  - the model and HTTP stubbed with `unittest.mock` or a stub server.
- Manual runs use an isolated copy (ports 8779/8781, a temporary data folder) and sample data. If a real-data check
  is ever needed, ask first, and afterwards say exactly what was added and offer to remove it.
- Licensed data (Oxford entries) is never committed. It is made locally by `tests/make_fixtures.py`.

## 4. Testing the local LLM

The model is not a source of truth. Test **our contract with it**, and measure its quality separately.

- **Unit level:** stub `llm.chat` / `llm.structured`. Assert that:
  - the prompt contains the source data;
  - malformed, empty, duplicate or unchanged outputs are **dropped**;
  - tags and markup in the output are stripped;
  - data reaches the prompt inside `<saved>…</saved>`, with `<` neutralised.
- **Evaluation level:** the golden set (`tests/quality/translation_set.json`) runs on the real model. Each miss is
  read and triaged. A key-word miss can be a correct paraphrase, but a grammar error or a meaning shift is a defect:
  log it (DEF-NN), even if it stays open as a known limitation.
- **Trusted sources first:**
  - meanings, Turkish, IPA, forms, *-ing/to* and examples come from the dictionaries, curated lists, lemminflect,
    wordfreq and Tatoeba;
  - the model only fills gaps, with the source text in its prompt, and the UI labels its output **AI**.
- **Code decides what code can check:** which quiz question is asked, which words are saved, and whether an answer is
  right are decided by code. The model only chats and explains. (DEF-01: the model quizzed a word that was never saved.)
- **Every prompt has a version hash in its cache key.** Changing a prompt must never serve old answers. Empty or
  failed outputs are never cached.
- **Model choice is a test decision:** compare candidates with `compare_models.py` on the same prompt. Accuracy beats
  speed for a learning app.

## 5. MCP server contract

The MCP tools are a public API for AI clients. Treat them like one.

- **Define before building:** tool name, description (what it returns and where the data comes from), JSON Schema
  for the input (`required`, limits, enums, `additionalProperties: false`), output shape, error behaviour,
  `annotations` (`readOnlyHint` etc.). Add the contract to the table in TESTING.md §8.9.
- **Validate input before any call** (type, emptiness, length, enums). Invalid input returns `isError: true` with a
  readable reason and never reaches the API.
- **Tool errors are not protocol errors.** A failure of the service or of the input → a result with `isError: true`.
  An unknown tool → `-32602`; an unknown method → `-32601`; bad JSON → `-32700`. A notification gets no reply.
- **stdout carries only JSON-RPC.** Logs go to stderr.
- **No tool writes the user's data** unless that is designed, reviewed and marked (`readOnlyHint: false`,
  `destructiveHint`).
- **Contract tests run the real `mcp_server.py` process** over stdio against a stub API (`tests/test_mcp.py`). A
  change to a tool's name, schema or output is a breaking change and needs the version in `SERVER_INFO` raised.

## 6. Clean code

- Follow the existing structure, naming and style. There is no build step, framework or npm; keep it that way.
- Keep the scope: no unrequested refactors or renames. Fix a small bug found on the way and mention it; propose a big
  one as separate work.
- A function does one thing and its name says what. Prefer two clear functions over a boolean parameter.
- No magic numbers: use named constants (`MAX_TEXT = 2000`, `TIMEOUT_S = 60`).
- Comments explain **why**. No dead code, unused imports or commented-out code.
- Never swallow an error silently: log it or show it to the user. An intentional `except: pass` needs a comment.
- Code, identifiers, logs and UI text are English. The teacher explains in Turkish.
- Extract shared logic only on the third similar use.

## 7. Security rules

- Servers bind to `127.0.0.1` and check the `Host` header (DNS rebinding).
- Page writes need `X-LL: 1`. The services accept JSON POSTs only, and CORS only for `LS_ALLOWED_ORIGINS`.
- Strict CSP: no inline `<script>` and no `style="…"`. Style through classes or `el.style`.
- SQL values are always parameters. Bodies are limited to 64 KB. Text is cleaned of control characters and
  length-limited at the boundary.
- External text (dictionary HTML, Tatoeba, model output) is escaped before display. Never put data into `innerHTML`.
- Logs never contain what the user typed. No secrets are needed; if one ever is, it goes to the environment
  (`.env` is git-ignored) and never to code, logs, URLs or commits.

## 8. Code review checklist

Run this on every change (yours or someone else's) before approving it.

**Correctness**
- [ ] The acceptance criteria are met, including the negative cases
- [ ] Edge cases are handled: empty, the maximum, Turkish characters, a service down, the model down
- [ ] No regression in the cases of related past defects

**Tests**
- [ ] New behaviour has tests; a bug fix has a test that failed before the fix
- [ ] The tests are isolated (no network, no real data, port 0) and deterministic (no timing races)
- [ ] The test names say the expected behaviour; the assertions check outcomes, not implementation details

**LLM and MCP**
- [ ] Model output is validated field by field and labelled AI in the UI
- [ ] Anything checkable is decided by code, not by the model
- [ ] A changed prompt changes its version hash; the golden set was run and triaged
- [ ] MCP: schema, errors and annotations match the contract; there is no output on stdout except JSON-RPC

**Security and privacy**
- [ ] Guards are intact (Host, `X-LL`, JSON only, CORS, CSP)
- [ ] There is no user text in logs, and nothing new leaves the Mac without being documented
- [ ] Everything is escaped on output; SQL is parameterised

**UI**
- [ ] Colours come from tokens (light and dark); existing components are reused; class names are unique
- [ ] Buttons and links have labels; the keyboard works; Escape closes things; focus returns
- [ ] Loading, empty, error and data states exist
- [ ] Gate G4 widths were measured

**Code quality**
- [ ] The change is in scope; there are no new dependencies without approval
- [ ] There is no dead code, no magic numbers and no swallowed errors; the comments explain why
- [ ] The docs were updated (README, TESTING.md §7–§9) when behaviour changed

## 9. How to report

End every task with:

1. **What changed** (files, behaviour).
2. **Evidence**: the suite results with numbers (e.g. "20/20, 45/45"), the manual cases run with pass/fail, and the
   measurements (widths, latency).
3. **Not verified**, and why (audio, microphone, a step that needs the user's approval).
4. **New defects found** (DEF-NN with severity) and **test gaps** added.

Never present untested code as tested, and never hide a failing or skipped test.

## 10. Git

Commit, push, merge or tag only on an explicit request. Messages are short English
[Conventional Commits](https://www.conventionalcommits.org) (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), split into
logical commits, **with no AI signature lines**.
