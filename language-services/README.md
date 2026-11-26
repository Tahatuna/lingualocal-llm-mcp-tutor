# Language Services

Local English ⇄ Turkish language APIs: translation, natural speech, word cards, pronunciation scoring and a browser
client for dictation. It listens on `127.0.0.1:8770` only, the language model is local (Ollama), and no paid service
is used. Example sentences (Tatoeba) and some US IPA (dictionaryapi.dev) come from free public services.

Used by the [LinguaLocal web app](../) and meant to be reused by other projects, by web pages (HTTP API, browser
client) and by AI assistants (MCP server, below).

## Run

```bash
scripts/lsctl start      # or: .venv/bin/python server.py
scripts/lsctl status | stop | restart | logs
```

It starts at login through a LaunchAgent (`local.language-services`). Logs: `~/Library/Logs/Language Services.log`
(one JSON line per request; the text you send is never logged).

Requirements:

| Part | What | Install |
|---|---|---|
| Model | Ollama + `gemma3:12b` | `ollama pull gemma3:12b` |
| Voice (English) | Kokoro v1.0 int8 (`models/`) | see *Setup* |
| Voice (Turkish) | macOS voice *Yelda* | built in; for a better one: System Settings › Accessibility › Spoken Content › System voice › Manage voices › Turkish › Yelda (Enhanced) |
| Dictionaries | New Oxford American, Oxford Turkish (Dictionary.app) | built in; enable *Oxford Turkish* in Dictionary › Settings |
| Python | `.venv` with `kokoro-onnx`, `onnxruntime`, `lemminflect`, `soundfile`, `wordfreq` | see *Setup* |

### Setup (once)

```bash
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p models && cd models
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

## MCP server

`mcp_server.py` makes the same tools available to AI assistants through the Model Context Protocol (stdio,
JSON-RPC 2.0, protocol versions 2024-11-05 to 2025-06-18). It is plain Python with no extra packages. It calls the
running HTTP API, so the model queue, the dictionaries and the cache are shared with the page. Start the service first.

| Tool | Input | Returns |
|---|---|---|
| `translate` | `text`, `from?`, `to?` (`auto`/`en`/`tr`) | translation, detected languages, key words, source (dictionary or model) |
| `check_english` | `text` | `has_errors`, `corrected`, `fixes[{wrong, right, why_tr}]` (reasons in Turkish) |
| `rewrite_english` | `text` | up to 3 better versions with labels |
| `word_card` | `word` | the full word card (below) |
| `example_sentences` | `word` | real sentences with human Turkish translations |

All tools are read-only and none of them touches the user's saved data. If the service is down, a tool answers with
a clear error instead of failing. Register it with Claude Code:

```bash
claude mcp add language-services --scope user -- "$PWD/.venv/bin/python" "$PWD/mcp_server.py"
```

Or in any MCP client configuration:

```json
{ "mcpServers": { "language-services": { "command": "/path/to/language-services/.venv/bin/python",
                                         "args": ["/path/to/language-services/mcp_server.py"] } } }
```

## API

All responses are JSON unless noted. `POST` bodies are JSON (`Content-Type: application/json`); other content types
are refused, so a web page can only call the API when its origin is allowed (CORS, `LS_ALLOWED_ORIGINS`).

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/v1/health` | | `{ok, model, model_running, voices}` |
| GET | `/v1/warm` | | `202`; loads the voice and the model in the background (call when a page opens) |
| POST | `/v1/detect` | `{text}` | `{lang: "en" \| "tr"}` |
| POST | `/v1/translate` | `{text, from?: "auto"\|"en"\|"tr", to?}` | `{translation, from, to, key_words, source: "dictionary"\|"model", cached}` |
| POST | `/v1/translate/variants` | `{text, from?, to?}` | `{variants[{text, label}], from, to}`: up to 3 translations, closest first, each named by its nuance ("Everyday and natural", "Stronger and firmer") |
| POST | `/v1/chat` | `{messages[{role: user\|assistant, content}], context?}` | `{reply}`: an English teacher for a Turkish speaker (checks sentences, runs exercises); the caller keeps the conversation; `context` carries data such as saved words (the last 20 messages are read) |
| POST | `/v1/translate/rewrite` | `{text}` | `{versions[{text, label}]}`: up to 3 better ways to write an English text ("More natural", "More formal", "Simpler") |
| POST | `/v1/translate/check` | `{text, translation, from?, to?}` | `{has_errors, corrected, fixes[{wrong,right,why_tr}]}`: corrections of the source text |
| GET/POST | `/v1/tts` | `text, lang: en\|tr, accent: us\|uk, speed: 0.6–1.5` | `audio/wav` |
| GET | `/v1/voices` | | the voices in use |
| GET | `/v1/word` | `word` | the word card (below) |
| GET | `/v1/word/fill` | `word` | Turkish for card items the Turkish dictionary lacks (model; slower) |
| GET | `/v1/word/examples` | `word` | `{examples[{en,tr}], source}`: real sentences from Tatoeba |
| GET | `/v1/word/senses` | `word` | meanings from the model, for words the dictionaries lack |
| POST | `/v1/pronunciation/score` | `{target, alternatives[{text, confidence}]}` | `{score 0–100, verdict, heard, words[{word,status,heard}]}` |
| GET | `/client.js` | | the browser client (ES module) |

