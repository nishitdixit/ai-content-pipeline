from content_pipeline.writer.themes import ThemeBank


def test_parses_real_theme_bank(paths):
    bank = ThemeBank(paths.theme_bank)
    by_pillar = {p: [t for t in bank.themes if t.pillar == p] for p in ("P1", "P2", "P3", "P4", "P5")}
    assert all(by_pillar.values())
    assert len(bank.themes) == 72
    gita = bank.by_id(1)
    assert gita.pillar == "P1" and gita.source == "Gita 2.47"
    assert bank.by_id(21).pillar == "P2" and bank.by_id(21).source is None
    # Seasonal and comment tables have no numbered rows and are ignored.
    assert all("Diwali cleaning" not in t.idea for t in bank.themes)


def test_mark_used_round_trips(paths):
    bank = ThemeBank(paths.theme_bank)
    bank.mark_used(bank.by_id(21), "2026-10-12")
    bank.save()
    reloaded = ThemeBank(paths.theme_bank)
    assert reloaded.by_id(21).used == "2026-10-12"
    assert reloaded.by_id(21).idea == bank.by_id(21).idea
    assert len(reloaded.unused("P2")) == len(bank.unused("P2"))


def test_add_appends_to_pillar_table(paths):
    bank = ThemeBank(paths.theme_bank)
    new = bank.add("P1", "Ek nayi | baat", "Gita 3.21")
    other = bank.add("P3", "Kam meetings", "ignored for P3")
    bank.save()
    reloaded = ThemeBank(paths.theme_bank)
    assert reloaded.by_id(new.id).pillar == "P1"
    assert reloaded.by_id(new.id).idea == "Ek nayi / baat"
    assert reloaded.by_id(new.id).source == "Gita 3.21"
    assert reloaded.by_id(other.id).pillar == "P3"
    assert reloaded.by_id(other.id).source is None
    assert len(reloaded.themes) == 74


def test_editorial_notes_are_stripped_but_kept_in_file(paths):
    bank = ThemeBank(paths.theme_bank)
    assert bank.by_id(21).idea == "25 tak settle: who set this deadline?"
    bank.mark_used(bank.by_id(21), "2026-10-12")
    bank.save()
    assert "*(worked example in the script template)*" in paths.theme_bank.read_text()
