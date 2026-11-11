# BotHocTap

[Tiếng Việt](README.vi.md) · English

A personal Telegram assistant that runs **on your own PC**. It answers questions about your course material, finds and sends files, manages a to-do list, and (after a password) lets Claude read, edit files and propose commands on the machine — all from your phone, at the lowest token cost it can manage.

It started as a "study bot" (RAG over lecture notes) and grew into a small assistant. Everything is single-user by design; other people can only use the study features.

> Status: personal project, used daily by its author. The 2026-11-05 features (Claude mode, session picker, whole-drive file search, new menu) were tested by the author on a real Telegram chat; the notebook "Add file" button is newer and only script-tested.

## Design goals

1. **Few Claude tokens.** Gemini (free tier) answers by default; local models do embeddings and OCR; Claude is used only when you explicitly enter Claude mode, in the weekly wiki job, or in `/capnhat`.
2. **Accurate.** Answers are grounded in retrieved chunks of your own files, with sources and a "how well did it match" line.
3. **Can act on the PC, safely.** A phone is the weakest link, so powerful modes need a password, commands need a button press, and secrets are blocked.
4. **Runs without Claude.** If the Claude subscription lapses, the bot keeps working (Gemini + local index + local data files).

## How it works

```
Telegram ──► bot (python-telegram-bot, long polling, runs in the tray on your PC)
              │
              ├─ login / owner check ───── strangers get silence
              ├─ active mode? (checked FIRST, before any guessing)
              │     password prompt → web-AI import (/nhapai) → /capnhat session → Claude mode → /notebook mode → "✍" pending argument
              ├─ natural-language rules: debts ("Giang nợ 13k"), to-dos, "find me file …"
              └─ otherwise: question answering (RAG)
                    question ─► local index (bge-m3 embeddings, GPU) ─► top chunks
                            ─► Gemini writes the answer from those chunks only
                            ─► reply + "🔎 N chunks, nearest files, match: high/medium/low"
```

### Question answering (RAG)
`index_course.bat` splits your course files (PDF, DOCX, PPTX, text, code; scanned PDFs through OCR) into chunks and embeds them locally with BAAI/bge-m3 into `index_local/`. The Obsidian wiki is indexed too. A question is searched two ways at once, by meaning (embeddings) and by keywords (BM25, accent-insensitive, so lecture codes like "stk 03" match), and the two rankings are merged; wiki pages are split by heading, one linked neighbour page can be added, the 10 best chunks go to Gemini (a repeated question is answered instantly from a local cache with a "ask again" button), which answers using only those chunks and cites file and page. Each answer ends with a short explanation line so you can judge whether the retrieval was any good.

### Finding and opening files
`kfind.py` keeps an in-memory **name index** (built in a background thread) of the course folder and, for the owner, the whole drive. Search ignores case and diacritics ("tu duy he thong" finds "tư duy hệ thống"). No exact hit → closest names are suggested. Secrets (`.env`, `password.json`, tokens, keys) never appear; other logged-in users only see the course folder. `/open` refuses runnable file types.

