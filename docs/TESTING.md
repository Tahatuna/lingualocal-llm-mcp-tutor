# LinguaLocal: Test Plan, Test Cases and Test Report

| | |
|---|---|
| **Product** | LinguaLocal: an English ⇄ Turkish tutor on a local LLM, with an MCP server |
| **Components under test** | Web app + data server (`:8767`), Language Services API (`:8770`), MCP server (stdio) |
| **Test owner** | Project author (QA / test lead) |
| **Platform** | macOS only (the product depends on macOS dictionaries, voices and LaunchAgents) |
| **Last full run** | 2026-11-27, results in [§10](#10-test-report-2026-11-27) |

**Contents**

1. [Quality goals](#1-quality-goals)
2. [Scope](#2-scope)
3. [Risk analysis](#3-risk-analysis)
4. [Test strategy](#4-test-strategy)
5. [Entry and exit criteria](#5-entry-and-exit-criteria)
6. [Test environment and data](#6-test-environment-and-data)
7. [Requirements traceability](#7-requirements-traceability)
8. [Test cases and acceptance criteria](#8-test-cases-and-acceptance-criteria)
9. [Defect log](#9-defect-log)
10. [Test report](#10-test-report-2026-11-27)
11. [Known test gaps](#11-known-test-gaps)

---

## 1. Quality goals

A learner trusts what this app teaches. A wrong grammar rule or an invented meaning is worse than no answer. In
priority order, the quality goals are:

1. **Correctness of what is taught.** Dictionary facts are never replaced by model guesses, model output is labelled
   **AI**, and anything code can check is checked by code.
2. **Privacy and local-only operation.** Your text stays on the Mac, except for the documented public lookups.
3. **Responsiveness.** The answer you are waiting for comes first, and slow model work never blocks a translation.
4. **A stable MCP contract.** Tools have fixed names, schemas and error behaviour, so AI clients can depend on them.
5. **Usability on every screen width**, with keyboard access and no hidden failures.

## 2. Scope

| In scope | Out of scope |
|---|---|
| Page features, data API, Language Services API, MCP server | Accuracy of Ollama, Kokoro or Chrome themselves |
| Prompt contracts and validation of model output | Windows and Linux (not supported) |
| Translation quality on a fixed sentence set (evaluation, not pass/fail) | Load testing (single user, local) |
| Security of the local servers (Host, CSRF, CSP, input limits) | Penetration testing of macOS or the browser |
| Responsive layout at 320–1440 px, keyboard use | Screen-reader certification (only basic ARIA is checked) |

## 3. Risk analysis

Likelihood and impact are rated 1–3. The risk score (L×I) sets the test depth.

| ID | Risk | L | I | Score | Mitigation and tests |
|---|---|---|---|---|---|
| R1 | The LLM invents facts (meanings, rules, quiz words) | 3 | 3 | **9** | Trusted sources first; code-graded quiz; validation of model output — `GrammarTest`, `test_quiz_asks_only_saved_words_with_a_meaning`, TC-QZ-01, TC-WC-02 |
| R2 | The LLM returns malformed or hostile output (bad JSON, HTML, tags) | 3 | 2 | **6** | Schema validation, escaping, tag stripping — `test_check_drops_empty_fixes`, `test_variants_dedupe_and_cap`, `test_chat_reply_…_wraps_context` |
| R3 | A slow model call blocks the translation you are waiting for | 3 | 2 | **6** | Priority queue with preemption — `QueueTest`, TC-PERF-01 |
| R4 | Another website reads or changes local data (DNS rebinding, CSRF) | 2 | 3 | **6** | Host allowlist, custom header, JSON only, CORS allowlist — `ServerTest` (both parts), TC-SEC-01…04 |
| R5 | A prompt injection through saved words or chat text | 2 | 2 | 4 | Data in tags, `<` neutralised, length limits — `test_chat_reply_…_wraps_context` |
| R6 | MCP clients break on a contract change | 2 | 2 | 4 | Contract tests on the real stdio process — `test_mcp.py`, TC-MCP-01…05 |
| R7 | Data loss on migration or rename | 1 | 3 | 3 | Forward-only migrations with a backup; old data folder kept — `MigrationTest`, `DataFolderTest`, TC-DATA-01 |
| R8 | The layout breaks on small screens or with classic scrollbars | 2 | 1 | 2 | Width matrix — TC-UI-01 |
| R9 | A macOS update removes the private dictionary API | 1 | 3 | 3 | The card falls back to the model and labels it; documented in the known limits |

## 4. Test strategy

### 4.1 Test levels

```
        ┌───────────────────────────┐
        │ Exploratory + manual E2E  │  browser on macOS, audio, microphone, MCP in Claude Code
        ├───────────────────────────┤
        │ LLM evaluation (golden)   │  30 sentences on the real model, every miss reviewed
        ├───────────────────────────┤
        │ Contract / integration    │  real HTTP servers on random ports, MCP over real stdio
        ├───────────────────────────┤
        │ Unit                      │  parsers, rules, queue, validators, store, quiz grading
        └───────────────────────────┘
```

| Level | Tool | Runs | Network or model |
|---|---|---|---|
| Unit | `unittest` | every change | no: model and HTTP are stubbed |
| Integration | `unittest` + real `ThreadingHTTPServer` on port 0 | every change | no |
| MCP contract | `test_mcp.py`, with the real `mcp_server.py` process against a stub API | every change | no |
| Page scripts | Node (`node --check`, quiz grading imported as an ES module) | every change | no |
| LLM evaluation | `tests/quality/run_translation.py`, `compare_models.py` | every prompt or model change | yes: local Ollama only |
| Manual E2E | Chrome on macOS, using the cases in §8 | every feature or UI change | local only |

### 4.2 Test design techniques used

- **Equivalence classes and boundary values** for input limits:
  - empty text, whitespace only, exactly 2000 characters and 2001 characters (the MCP server's `MAX_TEXT`);
  - 64 KB request bodies;
  - a word of 80 characters;
  - `from` values `auto | en | tr | de`.
- **Negative testing** on every guard:
  - a foreign `Host` header;
  - a missing `X-LL` header;
  - a non-JSON body;
  - a CORS origin that is not allowed;
  - path traversal (`/../store.py`);
  - an unknown MCP tool or method;
  - a parse error;
  - the service being down.
- **State-transition testing** for the quiz (start → question → answer → … → stop → score) and for chats
  (create → rename → switch → delete).
- **Decision tables** for language detection (Turkish letters, the forced direction, the word count) and for when
  **Say words** speaks (word vs sentence, live dictation, page restore).
- **Error guessing** from real defects (§9): multi-word phrases, Turkish `İ/ı` normalisation, tags in user text.
- **Golden-set evaluation** for the LLM. Each sentence has "must contain" key words. A miss is a **signal for a person
  to review**, not an automatic failure, because a correct paraphrase can miss a key word.

### 4.3 Testing a non-deterministic LLM

- Unit tests never call the model. They stub it and test **our** contract: the prompt is built correctly, every field
  of the output is validated, and bad output is dropped.
- The model temperature is low, and every prompt has a **version hash in its cache key**, so an evaluation always runs
  against the current prompt.
- Quality is measured, not assumed:
  - the golden set reports the median and maximum latency and the misses;
  - each miss is triaged as *paraphrase (accept)* or *defect (log)*;
  - `compare_models.py` compares candidate models on the same prompt.
- A model is accepted only when its outputs are **correct Turkish**, not only when they are fast. In the comparison,
  `aya-expanse:8b` was rejected despite a 0.47 s median because it broke Turkish grammar.

### 4.4 Regression policy

- Every defect gets a **regression test that fails before the fix and passes after it**. Where that cannot be
  automated (audio, real microphone, visual layout), a manual case is added to §8 and listed in §11.
- A fix is **retested** in the running app (the LaunchAgents restarted, the page reloaded without cache), and the full
  suite is run again.

## 5. Entry and exit criteria

**Entry (definition of ready).** Work on a feature starts only when:

- its acceptance criteria are written in Given/When/Then form and agreed;
- for an MCP tool, its contract is defined: name, input schema, output, errors, and whether it is read-only;
- the test data needed is known and is not the user's real data.

**Exit (definition of done).** A change is accepted only when:

- [ ] all unit, integration and contract tests pass (0 failures; skips are allowed only for the documented fixture);
- [ ] a bug fix has a regression test, or a manual case plus a gap entry;
- [ ] the affected manual cases in §8 pass on macOS in Chrome;
- [ ] the UI was checked at 320, 375, 768, 1280 and 1440 px: no horizontal scroll, no clipped text, no CSP errors;
- [ ] after a prompt or model change, the golden set was run and every miss was triaged;
- [ ] the code review checklist in the [project skill](../.claude/skills/lingualocal-dev/SKILL.md#8-code-review-checklist) passes;
- [ ] the running copy was updated and checked again;
- [ ] the report states what was **not** verified.

## 6. Test environment and data

| Item | Value |
|---|---|
| OS | macOS 27.2 on Apple silicon (M2 Pro, 16 GB) |
| Runtimes | Python 3.13.7, Node 24.18, Google Chrome |
| Model | Ollama 0.40.16, `gemma3:12b` |
| Voices | Kokoro v1.0 int8 (US `af_heart`, UK `bf_emma`); macOS *Yelda* (TR) |
| Dictionaries | New Oxford American, Oxford Turkish (Dictionary.app) |

**Test data rules**

- Automated tests use a temporary data folder (`LL_DATA_DIR`, `LS_DATA_DIR`) and port 0, and are cleaned up afterwards.
- Manual and E2E runs use an isolated copy with sample data, never the user's real history or saved words:

  ```bash
  LL_PORT=8779 LL_SERVICES=http://localhost:8781 LL_DATA_DIR="$(mktemp -d)" python3 server.py &
  cd language-services && LS_PORT=8781 LS_ALLOWED_ORIGINS=http://localhost:8779 \
      LS_DATA_DIR="$(mktemp -d)" .venv/bin/python server.py
  ```

- The dictionary parser fixtures are real Oxford entries. They are licensed with macOS, so they are **not published**.
  Generate them locally with `language-services/tests/make_fixtures.py`; without the file, those 4 tests are skipped.

**How to run**

```bash
python3 -m unittest discover tests -v                                       # web app and data (20)
(cd language-services && .venv/bin/python -m unittest discover tests -v)    # services + MCP (38 + 7)
(cd language-services && .venv/bin/python tests/quality/run_translation.py) # LLM golden set (30)
```

## 7. Requirements traceability

| Req | Requirement | Automated tests | Manual cases |
|---|---|---|---|
| REQ-01 | A word is translated from the Oxford Turkish Dictionary | `DictionaryParseTest`, `test_detect` | TC-TR-01 |
| REQ-02 | A sentence is translated by the local LLM; the key words are listed | `test_sentence_goes_to_the_model_with_examples`, `test_key_words_*` (2), golden set | TC-TR-02, TC-TR-03 |
| REQ-03 | English is corrected, with the reason for each fix in Turkish | `test_check_drops_empty_fixes`, `test_check_english_translates_then_checks` | TC-WR-01 |
| REQ-04 | Better versions of a text and alternative translations, each labelled | `test_rewrite_drops_unchanged_and_repeated`, `test_variants_dedupe_and_cap` | TC-WR-02 |
| REQ-05 | The word card comes from trusted sources | `FormsTest` (6), `FrequencyTest`, `GrammarTest` (3), `DictionaryParseTest` (4) | TC-WC-01 |
| REQ-06 | An unlisted phrase is explained by the model and marked AI | `test_unlisted_noun_phrase_is_not_a_verb` | TC-WC-02 |
| REQ-07 | Natural voice; **Say words** speaks only words | `test_tts_rejects_markup`, `test_client_js_is_served` | TC-AU-01, TC-AU-02 |
| REQ-08 | Mouth & tongue animation | `test_mouth_script_is_served`, `test_page_scripts_parse` | TC-MO-01, TC-MO-02 |
| REQ-09 | Pronunciation test and dictation | `PronounceTest` (4), `test_score_endpoint` | TC-PR-01…03 |
| REQ-10 | Teacher chat, with chats kept | `test_chats_are_kept_side_by_side_renamed_and_deleted`, `test_a_chat_keeps_only_its_newest_messages`, `test_long_names_are_shortened`, `test_chat_validate_*`, `test_chat_reply_*` | TC-CH-01…03 |
| REQ-11 | The quiz uses only saved words and is graded by code | `test_quiz_asks_only_saved_words_with_a_meaning`, `test_quiz_with_one_word_and_with_none`, `test_quiz_grading_is_done_by_code`, `test_quiz_answers_are_normalised` | TC-QZ-01 |
| REQ-12 | History and saved lists | `StoreTest` (2), `test_saved_roundtrip`, `test_remove_one_history_item`, `test_history_keeps_the_input_language` | TC-LS-01, TC-LS-02 |
| REQ-13 | MCP server with 5 read-only tools | `test_mcp.py` (7) | TC-MCP-01…05 |
| REQ-14 | Local only and secure | `test_page_has_csp_and_no_inline_script`, `test_foreign_host_and_missing_header_refused`, `test_only_listed_files_are_served`, `test_foreign_host_refused`, `test_post_needs_json`, `test_cors_only_for_allowed_origins` | TC-SEC-01…04 |
| REQ-15 | Responsive and keyboard friendly | — | TC-UI-01, TC-UI-02 |
| REQ-16 | Performance budgets (§8.10) | `QueueTest` (2), `PhonemizerCacheTest` (2), golden set timings | TC-PERF-01 |
| REQ-17 | No data loss on upgrade or rename | `MigrationTest`, `DataFolderTest` | TC-DATA-01 |

## 8. Test cases and acceptance criteria

Each case has a priority: P1 must pass to ship, P2 should pass, P3 is nice to have. Unless stated otherwise, cases
run in Chrome on macOS against the isolated copy.

### 8.1 Translation

**TC-TR-01: word from the dictionary** · P1 · REQ-01
- **Given** the services are running
- **When** I type `reluctant`
- **Then** *isteksiz* appears from the **Oxford Turkish Dictionary**, in about 0.1 s
- **And** the source is named on the card, with no AI label

**TC-TR-02: sentence from the local LLM** · P1 · REQ-02
- **Given** Ollama is running with `gemma3:12b`
- **When** I type `I have been looking forward to this.`
- **Then** a Turkish translation appears within **3 s** (budget: median ≤ 2 s)
- **And** it is labelled **AI**, and *look forward to* is listed as a key word

**TC-TR-03: Turkish input and direction** · P2 · REQ-02, REQ-04
- **When** I type `Yarın erken kalkmam lazım.`
- **Then** the direction becomes **TR → EN** by itself
- **And** up to three English translations appear, each with a nuance label and no duplicates

### 8.2 Writing help

**TC-WR-01: correction with the reason in Turkish** · P1 · REQ-03
- **When** I type `She go to school by bus yesterday.`
- **Then** **Correct English** shows *She went to school by bus yesterday.*
- **And** the fix `go → went` has a reason written in **Turkish**
- **And** a correct sentence (`She goes to school.`) shows **no** correction block

**TC-WR-02: better ways to write it** · P2 · REQ-04
- **Then** at most 3 versions appear, labelled *More natural / More formal / Simpler*
- **And** none is identical to my input or to another version

### 8.3 Word card

**TC-WC-01: trusted word card** · P1 · REQ-05
- **When** I look up `give`
- **Then** I see:
  - meanings in order of frequency, with Turkish for each meaning;
  - US/UK IPA, verb forms and 13 tenses;
  - phrasal verbs and the frequency band (*very common*);
- **When** I look up `avoid`
- **Then** it says *followed by the -ing form*, with the mistake *I avoided to do it.* → *I avoided doing it.*
- **When** I look up `reluctant`
- **Then** the word family shows *reluctance* (noun) and *reluctantly* (adverb), with Turkish
- **And** every section names its source (Oxford, curated, wordfreq)

**TC-WC-02: unlisted phrase** · P1 · REQ-06
- **When** I look up `bicycle bay`
- **Then** its meaning is shown in a section marked **AI**
- **And** no verb forms, tenses or verb mistakes appear (it is a noun phrase)

### 8.4 Audio

**TC-AU-01: voices** · P1 · REQ-07 · *needs a person (audio)*
- **When** I press Play and then Slow, in US and then UK
- **Then** the voice is natural, Slow is clearly slower, the accent changes, and Turkish text uses the Turkish voice

**TC-AU-02: Say words** · P2 · REQ-07 · *needs a person (audio)*
- **Given** **Say words** is on
- **When** I look up a word, and then a sentence
- **Then** only the word is spoken
- **And** the option is still on after a reload
- **And** nothing is spoken while I dictate or when the page restores the last lookup

### 8.5 Mouth & tongue

**TC-MO-01: layout** · P2 · REQ-08
- **When** I open **Mouth & tongue** on `catastrophically`
- **Then** all sound cards have the same height (about 50 px), wrap onto new rows if needed, and sit under the views
- **And** the note uses the full width below them

**TC-MO-02: hold a sound** · P2 · REQ-08
- **When** I click the `l` card
- **Then** the side view shows the tongue tip touching behind the upper teeth (touch point marked)
- **And** the note says *voiced* and *air through the mouth*

### 8.6 Pronunciation and dictation

**TC-PR-01: pronunciation score** · P1 · REQ-09 · *needs a person (microphone)*
- **When** I press **Test my pronunciation** and say `think` as *sink*
- **Then** a score from 0 to 100 appears, and the word is marked as heard as *sink*

**TC-PR-02: result is visible** · P2 · REQ-09
- **Given** the Mouth & tongue panel is open
- **When** I start the pronunciation test
- **Then** the panel closes, so the result is in view

**TC-PR-03: dictation joins words correctly** · P1 · REQ-09 · *needs a person (microphone)*
- **When** I dictate `this is a test because I can`
- **Then** the words keep their spaces (*test because*, not *testbecause*), the translation follows the speech, and a
  pause stops listening

### 8.7 Teacher chat and quiz

**TC-CH-01: sentence check in the chat** · P1 · REQ-10
- **When** I send `She don't like coffee. Is this correct?`
- **Then** within 15 s the teacher says it is wrong, gives *She doesn't like coffee.*, and explains why in Turkish

**TC-CH-02: persistence** · P1 · REQ-10
- **When** I reload the page
- **Then** the panel's open or closed state, the selected chat and every message are kept

**TC-CH-03: manage chats** · P2 · REQ-10
- **When** I create, rename, switch between and delete chats
- **Then** the chats are kept side by side, and deleting asks for confirmation and names the chat and its message count

**TC-QZ-01: quiz from saved words** · P1 · REQ-11
- **Given** I saved 5 words that have Turkish meanings
- **When** I start the quiz, answer one right, answer one wrong (`İ/ı` and case are ignored), and type `stop`
- **Then** every question is one of my 5 words
- **And** right and wrong are decided by the app; the model plays no part in grading
- **And** the final score is shown

### 8.8 Lists

**TC-LS-01: speak a row** · P2 · REQ-12 · *needs a person (audio)*
- **When** I click the speaker in a history row and in a saved row
- **Then** each item is spoken in its own language

**TC-LS-02: save, remove, clear** · P1 · REQ-12
- **When** I save a word, remove it, and clear the history
- **Then** the lists update at once
- **And** clearing asks for confirmation with the item count, and saved items stay

### 8.9 MCP server

**Contract:**

| Tool | Input | Output | Errors | Side effects |
|---|---|---|---|---|
| `translate` | `text` (1–2000 chars), `from`/`to` ∈ {auto, en, tr} | translation, languages, key words, source | `isError` with a readable reason | none (read-only) |
| `check_english` | `text` | `has_errors`, `corrected`, `fixes[{wrong,right,why_tr}]` | same | none |
| `rewrite_english` | `text` | `versions[{text,label}]` (≤ 3) | same | none |
| `word_card` | `word` (≤ 80 chars) | the full word card | same | none |
| `example_sentences` | `word` | `examples[{en,tr}]` | same | none |

Protocol: JSON-RPC 2.0 over stdio, protocol versions 2024-11-05 to 2025-06-18. A notification gets no response.
Errors use the standard codes `-32700`, `-32601` and `-32602`.

**TC-MCP-01: handshake** · P1
- **When** a client sends `initialize` and then `tools/list`
- **Then** the server answers with the requested protocol version and lists 5 tools, each with `readOnlyHint: true`

**TC-MCP-02: a real call** · P1
- **When** Claude Code (with the project's `.mcp.json` approved) is asked *"Check this English: She go to school by bus yesterday."*
- **Then** it calls `check_english`, and the answer contains *went* and a Turkish reason

**TC-MCP-03: invalid input** · P1
- **When** a tool gets an empty text, 2001 characters, or `from: "de"`
- **Then** it returns `isError: true` with a reason, and **no request reaches the API**

**TC-MCP-04: service down** · P1
- **Given** Language Services is stopped
- **When** any tool is called
- **Then** it answers *"not reachable … scripts/lsctl start"*, and the MCP server keeps running

**TC-MCP-05: protocol errors** · P2
- **When** the server gets bad JSON, an unknown method or an unknown tool
- **Then** it answers `-32700`, `-32601` and `-32602`, and a later `ping` still succeeds

### 8.10 Security, performance, UI, data

**TC-SEC-01: foreign Host** · P1
- `curl -H 'Host: evil.example' http://127.0.0.1:8767/api/history` returns **403**

**TC-SEC-02: CSRF header** · P1
- `curl -X POST http://127.0.0.1:8767/api/history/clear` without `X-LL: 1` returns **403**, and nothing is cleared

**TC-SEC-03: CSP** · P1
- With the console open, use every screen: there are **no CSP violations**, and the page has no inline script or style

**TC-SEC-04: model down** · P2
- **Given** Ollama is not running
- **When** I translate a sentence and then a word
- **Then** the sentence shows a clear *"local model is not running"* message, and the word still works from the dictionary

**TC-PERF-01: performance budgets** · P2

| Request | Budget |
|---|---|
| Word card, first time | ≤ 1 s |
| Word card, cached | ≤ 50 ms |
| Word translation (dictionary) | ≤ 0.2 s |
| Sentence translation, model warm | median ≤ 2 s, max ≤ 3 s |
| Translation while a check is running | no wait: the check is cancelled |

**TC-UI-01: width matrix** · P1
- At 320, 375, 768, 1280 and 1440 px, with overlay **and** classic scrollbars:
  - `scrollWidth − clientWidth = 0`;
  - no clipped or overlapping text;
  - at ≤ 900 px the teacher panel becomes full screen.

**TC-UI-02: keyboard** · P2
- With the keyboard alone:
  - `/` focuses the input, Enter submits, and Shift+Enter adds a new line;
  - the chat `⋯` menu works with the arrow keys, and Escape closes it and returns focus;
  - the focus ring is visible.

**TC-DATA-01: upgrade keeps data** · P1
- **Given** a Mac with data under the app's first name (`Pronunciation Mirror`)
- **When** LinguaLocal starts
- **Then** it uses that folder, so no history, saved word or chat is lost

## 9. Defect log

More than 20 defects were found during development, and one more (DEF-22) in the final review. These are the ones with a lesson worth keeping: each has its
root cause and the test that now guards against it. Small slips that were fixed on the spot are not listed.
Severity: S1 critical · S2 major · S3 minor · S4 cosmetic.

| ID | Defect | Sev | Root cause | Fix | Regression guard |
|---|---|---|---|---|---|
| DEF-01 | The quiz asked about *Delicious*, a word the learner had not saved | S2 | Choosing quiz questions was left to the LLM | The quiz is chosen and graded by code | `test_quiz_asks_only_saved_words_with_a_meaning`, TC-QZ-01 |
| DEF-02 | The word card showed invented grammar (wrong -ing/to rules) and invented meanings | S2 | The model was the source of facts | Dictionaries and curated rules first; the model only fills gaps, labelled AI | `test_mistakes_are_rule_made`, `test_word_family_rules_never_invent_words`, `test_curated_patterns` |
| DEF-03 | `bicycle bay` was conjugated as a verb (*bicycled bay*) | S3 | An unknown multi-word phrase was treated as a verb | Unknown phrases are noun phrases; only real phrasal verbs get verb data | `test_unlisted_noun_phrase_is_not_a_verb` |
| DEF-04 | A short translation waited **23.5 s** behind a word-card request | S2 | The model serves one request at a time, first come first served | Priority queue; a translation cancels a running low-priority call | `test_translation_cuts_off_a_running_check`, `test_lower_priority_never_cuts_off_a_translation` |
| DEF-05 | An old translation was shown after the prompt changed | S3 | The cache key did not include the prompt | A prompt-version hash is part of the cache key | retested manually (translation of *bicycle bay*) |
| DEF-06 | The teacher echoed internal `<saved>` tags; learner text could close the tag early | S3 | Data and instructions were not separated well enough | `<` is neutralised in the data, and tags are stripped from replies | `test_chat_reply_needs_a_user_message_and_wraps_context` |
| DEF-07 | Dictation glued words together (*testbecause*) | S2 | Speech chunks were trimmed after a "starts with a space" check | Chunks are trimmed first, then joined with one space | TC-PR-03 (manual; see §11) |
| DEF-08 | The pronunciation result was hidden under the open Mouth & tongue panel | S3 | Both panels stayed open | The panel closes when the test starts | TC-PR-02 |
| DEF-09 | The sound cards stretched to the note's height and the note was squeezed | S4 | `align-items: stretch` in a two-column grid | Cards in one row, the note below | TC-MO-01 |
| DEF-10 | The header overflowed by 6 px at 375 px | S4 | Classic scrollbars take 11 px; overlay scrollbars hid the problem | The brand can shrink; tighter buttons below 400 px | TC-UI-01 (now run with both scrollbar types) |
| DEF-11 | The release audit found full Oxford dictionary entries in a test fixture | S2 (licence) | Real data was saved for parser tests | The fixture is git-ignored, made locally by a script, and the tests skip without it | release checklist |
| DEF-12 | The model writes *sigayı* for *sigarayı* (2 of 30 golden sentences) | S3 | A weakness of the model | **Open**: known limitation, tracked by the golden set | golden set |
| DEF-13 | *train station* was translated as *banliyö istasyonu* (meaning shift) | S3 | A model error | **Open**: tracked by the golden set | golden set |
| DEF-14 | An unlisted word showed an empty "Turkish" heading and no meaning | S2 | The model-meanings endpoint existed but was never called by the page | The card calls it when the dictionaries have nothing; the output is labelled AI | TC-WC-02 |
| DEF-15 | Saved words with an empty Turkish meaning could never be quizzed | S3 | A word saved before its translation arrived kept an empty meaning | A later translation fills in the saved word | TC-QZ-01 |
| DEF-16 | The first keystrokes of a quiz answer were lost | S3 | The input had no focus when the quiz started | The input is focused on start | TC-QZ-01 |
| DEF-17 | The teacher greeted the learner in every reply and once offered a wrong "more natural" version (*She used to go…*) | S3 | The prompt was too loose | The prompt was tightened: no greetings, and alternatives only when sure | TC-CH-01 |
| DEF-18 | On the word card, the Turkish example sentence ran into the English one | S4 | The example and its translation were inline elements | The translation is a block on its own line | TC-WC-01 |
| DEF-19 | Card buttons scattered with a long word and two IPA blocks (two wrapped, one stayed right) | S4 | The title, IPA and buttons shared one wrapping row | The buttons got their own row | TC-WC-01 (short and long words) |
| DEF-20 | The header overflowed at 375 px after the Teacher button was added | S4 | The button label was too long for phones | A shorter label and a smaller header at ≤ 600 px | TC-UI-01 |
| DEF-21 | The launcher reported "running" while another local app held the port, and opened the wrong app | S2 | The health check accepted any HTTP answer | A dedicated port, and the health check verifies the service's own answer (`lsctl`) | manual: `lsctl status` with the port taken |
| DEF-22 | A cached word card took 0.5 s on **every** request for words without a dictionary US IPA (budget: 50 ms) | S3 (perf) | The phonemizer restarts in each request thread and its result was never cached | Its IPA is cached per word and accent; failures are not cached | `PhonemizerCacheTest` (failed before the fix), TC-PERF-01 |

## 10. Test report (2026-11-27)

| Suite | Total | Passed | Failed | Skipped |
|---|---|---|---|---|
| Web app + data (`tests/`) | 20 | 20 | 0 | 0 |
| Language Services + MCP (`language-services/tests/`) | 45 (38 + 7) | 45 | 0 | 0 (4 skip on a machine without the local fixture) |
| LLM golden set (30 sentences, real model) | 30 | 27 correct | 3 wrong | — |

**Golden set triage.** The key-word check flagged 7 of 30 sentences. On review, 4 were correct paraphrases (*this
evening* for *tonight*, *apologize* for *sorry*, *get well soon*, *making dinner*). The other 3 are real errors: DEF-12
(twice) and DEF-13. Latency: **median 1.75 s, max 2.50 s**, which is within the budget.

**Manual and E2E (isolated copy, Chrome on macOS 27.2):**

| Case | Result |
|---|---|
| TC-TR-01, TC-WR-01, TC-WR-02, TC-WC-01, TC-MO-01, TC-MO-02, TC-CH-01 | Pass |
| TC-SEC-01, TC-SEC-02 | Pass (403, nothing cleared) |
| TC-UI-01 (320 / 375 / 768 / 1280 / 1440 px, classic scrollbar) | Pass after the DEF-10 fix |
| TC-MCP-01, 03, 04, 05 | Pass (automated contract tests) |
| TC-MCP-02 | MCP server checked against the real services and model (`translate`, `check_english` correct); the run inside Claude Code waits for the project server's approval |
| TC-PERF-01 | Pass after the DEF-22 fix. Cached card: 2–3 ms. First card: about 0.5 s (1.1 s right after a restart, while the voice engine loads). Word translation: 0.11 s. Sentence, model warm: 1.9 s (golden set median 1.75 s, max 2.50 s). |
| TC-DATA-01 | Pass: after the rename, the real app still serves the existing saved words |
| TC-AU-01, TC-AU-02, TC-LS-01, TC-PR-01, TC-PR-03 | Not run by automation (audio and microphone); manual run by the author |

## 11. Known test gaps

| Gap | Why | Plan |
|---|---|---|
| Dictation word joining (DEF-07) has no automated test | Not yet written. The fix lives in `joinText` in `language-services/client/ls-client.js`, a pure function that Node can import directly | Add a Node test with chunks that start or end with spaces (`' test'`, `'because '`) |
| Audio output and the microphone | Automation cannot hear or speak | Manual cases TC-AU-*, TC-PR-*, run on every audio change |
| No CI | The tests need macOS (dictionaries, voices) and a local model | Run locally before every commit; a macOS CI runner without the model could run the unit tests |
| No coverage measurement | Only the standard library is used, no `coverage` package | Traceability (§7) is used instead; add `coverage.py` if the project grows |
