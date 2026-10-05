from datetime import date

from conftest import FakeProvider, make_draft

from thahrav.models import QuoteToVerify, ScriptDraft, json_schema
from thahrav.prompts import build_script_request, build_system_prompt
from thahrav.render import read_front_matter, render_markdown, slugify
from thahrav.scriptgen import HELPLINE_LINE, generate_script


def test_schema_is_strict_and_inlined():
    schema = json_schema(ScriptDraft)
    assert "$defs" not in schema and "$ref" not in str(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["quotes_to_verify"]["items"]["additionalProperties"] is False
    assert set(schema["required"]) == set(ScriptDraft.model_fields)


def test_system_prompt_embeds_voice_guide_and_example(paths):
    prompt = build_system_prompt(paths, "feminine")
    assert "Ruko zara." in prompt  # from the voice guide
    assert "25 tak settle ho jaana chahiye" in prompt  # from the worked example
    assert "sochti thi" in prompt
    assert "{verb_form}" not in prompt and "{example}" not in prompt


def test_p5_request_asks_for_placeholders():
    req = build_script_request(day=date(2026, 10, 18), pillar="P5", idea="Why I started", source=None, series=None)
    assert "Sunday" in req and "bracketed prompts" in req


def test_generate_finalizes_and_warns(paths):
    draft = make_draft(
        sensitive_topic=True,
        relate="Main bhi [apna real example] aisa sochta tha.",
        quotes_to_verify=[QuoteToVerify(quote="Karmanye vadhikaraste", claimed_source="Gita 2.47")],
    )
    result = generate_script(FakeProvider([draft]), "sys", day=date(2026, 10, 12), pillar="P2", idea="x")
    d = result.draft
    assert d.hashtags == ["#hinglish", "#slowliving", "#lifelessons"]
    assert HELPLINE_LINE in d.soft_close
    assert any("placeholder" in w for w in result.warnings)
    assert any("Verify 1 quote" in w for w in result.warnings)


def test_rewrites_once_when_length_is_off():
    provider = FakeProvider([make_draft(words=300), make_draft(words=140)])
    result = generate_script(provider, "sys", day=date(2026, 10, 12), pillar="P2", idea="x")
    assert len(provider.calls) == 2 and "spoken words; the target is 130-160" in provider.calls[1][1]
    assert not any("Spoken length" in w for w in result.warnings)


def test_render_has_front_matter_and_sections():
    result = generate_script(FakeProvider(), "sys", day=date(2026, 10, 12), pillar="P2", idea="25 tak settle",
                             series="Ruko Zara", theme_id=21)
    md = render_markdown(result, notion_page_id="abc")
    for section in ("## Hook (0-3s)", "## Relate", "## Reframe", "## Takeaway", "## Soft close", "## Quotes to verify"):
        assert section in md
    assert "Ruko Zara" in md


def test_front_matter_round_trip(tmp_path):
    result = generate_script(FakeProvider(), "sys", day=date(2026, 10, 12), pillar="P2", idea="x", theme_id=21)
    path = tmp_path / "s.md"
    path.write_text(render_markdown(result, "page-1"))
    meta = read_front_matter(path)
    assert meta["theme_id"] == "21" and meta["notion_page_id"] == "page-1" and meta["status"] == "Drafted"


def test_slugify():
    assert slugify("25 tak settle — ye deadline kisne di?") == "25-tak-settle-ye-deadline-kisne-di"
    assert slugify("ठहराव") == "script"
