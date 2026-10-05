# Thahrav engine

Phase 1 of the [roadmap](../docs/07-roadmap.md): the **script engine**. Each week it picks 7 ideas from the [theme bank](../content/theme-bank.md) following the pillar rotation, writes a Hinglish script for each in your voice, and saves them as markdown files in `content/scripts/`. If Notion is configured, it also creates a page per script in your Content database.

Phases 2 (editing) and 3 (publishing and analytics) are not built yet.

## Setup (one time, ~10 minutes)

```bash
cd ~/project/ai_project/thahrav/engine
cp .env.example .env          # then fill in the keys (see below)
.venv/bin/thahrav doctor      # checks everything
```

The virtualenv (`.venv`) is already created with everything installed. To recreate it:
`python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"`

**Keys in `engine/.env`:**
| Key | Needed? | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | One of these two | console.anthropic.com → API keys |
| `GROQ_API_KEY` | One of these two | console.groq.com → API keys (starts with `gsk_`) |
| `NOTION_API_KEY` | Optional | notion.so/my-integrations → new internal integration |
| `NOTION_CONTENT_DB_ID` | Optional | Created by `thahrav notion-setup` (below) |
| `THAHRAV_HINDI_VERB_FORM` | Set it | `masculine` ("main karta tha") or `feminine` ("main karti thi") |

**Notion (optional):** create a page called "Thahrav" in Notion, share it with your integration (••• → Connections), copy the page ID from its URL, then run:
```bash
.venv/bin/thahrav notion-setup --parent-page <page-id>
```
Paste the printed `NOTION_CONTENT_DB_ID=...` line into `.env`.

## Everyday use

The commands below assume you're in `engine/`. Add `alias thahrav=~/project/ai_project/thahrav/engine/.venv/bin/thahrav` to `~/.zshrc` to run `thahrav` from anywhere.

| Command | What it does |
|---|---|
| `thahrav plan-week` | Writes next Monday-Sunday's 7 scripts. Days that already have a script are skipped. |
| `thahrav plan-week --dry-run` | Shows which ideas would be used, without spending anything |
| `thahrav plan-week --start 2026-10-12 --days 3` | A custom range |
| `thahrav plan-week --force` | Rewrites existing days with the same ideas (and replaces their Notion pages) |
| `thahrav script --theme-id 21 --date 2026-10-08` | One script from a theme bank idea, e.g. a pilot |
| `thahrav script --idea "Exam results aur self-worth" --pillar P2` | One script from your own idea |
| `thahrav themes` | Unused ideas per pillar, and how many weeks they'll last |
| `thahrav suggest-ideas --pillar P3 --count 5` | Adds new ideas to the theme bank (this also happens automatically when a pillar runs out) |
| `thahrav compare --n 5` | Blind test: the same 5 ideas written by Claude and by Groq, labelled A/B (roadmap task 1.4) |
| `thahrav doctor` | Checks setup and shows ideas left |

### How it decides
- **Which pillar:** by weekday. Mon P2, Tue P1, Wed P3, Thu P4, Fri P2, Sat P1, Sun P5 ([content strategy](../docs/02-content-strategy.md)).
- **Which idea:** the first unused idea of that pillar, in theme bank order. To change the order, reorder the rows or write a date in the "Used" column to skip one.
- **After writing:** the idea's "Used" column gets the post date.
- **Writer:** Claude (`claude-opus-5-5`) if `ANTHROPIC_API_KEY` is set, otherwise Groq (decision D11). Override with `--provider`.
- **Voice:** the prompt embeds [the voice & style guide](../docs/03-voice-and-style-guide.md) verbatim, plus the worked example from [the script template](../content/script-template.md). **Editing those docs changes the scripts.** That's the main tuning knob.

### What the engine guarantees
- Output is structured (JSON schema), never parsed from free text.
- Every quote is listed under "Quotes to verify" with a checkbox.
- It never invents your life story. P5 scripts and personal details come back as `[bracketed prompts]` for you to fill in, and the "Before recording" box counts them.
- Sensitive topics get the Tele-MANAS 14416 line added to the close automatically.
- Hashtags are normalised; titles of 60+ characters and scripts outside 110-190 words are flagged (one automatic rewrite is attempted first).
- A failed day doesn't stop the rest of the week. A Notion failure never loses the local file.

## Run it automatically every Saturday night

```bash
mkdir -p logs
cp jobs/com.thahrav.plan-week.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.thahrav.plan-week.plist
```
On Sunday, the week's scripts are waiting for review. Output goes to `logs/plan-week.log`.

## Tests

```bash
.venv/bin/pytest -q
```
The tests run on a temporary copy of `docs/` and `content/` with a fake LLM, so they cost nothing and never change real files.

## Code map
```
src/thahrav/
├── cli.py          # commands
├── plan.py         # weekly planning: pick idea → write → mark used
├── scriptgen.py    # one script: generate, length check + rewrite, house rules, warnings
├── prompts.py      # system prompt (built from the docs) and requests
├── llm.py          # Claude + Groq providers, both returning validated pydantic objects
├── models.py       # output schemas
├── themes.py       # read/update content/theme-bank.md
├── render.py       # markdown script files
├── notion_sync.py  # Notion database + pages
├── pillars.py      # pillars, series, weekly rotation
└── config.py       # paths and .env settings
```
