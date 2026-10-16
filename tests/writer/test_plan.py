from datetime import date

from conftest import FakeProvider

from content_pipeline.writer.plan import next_monday, plan_week
from content_pipeline.writer.render import read_front_matter
from content_pipeline.writer.themes import ThemeBank

MONDAY = date(2026, 10, 12)


def quiet(_msg):
    pass


def test_next_monday():
    assert next_monday(date(2026, 10, 5)) == MONDAY  # a Monday rolls to the following week
    assert next_monday(date(2026, 10, 10)) == MONDAY


def test_rotation_follows_weekday(channel):
    assert [channel.pillar_for(date(2026, 10, 12 + i)) for i in range(7)] == channel.weekly_rotation


def test_plan_week_writes_seven_scripts_and_marks_themes(paths, channel, fake_provider):
    outcomes = plan_week(paths, channel, fake_provider, "sys", MONDAY, log=quiet)
    assert [o.status for o in outcomes] == ["written"] * 7
    files = sorted(paths.scripts_dir.glob("*.md"))
    assert len(files) == 7
    # Monday is P2 and gets the first unused P2 idea (#21); the two P2 days get different ideas.
    assert read_front_matter(files[0])["theme_id"] == "21"
    p2_ids = [read_front_matter(f)["theme_id"] for f in files if read_front_matter(f)["pillar"] == "P2"]
    assert len(set(p2_ids)) == 2
    bank = ThemeBank(paths.theme_bank)
    assert bank.by_id(21).used == "2026-10-12"
    assert len([t for t in bank.themes if t.is_used]) == 7


def test_plan_week_is_idempotent(paths, channel, fake_provider):
    plan_week(paths, channel, fake_provider, "sys", MONDAY, log=quiet)
    calls = len(fake_provider.calls)
    outcomes = plan_week(paths, channel, fake_provider, "sys", MONDAY, log=quiet)
    assert [o.status for o in outcomes] == ["skipped"] * 7
    assert len(fake_provider.calls) == calls


def test_force_rewrites_same_theme(paths, channel, fake_provider):
    plan_week(paths, channel, fake_provider, "sys", MONDAY, days=1, log=quiet)
    plan_week(paths, channel, fake_provider, "sys", MONDAY, days=1, force=True, log=quiet)
    files = list(paths.scripts_dir.glob("*.md"))
    assert len(files) == 1 and read_front_matter(files[0])["theme_id"] == "21"
    assert len(ThemeBank(paths.theme_bank).unused("P2")) == 19


def test_dry_run_changes_nothing(paths, channel):
    before = paths.theme_bank.read_text()
    outcomes = plan_week(paths, channel, None, "sys", MONDAY, dry_run=True, log=quiet)
    assert [o.status for o in outcomes] == ["planned"] * 7
    assert paths.theme_bank.read_text() == before
    assert not paths.scripts_dir.exists() or not list(paths.scripts_dir.glob("*.md"))


def test_suggests_ideas_when_a_pillar_runs_out(paths, channel, fake_provider):
    bank = ThemeBank(paths.theme_bank)
    for t in bank.unused("P5"):
        bank.mark_used(t, "2026-01-01")
    bank.save()
    sunday = date(2026, 10, 18)
    outcomes = plan_week(paths, channel, fake_provider, "sys", sunday, days=1, log=quiet)
    assert outcomes[0].status == "written"
    bank = ThemeBank(paths.theme_bank)
    assert len([t for t in bank.themes if t.pillar == "P5" and t.idea.startswith("New idea")]) == 5


def test_failure_on_one_day_keeps_the_rest(paths, channel):
    class Flaky(FakeProvider):
        def generate(self, system, user, schema):
            if "2026-10-13" in user:
                raise RuntimeError("boom")
            return super().generate(system, user, schema)

    outcomes = plan_week(paths, channel, Flaky(), "sys", MONDAY, days=3, log=quiet)
    assert [o.status for o in outcomes] == ["written", "failed", "written"]
    assert len(list(paths.scripts_dir.glob("*.md"))) == 2


class FakeNotion:
    def __init__(self, fail=False):
        self.fail = fail
        self.pushed = []

    def push(self, result, local_file, replace_page_id=None):
        if self.fail:
            raise RuntimeError("notion down")
        self.pushed.append((local_file, replace_page_id))
        return f"page-{len(self.pushed)}"


def test_notion_mirror_and_replace(paths, channel, fake_provider):
    notion = FakeNotion()
    plan_week(paths, channel, fake_provider, "sys", MONDAY, days=1, notion=notion, log=quiet)
    plan_week(paths, channel, fake_provider, "sys", MONDAY, days=1, notion=notion, force=True, log=quiet)
    assert notion.pushed[0][1] is None and notion.pushed[1][1] == "page-1"
    meta = read_front_matter(next(paths.scripts_dir.glob("*.md")))
    assert meta["notion_page_id"] == "page-2"


def test_notion_failure_still_writes_file(paths, channel, fake_provider):
    outcomes = plan_week(paths, channel, fake_provider, "sys", MONDAY, days=1, notion=FakeNotion(fail=True), log=quiet)
    assert outcomes[0].status == "written" and outcomes[0].path.exists()