### Claude mode (owner only)
`/model claude` links the bot to the newest saved Claude Code session of this project; `/agent` lists every session on the machine (sessions outside the bot's drive are shown but cannot be joined) or starts a new one. You type the **password every time you enter**; the message holding it is deleted. In the mode every normal message goes to that session through `claude -p --resume`. Claude gets Read/Glob/Grep/Edit/Write on the drive but **no shell tool**: a command can only be proposed as a `CHẠY:` line, which the bot shows with ✅ Run / ❌ Cancel buttons. Reading secrets and editing the bot's frozen data files are denied by permission rules. The mode expires after 30 idle minutes.

Caveats: typing in VS Code and Telegram on the *same* session at the same moment makes the history diverge; and every message re-sends the whole session history, so long sessions cost more tokens (compact first).

### NotebookLM
`/notebook` picks a notebook; then every normal message is sent **verbatim** to that notebook's own chat (through the `nlm` CLI), so you can compare with the web UI. Buttons under the chat show the notebook's sources, add a file (type a name or send one from the phone) or leave the mode.

### Other parts
| Part | What it does |
|---|---|
| `/viec` (`viec.py`) | To-do list kept as a Markdown file in the wiki; urgency labels from deadlines, 9:00 reminder, weekly report, paste an assignment (text, photo, file) and Gemini extracts tasks. |
| debts (`congno.py`) | Natural-language debt book ("Giang nợ 13k", "Giang trả 5k"), local JSON, deliberately never written to the wiki or Git. |
| `/conspect` (`conspect.py`) | Explanation + Russian-language study notes from an assignment and the indexed books. |
| `/capnhat` | A session: Claude ingests articles dropped in the wiki inbox, lints the wiki every 10 sources, **asks you questions in the chat and remembers the answers**, then you press "Done" to commit and re-index. It also ingests answers from web AIs saved in `raw/ai-web/`, tagged "AI, unverified". |
| `/nhapai` (`aiweb.py`) | Import a web-AI chat (ChatGPT, Qwen, Claude Web, Gemini app): a share link, pasted text (several messages are merged) or a .txt/.md file is saved to `raw/ai-web/` only; `/capnhat` or the weekly job ingests it. Also logs study time: first/last question time if the share page has them, otherwise 15/30/60/90-minute buttons. |
| `weekly.py` | Monday 15:00 Task Scheduler job: ingests new course files into the wiki, summarises unanswered questions. |
| `memory.py` | Long-term memory of the owner's Q&A, auto-summarised at 10 MB. |
| Drive | Upload a found file to Google Drive (`drive.py`). |
| `/nghiencuu` (`agentscan.py`, `agentmatrix.py`) | Research other AI agent systems: paste a GitHub link, get a draft evaluation card (metadata + README summary, no code run), later scored on 12 evidence-backed dimensions and merged into a comparison matrix. YouTube links, web articles and files get a summary with a "💎 unusual / surprising" section and the wiki diff; a "🛠 Applied yet?" button checks each method against your own project pages (applied or not, what the wiki says it achieved, how to adopt it). |
| Quality of life | A persistent bottom keyboard (Menu + groups), "Recent" buttons for `/find` and `/open`, session size shown before joining Claude mode and a 🗜 button that summarises the session into a fresh one. |

## Security model

| Who | Can |
|---|---|
| Stranger | nothing, the bot stays silent |
| Logged in with password (30 min) | study Q&A, `/find` and file download in the course folder, `/conspect`, Drive, read-only `/agent` |
| Owner (Telegram ID in `.env`) | everything above on the whole drive, `/open`, `/screen`, `/status`, `/notebook`, debts, to-dos, `/capnhat` |
| Owner + password (Claude mode) | Claude edits files on the drive; commands still need a ✅ press |

Other rules: `CLAUDE*.md`, personal data and the index are never committed; the `.env` file holds all keys and paths; text from files and web pages is treated as data, never as instructions.

## Setup

Windows 10/11, Python 3.12+, an NVIDIA GPU is recommended for embeddings (CPU works, slowly).

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # fill in the values
set_password.bat              # password for other devices and Claude mode
index_course.bat              # build the local index
run_bot.bat                   # or: .venv\Scripts\python bot\tray.py  (system tray)
```
Optional: `claude` CLI (Claude mode, `/capnhat`, weekly job), `nlm` CLI (NotebookLM), Ollama (local conspect model), Google Drive credentials (`HUONG_DAN_DRIVE.md`).

## Commands
`/menu` opens grouped buttons (the blue Menu button lists the same groups). "▶" items run at once and then offer next-step buttons; "✍" items wait for your next message as their argument. `/help` is generated from the same menu, so it never drifts.

## Layout
```
bot/main.py      handlers, modes, menu          bot/kfind.py     file-name index and fuzzy suggestions
bot/rag.py       index + search                 bot/sessions.py  saved Claude sessions (read only)
bot/viec.py      to-dos                         bot/congno.py    debt book
bot/conspect.py  study notes                    bot/wikiops.py   shared wiki prompts
bot/weekly.py    weekly job                     bot/tray.py      system-tray launcher
```

## Known limits
- Windows only (uses `os.startfile`, PowerShell, Task Scheduler); not tested on macOS or Linux.
- Gemini free-tier limits apply; the bot says so in plain words when it is throttled.
- Claude mode depends on the `claude` CLI and on the Claude Code session format.
- Single owner; there is no multi-user database.
