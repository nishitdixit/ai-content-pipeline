"""AI content pipeline: an LLM script writer and an agentic video editor, joined.

    writer  -> plans ideas and writes structured scripts in a channel's voice
    studio  -> remembers footage, directs an edit, renders a vertical short
    bridge  -> turns a written script into the studio's edit request
    events  -> one event bus that the CLI, the JSONL log and the dashboard share
"""

__version__ = "0.2.0"