### The word card (`GET /v1/word?word=give`)

Each part comes from the most reliable source available, so a learner can trust it:

| Field | Source |
|---|---|
| `tr`, `turkish`, `turkish_phrases` | Oxford Turkish Dictionary (human translations, per meaning) |
| `meanings` (definitions, grammar notes, examples), `phrasal_verbs`, `idioms` | New Oxford American Dictionary (most frequent meanings first) |
| `family` (derived words by part of speech) | dictionary derivatives + affix rules, kept only if the English lexicon knows the word |
| `frequency` (`band`: very common … rare, `rank` among the 50,000 most used words, `zipf`) | wordfreq (Wikipedia, subtitles, news, books, web), all forms of the word counted; phrases are an estimate |
| `forms`, `irregular`, `tenses` (13 rows with negative and question) | rules + lemminflect lexicon; verbs like *lie* (lay/lied) are curated |
| `complement` (-ing or to), `aspect` (stative), `prepositions`, `mistakes` | curated lists from learner grammars (`services/grammar_data.py`) and rules: the typical mistakes are built from the curated pattern, not by the model |
| `ipa.uk` / `ipa.us` | Oxford (UK); Wiktionary or the voice's phonemizer (US) |

Anything the model adds (`/v1/word/fill`, `/v1/word/senses`, sentence translation and checks) is labelled by the
endpoint it comes from, so a client can mark it.

### Speed (test Mac: M2 Pro, 16 GB)

| Request | Time |
|---|---|
| word card | ~0.5 s first time (~1 s right after a restart), 2–5 ms cached |
| single word translation (dictionary) | ~0.1 s |
| sentence translation (model, warm) | median 1.75 s, max 2.50 s on the 30-sentence test set (2026-11-27) |
| translation options (variants) | 6–12 s (after the translation is shown) |
| sentence check | 5–15 s (English input only, after the translation) |
| speech, English sentence | ~0.3–0.7 s; cached clips ~1 ms |

The model answers one request at a time, so requests go through one priority queue: translations first, then sentence
checks and the teacher chat, then word-card fills. Measured without it: a translation waited 23.5 s behind a word card.

### Browser client

```js
import { createClient, listen, testPronunciation } from 'http://localhost:8770/client.js';
const ls = createClient();
const { translation } = await ls.translate('I have been looking forward to this.');
ls.speak('looking forward', { lang: 'en', accent: 'uk', speed: 0.8 });
const stop = listen({ lang: 'tr-TR', onText: (final, interim) => {}, onEnd: (err) => {} });  // dictation
const result = await testPronunciation(ls, 'think');                                       // {score, words}
```

Dictation and the pronunciation test use the browser's speech recognizer (Chrome sends the audio to Google for
recognition). Your page's origin must be in `LS_ALLOWED_ORIGINS`.

## Settings (environment)

`LS_PORT` (8770), `LS_DATA_DIR` (cache, default `~/Library/Application Support/Language Services`),
`LS_ALLOWED_ORIGINS` (comma separated, default `http://localhost:8767,http://127.0.0.1:8767`),
`LS_OLLAMA_URL`, `LS_OLLAMA_MODEL` (`gemma3:12b`), `LS_OLLAMA_KEEP_ALIVE` (`30m`),
`LS_VOICE_US` (`af_heart`), `LS_VOICE_UK` (`bf_emma`), `LS_VOICE_TR` (`Yelda`).
MCP server: `LS_URL` (`http://127.0.0.1:8770`), where it finds the running API.

## Tests

```bash
.venv/bin/python -m unittest discover tests          # unit + MCP tests: no network, no model
.venv/bin/python tests/make_fixtures.py              # once: dictionary entries for the parser tests (from this Mac)
.venv/bin/python tests/quality/run_translation.py    # translation quality run against the real model
.venv/bin/python tests/quality/compare_models.py gemma3:12b other-model   # side by side, same prompt
```

## Known limits

- Model choice (2026-11-24, 30-sentence set): gemma3:12b median 1.76 s on that run; aya-expanse:8b median 0.47 s but broke Turkish
  grammar ("Geliyordunuzu bilseydim", "bir sonraki hafta ertelendi") and shifted meanings ("Afiyet olsun" → "Delicious!").
  gemma3:12b stays: accuracy matters more for learning.
- The model writes *sigara* + accusative as "sigayı" (a weakness of this model; found by the quality run).
- The model once translated *train station* as "banliyö istasyonu" (a meaning shift; found by the quality run).
- Oxford Turkish has no entries for a few very basic words (*go*, *do*); their Turkish comes from `/v1/word/fill`.
- The dictionary records API (`DCSCopyRecordsForSearchString`) is not public; if a macOS update removes it, the card
  loses Oxford data and falls back to the model (`/v1/word/senses`).
- Pronunciation scoring finds word mix-ups (ship/sheep, think/sink) through the recognizer; it does not grade
  fine accent details.
