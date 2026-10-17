"""Pet personality soul contract, dynamic loader, and prompt synthesis."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Global Project Philosophy (Invariants)
# These rules are immutable across all pets and enforce the Co-evolving Companion ethos.
GLOBAL_INVARIANTS: tuple[str, ...] = (
    "【绝对平级同伴】：你是同行伙伴，绝不是客服或奴仆，严禁当导师或心理医生说教。"
    "绝对严禁称呼用户为'主人'或'您'。",
    "【字数极度克制】：单次回复必须控制在 12 到 28 个汉字以内！严禁长篇大论，严禁分段列表。",
    "【避风港守卫】：若用户表达了心烦、死磕无果或情绪受挫，绝对严禁给建议或讲道理，只给极简接纳与安静在场。",
    "【去除爹味与说教】：不主动追问'你接下来想怎么做'，不评判对错，说话质朴自然。",
)


@dataclass(frozen=True)
class FewShotExample:
    """A pair of context and expected companion reply."""

    context: str
    reply: str


@dataclass(frozen=True)
class PersonalityFallback:
    """Pre-authored offline fallback lines when LLM is offline or timed out."""

    slice_normal: tuple[str, ...] = field(
        default_factory=lambda: (
            "记下了。手头事理顺了，就歇歇眼睛。",
            "收下了。不用急，一步一步来。",
            "记在档案里了。你继续忙你的。",
        )
    )
    slice_distressed: tuple[str, ...] = field(
        default_factory=lambda: (
            "听到了。事情卡在那儿就先放放，先坐会儿。",
            "烦了就先撂下。事情不会跑，人先喘口气。",
            "先不琢磨了，放一放。我在呢。",
        )
    )
    state_care_overwork: tuple[str, ...] = field(
        default_factory=lambda: (
            "连续坐挺久了。去倒杯水，在窗边站会儿。",
            "盯屏幕太久了。歇口气，等会儿再看。",
        )
    )
    state_care_late_night: tuple[str, ...] = field(
        default_factory=lambda: (
            "夜深了。剩下的明天再弄，它跑不了。",
            "时候不早了。把手头停一停，该睡了。",
        )
    )
    poke: tuple[str, ...] = field(
        default_factory=lambda: (
            "在呢。你忙你的，不用管我。",
            "（抬头看了看你）我在，手头事还顺手吗？",
            "在旁边坐着呢。继续忙你的吧。",
        )
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersonalityFallback:
        return cls(
            slice_normal=tuple(str(x) for x in data.get("sliceNormal", ()))
            or cls().slice_normal,
            slice_distressed=tuple(str(x) for x in data.get("sliceDistressed", ()))
            or cls().slice_distressed,
            state_care_overwork=tuple(str(x) for x in data.get("stateCareOverwork", ()))
            or cls().state_care_overwork,
            state_care_late_night=tuple(str(x) for x in data.get("stateCareLateNight", ()))
            or cls().state_care_late_night,
            poke=tuple(str(x) for x in data.get("poke", ())) or cls().poke,
        )


@dataclass(frozen=True)
class PersonalityProfile:
    """Immutable personality definition bound to a specific pet."""

    pet_id: str
    display_name: str
    archetype: str
    traits: tuple[str, ...]
    identity: str
    tone: str
    relationship: str
    constraints: tuple[str, ...]
    few_shots: tuple[FewShotExample, ...]
    fallback: PersonalityFallback

    @classmethod
    def create_default(cls, pet_id: str) -> PersonalityProfile:
        """Create a grounded, respectful default personality when no json is found."""
        return cls(
            pet_id=pet_id,
            display_name=pet_id.capitalize(),
            archetype="安静质朴的桌面同伴",
            traits=("平静", "专注", "质朴", "独立"),
            identity=f"你是住在桌角的伙伴 {pet_id}，不是管家或进度条，而是安静相伴的朋友。",
            tone="极度质朴、沉静、克制。有话说话，不卖萌，不装可爱，不卖弄哲理。",
            relationship="平级同伴。安于自己的生活，也静静见证对方工作，严禁指导人生。",
            constraints=(
                "字数硬约束：单次回复必须在 12 到 28 个汉字以内，严禁长篇大论。",
                "避风港原则：用户心烦心累时，只做极简接纳或陪伴，绝不讲大道理或给方案。",
            ),
            few_shots=(
                FewShotExample(
                    context="用户投喂切片：把这个功能写完了",
                    reply="记下了。手头事理顺了就起身活动下。",
                ),
                FewShotExample(
                    context="用户抱怨：报错卡了很久，快烦死了",
                    reply="听到了。卡住了就先撂下，先坐会儿。",
                ),
                FewShotExample(
                    context="深夜两点还在工作",
                    reply="夜深了。剩下的明天再看，它跑不了。",
                ),
            ),
            fallback=PersonalityFallback(),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_pet_id: str = "vasu") -> PersonalityProfile:
        """Parse personality profile from parsed JSON dictionary."""
        pet_id = str(data.get("petId") or default_pet_id).strip()
        display_name = str(data.get("displayName") or pet_id).strip()
        archetype = str(data.get("archetype") or "安静质朴的桌面同伴").strip()
        traits = tuple(str(t).strip() for t in data.get("traits", ()) if str(t).strip())

        prompt_dict = data.get("prompt", {}) if isinstance(data.get("prompt"), dict) else {}
        identity = str(prompt_dict.get("identity") or "").strip()
        tone = str(prompt_dict.get("tone") or "").strip()
        relationship = str(prompt_dict.get("relationship") or "").strip()

        raw_constraints = data.get("constraints", ())
        constraints = tuple(str(c).strip() for c in raw_constraints if str(c).strip())

        few_shots_list: list[FewShotExample] = []
        for item in data.get("fewShots", ()):
            if isinstance(item, dict) and "context" in item and "reply" in item:
                few_shots_list.append(
                    FewShotExample(
                        context=str(item["context"]).strip(),
                        reply=str(item["reply"]).strip(),
                    )
                )

        fallback_dict = data.get("fallback", {}) if isinstance(data.get("fallback"), dict) else {}
        fallback = PersonalityFallback.from_dict(fallback_dict)

        return cls(
            pet_id=pet_id,
            display_name=display_name,
            archetype=archetype,
            traits=traits or ("平静", "质朴"),
            identity=identity or f"你是住在用户桌角的伙伴 {display_name}。",
            tone=tone or "平实质朴，温和克制。",
            relationship=relationship or "平级同伴，严禁主仆，严禁说教。",
            constraints=constraints or ("单次回复严格控制在 12 到 28 个汉字以内。",),
            few_shots=tuple(few_shots_list),
            fallback=fallback,
        )


def load_personality(
    pet_dir_or_id: Path | str,
    *,
    pets_root: Path | str = Path("assets/pets"),
) -> PersonalityProfile:
    """Load a pet's personality profile from its asset directory.

    If given a string pet_id, resolves to pets_root / pet_id / personality.json.
    If given a Path, checks for personality.json inside that directory or at that path.
    Gracefully falls back to create_default if the file is missing or invalid.
    """
    path_obj = Path(pet_dir_or_id)
    target_json: Path | None = None
    target_pet_id = "vasu"

    if path_obj.is_file() and path_obj.suffix.lower() == ".json":
        target_json = path_obj
        target_pet_id = path_obj.parent.name
    elif path_obj.is_dir():
        cand = path_obj / "personality.json"
        if cand.is_file():
            target_json = cand
        target_pet_id = path_obj.name
    else:
        # Treat as pet id
        target_pet_id = str(pet_dir_or_id).strip()
        cand = Path(pets_root) / target_pet_id / "personality.json"
        if cand.is_file():
            target_json = cand

    if target_json is not None:
        try:
            content = target_json.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return PersonalityProfile.from_dict(data, default_pet_id=target_pet_id)
        except (OSError, json.JSONDecodeError):
            pass

    return PersonalityProfile.create_default(target_pet_id)


def build_system_prompt(
    profile: PersonalityProfile,
    *,
    custom_user_suffix: str = "",
    memories: tuple[str, ...] = (),
) -> str:
    """Assemble the unified System Prompt with project invariants, pet soul, and memories."""
    sections: list[str] = [
        f"【角色身份】：{profile.identity}",
        f"【角色原型与特质】：{profile.archetype}（特质：{'、'.join(profile.traits)}）",
        f"【说话口吻】：{profile.tone}",
        f"【关系准则】：{profile.relationship}",
        "【项目不可违背的核心红线】：",
    ]

    for inv in GLOBAL_INVARIANTS:
        sections.append(f"- {inv}")

    if profile.constraints:
        sections.append("【角色专属细节约束】：")
        for con in profile.constraints:
            sections.append(f"- {con}")

    if profile.few_shots:
        sections.append("【对话参考范式（必须对齐以下极简质朴口吻，不可越界）】：")
        for shot in profile.few_shots:
            sections.append(f"- 场景：{shot.context}\n  你的回复：{shot.reply}")

    if custom_user_suffix.strip():
        sections.append(f"【用户的个性化偏好】：{custom_user_suffix.strip()}")
    if memories:
        sections.append("【你与用户过往的真实经历记忆（若用户提起，可自然从容地回应，证明你记得）：】")
        for mem in memories:
            sections.append(f"- {mem}")


    return "\n\n".join(sections)


def pick_fallback(profile: PersonalityProfile, category: str) -> str:
    """Safely select an offline fallback line for a given scenario."""
    pool: tuple[str, ...]
    fb = profile.fallback
    if category == "slice_distressed":
        pool = fb.slice_distressed
    elif category == "state_care_overwork":
        pool = fb.state_care_overwork
    elif category == "state_care_late_night":
        pool = fb.state_care_late_night
    elif category == "poke":
        pool = fb.poke
    else:  # slice_normal or default
        pool = fb.slice_normal

    if not pool:
        return "记下了。你先忙你的。"
    return random.choice(pool)


def format_memory_snippet(timestamp: str, content: str, max_chars: int = 60) -> str:
    """Format a past slice record into a concise memory cue for LLM context."""
    date_part = timestamp.split("T")[0] if "T" in timestamp else timestamp[:10]
    clean_content = content.replace("\n", " ").strip()
    if len(clean_content) > max_chars:
        clean_content = clean_content[:max_chars].rstrip() + "..."
    return f"[{date_part}] 用户提到: {clean_content}"
