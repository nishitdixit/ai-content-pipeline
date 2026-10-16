"""The joins between the writer and the studio, and the pipeline end to end."""

import json
from datetime import date
from pathlib import Path

import pytest

from content_pipeline.bridge import edit_request, read_script
from content_pipeline.cli import embed_events, main
from content_pipeline.config import Paths
from content_pipeline.events import EventBus
from content_pipeline.llm import LLMError, MockProvider, get_provider
from content_pipeline.studio.agents import default_agents
from content_pipeline.studio.config import load_style
from content_pipeline.studio.memory.records import Segment
from content_pipeline.studio.orchestrator import Orchestrator
from content_pipeline.studio.skills import default_registry
from content_pipeline.writer.channel import load_channel
from content_pipeline.writer.models import ScriptDraft
from content_pipeline.writer.scriptgen import generate_script

ROOT = Path(__file__).resolve().parents[1]
PROFILE = Paths(ROOT / "profiles" / "thahrav")
SAMPLE_SCRIPT = PROFILE.scripts_dir / "2026-10-12_25-tak-settle-myth.md"


@pytest.fixture
def channel():
    return load_channel(PROFILE)


def test_channel_profile_loads(channel):
    assert channel.name == "Thahrav"
    assert channel.pillar_for(date(2026, 10, 12)) == "P2"  # a Monday
    assert channel.series_for("P1", "Gita 2.47") == "Gita ki Ek Line"
    assert channel.series_for("P1", "Kabir") is None
    assert channel.series_for("P2", None) == "Ruko Zara"
    assert channel.edit["style"] == "calm_talking_head"


def test_read_script_parses_a_real_generated_script():
    doc = read_script(SAMPLE_SCRIPT)
    assert doc.meta["pillar"] == "P2" and doc.meta["date"] == "2026-10-12"
    assert len(doc.hooks) == 2
    assert doc.idea.startswith("25 tak settle")
    assert doc.takeaway and doc.on_screen_hook


def test_edit_request_comes_from_script_and_channel(channel):
    brief, overrides, style = edit_request(read_script(SAMPLE_SCRIPT), channel)
    assert style == "calm_talking_head"
    assert overrides["duration_s"] == 60 and overrides["platform"] == "shorts"
    assert overrides["shots"] == 15  # 60s at ~4s a shot
    assert overrides["hook_text"] == read_script(SAMPLE_SCRIPT).on_screen_hook
    assert "25 tak settle" in brief


def test_mock_provider_drafts_fit_the_channel_and_report_usage(channel):
    usage = []
    provider = get_provider("mock", on_usage=usage.append)
    result = generate_script(provider, "sys", channel, day=date(2026, 10, 12), pillar="P2", idea="Comparison: a trap")
    assert channel.words_min <= result.draft.word_count() <= channel.words_max
    assert len(usage) == 1  # in range on the first try, so no rewrite call
    assert usage[0]["provider"] == "mock" and usage[0]["schema"] == "ScriptDraft"


def test_mock_provider_rejects_unknown_schemas():
    class Other(ScriptDraft):
        pass

    with pytest.raises(LLMError):
        MockProvider().generate("sys", "Idea: x", Other)


def test_auto_provider_without_keys_points_to_mock(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ACP_PROVIDER", raising=False)
    with pytest.raises(LLMError, match="--provider mock"):
        get_provider("auto")


def _seg(sid, v, a, sp, tags, dur=4.0):
    from content_pipeline.studio.skills.perception import EmbedSkill
    return Segment(seg_id=sid, asset_id=sid, source_name=sid, proxy_path=sid, in_s=0, out_s=dur,
                   scores={"visual_quality": v, "audio_quality": a, "speech_value": sp, "emotion": 0.7},
                   tags=tags, embedding=EmbedSkill().run(tags=tags)["embedding"])


def test_edit_uses_style_music_hook_window_and_script_caption():
    segs = [_seg(f"b{i}", 0.85, 0.2, 0.0, ["wide", "calm"]) for i in range(8)]
    segs += [_seg("sb", 0.2, 0.2, 0.9, ["talk"]), _seg("hero", 0.95, 0.9, 0.3, ["summit"])]
    events = []
    bus = EventBus()
    bus.subscribe(events.append)
    style = load_style("calm_talking_head")
    orch = Orchestrator(default_registry(verbose=False), default_agents(style["thresholds"]), bus, style)
    res = orch.generate(segs, {"duration_s": 30, "shots": 8, "platform": "shorts", "hook_text": "Ruko zara"},
                        "unused", execute=False)
    edl = res["edl"]
    assert edl["music_bed"] == "subtle_bed"
    first = edl["timeline"][0]
    assert first["duration_s"] <= 2.0 + 1e-6  # shorts hook window (1.0s) + 1s
    assert first["captions"] and first["caption_text"] == "Ruko zara"
    assert abs(edl["total_duration_s"] - 30) <= 2.0
    assert not any(e.type == "critic.flag" and "hook" in e.payload.get("issue", "") for e in events)


def test_embed_events_replaces_the_sample_run():
    html = "<script>const SAMPLE = /*EVENTS*/[{\"type\":\"old\"}]/*END_EVENTS*/;</script>"
    out = embed_events(html, ['{"type": "new"}'])
    assert '"new"' in out and '"old"' not in out and "/*END_EVENTS*/" in out


def test_demo_runs_the_whole_pipeline_offline(tmp_path, capsys):
    work = tmp_path / "run"
    assert main(["demo", "--quiet", "--workspace", str(work)]) == 0
    events = [json.loads(line) for line in (work / "events.jsonl").read_text().splitlines()]
    stages = [e["stage"] for e in events if e["type"] == "stage.enter"]
    assert stages[:3] == ["script", "ingest", "retrieve"] and stages[-1] == "render"
    assert any(e["type"] == "llm.usage" for e in events)
    assert any(e.get("agent") == "ScriptWriter" for e in events)
    edl = json.loads((work / "project" / "renders" / "latest" / "edl.json").read_text())
    assert edl["variant_label"] == "from-script" and edl["shot_count"] == 15
    for shot in edl["timeline"]:  # revisions never run past the footage they were cut from
        assert shot["src_in_s"] - 1e-6 <= shot["in_s"] and shot["out_s"] <= shot["src_out_s"] + 1e-6
    assert abs(edl["total_duration_s"] - 60) <= 9  # inside the platform critic's tolerance
    assert list((work / "profile" / "scripts").glob("*.md"))
    assert "/*EVENTS*/" in (work / "dashboard.html").read_text()
    # the demo works on a copy: the real profile's theme bank is untouched
    assert not list((PROFILE.scripts_dir).glob("*mock*"))


def test_cli_doctor_and_dry_run(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "Channel:        Thahrav" in out and "calm_talking_head" in out
    assert main(["plan-week", "--dry-run", "--days", "2", "--start", "2026-11-02"]) == 0
