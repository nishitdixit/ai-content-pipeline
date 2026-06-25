from .base import Skill, SkillRegistry
from . import perception, production, render, remote


def default_registry(providers: dict[str, str] | None = None, verbose: bool = True) -> SkillRegistry:
    """Build the registry. `providers` maps capability -> impl name (for
    swapping mock -> hosted -> self-hosted). Remote adapters with their API
    key set are auto-preferred; otherwise the mock impl is used.
    """
    reg = SkillRegistry()
    for skill in (
        perception.SceneDetectSkill(),
        perception.VisualQualitySkill(),
        perception.AudioQualitySkill(),
        perception.SpeechValueSkill(),
        perception.EmotionThemeSkill(),
        perception.EmbedSkill(),
        perception.MockTranscribeSkill(),
        production.ReframeSkill(),
        production.CaptionSkill(),
        production.MusicSkill(),
        render.RenderSkill(),
        # --- remote adapters (active only when their API key is set) ---
        remote.DeepgramTranscribeSkill(),
    ):
        reg.register(skill)

    # explicit providers.json choices first
    for cap, name in (providers or {}).items():
        impl = reg._by_cap.get(cap, {}).get(name)
        if impl is not None and (not getattr(impl, "remote", False) or impl.available()):
            reg.set_preference(cap, name)

    # then auto-prefer any remote skill whose key is present (key wins)
    live = []
    for impls in list(reg._by_cap.values()):
        for s in impls.values():
            if getattr(s, "remote", False) and s.available():
                reg.set_preference(s.capability, s.name)
                live.append(s.info())

    if verbose and live:
        print("  [skills] remote services active:", ", ".join(live))
    return reg


__all__ = ["Skill", "SkillRegistry", "default_registry"]
