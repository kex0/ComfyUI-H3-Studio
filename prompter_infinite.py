"""H3 Studio Local Infinite Prompter: dump + plan → labeled Ref2VA clips."""

from __future__ import annotations

import hashlib
import os
import re

from .chain_inputs import MAX_SEGMENTS
from .pack import format_builder_dump, parse_prompt_citations
from .prompt_document import assemble_auto_chain_document
from .prompter_llama import (
    CATALOG_LABEL, LOCAL_GGUF_LABEL, find_llama_cli, find_llama_server,
    llama_cli_complete, LlamaServerSession, model_combo_values, resolve_gguf,
    unload_comfy_models,
)

SECTION_HEADS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)
_ITEM_LINE = re.compile(
    r"^(Model|Picture|Video|Audio)\s+(\d+)\s*:\s*(.*)$", re.I | re.M,
)
_DURATION = re.compile(r"^duration:\s*([\d.]+)\s*s?\s*$", re.I | re.M)
_SEGMENTS = re.compile(r"^segments:\s*(\d+)\s*$", re.I | re.M)
_CLIP_LABEL = re.compile(r"^\*\*[^*]+\*\*\s*", re.M)
_T2VA_LOCK = re.compile(
    r"at\s+0\.00\s+seconds.{0,80}fully\s+referenced", re.I | re.S,
)
_FIRST_FRAME_ROW = re.compile(
    r"<Picture\s+(\d+)>\s+is the first frame of \[Shot 1\]", re.I,
)
_SYSTEM_PATH = os.path.join(os.path.dirname(__file__), "prompts", "infinite_system.txt")


def load_system_prompt() -> str:
    with open(_SYSTEM_PATH, encoding="utf-8") as handle:
        return handle.read().strip()


def parse_builder_dump(text: str) -> dict:
    raw = str(text or "")
    plan = ""
    plan_match = re.search(r"^plan:\s*$", raw, re.I | re.M)
    inventory_text = raw
    if plan_match:
        inventory_text = raw[:plan_match.start()].rstrip()
        plan = raw[plan_match.end():].strip()
    else:
        same = re.search(r"^plan:\s+(.+)$", raw, re.I | re.M)
        if same:
            inventory_text = (raw[:same.start()] + raw[same.end():]).rstrip()
            plan = same.group(1).strip()
    items = {"models": [], "pictures": [], "videos": [], "audios": []}
    first_frame = None
    for kind, raw_n, desc in _ITEM_LINE.findall(inventory_text):
        n = int(raw_n)
        key = kind.lower() + "s"
        marked = desc.rstrip().endswith("(first frame)")
        entry = {"index": n, "description": desc.strip(), "first_frame": marked}
        if marked and kind.lower() == "picture":
            first_frame = n
            entry["description"] = re.sub(r"\s*\(first frame\)\s*$", "", desc.strip())
        items[key].append(entry)
    dur_match = _DURATION.search(inventory_text)
    seg_match = _SEGMENTS.search(inventory_text)
    return {
        "models": items["models"],
        "pictures": items["pictures"],
        "videos": items["videos"],
        "audios": items["audios"],
        "first_frame": first_frame,
        "duration": float(dur_match.group(1)) if dur_match else None,
        "segments": int(seg_match.group(1)) if seg_match else None,
        "plan": plan,
        "raw": raw.strip(),
    }


def dump_indices(inventory: dict) -> dict:
    return {
        "pictures": [int(item["index"]) for item in inventory.get("pictures") or []],
        "videos": [int(item["index"]) for item in inventory.get("videos") or []],
        "audios": [int(item["index"]) for item in inventory.get("audios") or []],
        "models": [int(item["index"]) for item in inventory.get("models") or []],
    }


def clip_role(index: int, segments: int, loop=False, is_loop=False) -> str:
    if is_loop:
        return "Loop"
    if index == 1:
        return "Start" if int(segments) > 1 or loop else "Start (final)"
    if index == int(segments):
        return "Finish"
    return "Continue"


def clip_heading(index: int, role: str) -> str:
    if role == "Loop":
        return "**Loop — return to Clip 1**"
    if role == "Start (final)":
        return "**Clip 1 — Start (final)**"
    return f"**Clip {int(index)} — {role}**"


def strip_generated_body(text: str) -> str:
    body = str(text or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:text|markdown)?\s*", "", body)
        body = re.sub(r"\s*```\s*$", "", body)
    body = _CLIP_LABEL.sub("", body).strip()
    return body.strip()


def validate_clip_prompt(body: str, inventory: dict, clip_index: int, is_loop=False) -> list[str]:
    text = str(body or "")
    issues = []
    for head in SECTION_HEADS:
        if not re.search(rf"^{re.escape(head)}\s*:", text, re.I | re.M):
            issues.append(f"missing section {head}")
    cites = parse_prompt_citations(text)
    allowed = dump_indices(inventory)
    for kind, used in cites.items():
        legal = set(allowed.get(kind) or [])
        extra = [n for n in used if n not in legal]
        if extra:
            issues.append(f"unknown {kind} tags {extra}; dump has {sorted(legal)}")
    first_n = inventory.get("first_frame")
    first_row = _FIRST_FRAME_ROW.search(text)
    if first_n and int(clip_index) == 1 and not is_loop:
        if not first_row:
            issues.append(
                f"clip 1 must include '<Picture {first_n}> is the first frame of [Shot 1]'"
            )
        elif int(first_row.group(1)) != int(first_n):
            issues.append(f"first-frame row must cite dump Picture {first_n}")
    elif first_row:
        if int(clip_index) == 1 and not is_loop:
            issues.append("no dump picture is marked first frame")
        else:
            issues.append("Continue/Finish/Loop must not reopen the first-frame still")
    if _T2VA_LOCK.search(text):
        issues.append("do not write the T2VA lock sentence 'at 0.00 seconds … fully referenced'")
    return issues


def _progress(unique_id, text):
    from .png_sequence import send_node_progress
    send_node_progress(unique_id, text)


def _dump_text(dump, pack) -> str:
    text = str(dump or "").strip()
    if text:
        return text
    if isinstance(pack, dict) and (pack.get("models") or pack.get("pictures")
                                   or pack.get("videos") or pack.get("audios")
                                   or pack.get("plan")):
        return format_builder_dump(
            pack.get("models") or [],
            pack.get("pictures") or [],
            pack.get("videos") or [],
            pack.get("audios") or [],
            plan=pack.get("plan") or "",
        )
    raise ValueError("h3_studio: paste a Builder dump or connect pack")


def _user_turn(inventory, plan, index, role, duration, previous_body, is_loop=False) -> str:
    if is_loop:
        job = f"Write the body for the Loop clip, duration {float(duration):.2f}s."
    else:
        job = f"Write the body for clip {index} ({role}), duration {float(duration):.2f}s."
    parts = [
        "Builder dump:",
        inventory["raw"] or "(empty dump)",
        "",
        "User plan:",
        str(plan or "").strip() or "(no extra plan)",
        "",
        job,
    ]
    if is_loop:
        parts.append(
            "Continue from the last story clip toward clip 1's opening action already in motion."
        )
    first_n = inventory.get("first_frame")
    if first_n and int(index) == 1 and not is_loop:
        parts.append(
            f"Dump Picture {first_n} is marked (first frame). Shot 1 must match that still "
            f"and include '<Picture {first_n}> is the first frame of [Shot 1]'."
        )
    elif first_n:
        parts.append(
            f"Do not reopen Picture {first_n} as a first-frame lock. Continue from the "
            "previous clip's last visible state."
        )
    if previous_body:
        parts.extend(["", "Previous clip body:", previous_body])
    parts.append("Output only the six-section body.")
    return "\n".join(parts)


def _flatten_cli_messages(messages) -> tuple[str, str]:
    system = ""
    chunks = []
    for msg in messages:
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if role == "system" and not system:
            system = content
        elif role == "user":
            chunks.append(content)
        elif role == "assistant":
            chunks.append("Previous draft:\n" + content)
    return system, "\n\n".join(chunks)


def generate_clip_bodies(inventory, plan, segments, duration, loop, chat_fn) -> tuple[list[tuple[str, str, str]], list[str]]:
    system = load_system_prompt()
    jobs = []
    for i in range(1, int(segments) + 1):
        jobs.append((i, clip_role(i, segments, loop=loop), False))
    if loop:
        jobs.append((int(segments), "Loop", True))
    bodies = []
    notes = []
    previous = ""
    for index, role, is_loop in jobs:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": _user_turn(
                inventory, plan, index, role, duration, previous, is_loop=is_loop,
            )},
        ]
        raw = chat_fn(messages)
        body = strip_generated_body(raw)
        issues = validate_clip_prompt(body, inventory, index, is_loop=is_loop)
        if issues:
            repair = (
                "Repair the draft. Keep the six-section Ref2VA body. Fix:\n- "
                + "\n- ".join(issues)
            )
            messages.extend([
                {"role": "assistant", "content": body},
                {"role": "user", "content": repair},
            ])
            body = strip_generated_body(chat_fn(messages))
            leftover = validate_clip_prompt(body, inventory, index, is_loop=is_loop)
            if leftover:
                notes.append(f"clip {index} ({role}): " + "; ".join(leftover))
        heading = clip_heading(index, role)
        bodies.append((heading, body, role))
        if not is_loop:
            previous = body
    return bodies, notes


class H3StudioLocalInfinitePrompter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "dump": ("STRING", {
                    "multiline": True, "default": "",
                    "tooltip": (
                        "Paste the Builder Copy pack summary. That dump is the only legal "
                        "Model / Picture / Video / Audio inventory."
                    ),
                }),
                "plan": ("STRING", {
                    "multiline": True, "default": "",
                    "tooltip": "Story plan for the Auto Chain clips. Follow this; do not invent a morph plot.",
                }),
                "model": (model_combo_values(), {
                    "default": CATALOG_LABEL,
                    "tooltip": (
                        "Qwen3.8-27B-Uncensored Q4_K_M looks under models/LLM. Local GGUF uses "
                        "gguf_path. Scanned files appear as local:relative/path.gguf."
                    ),
                }),
                "segments": ("INT", {
                    "default": 2, "min": 1, "max": MAX_SEGMENTS, "step": 1,
                    "tooltip": "Story clip count. Loop adds one extra prompt after these.",
                }),
                "duration": ("FLOAT", {
                    "default": 10.0, "min": 2.0, "max": 15.0, "step": 0.1,
                    "tooltip": "Requested length of each clip in seconds.",
                }),
                "loop": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Also write a Loop prompt that returns to clip 1's opening already in motion.",
                }),
                "allow_download": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "If the catalog GGUF is missing, download it into models/LLM from Hugging Face "
                        "(~16 GB). Off raises instead."
                    ),
                }),
                "n_ctx": ("INT", {
                    "default": 16384, "min": 2048, "max": 131072, "step": 256,
                    "tooltip": "llama.cpp context length.",
                }),
                "n_gpu_layers": ("INT", {
                    "default": 99, "min": 0, "max": 999, "step": 1,
                    "tooltip": "GPU layers for llama-server / llama-cli. 99 offloads the whole 27B Q4.",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.6, "min": 0.0, "max": 2.0, "step": 0.05,
                    "tooltip": "Sampling temperature for each clip completion.",
                }),
            },
            "optional": {
                "pack": ("H3_STUDIO_PACK", {
                    "tooltip": "Optional Builder pack. Used only when dump is empty.",
                }),
                "gguf_path": ("STRING", {
                    "default": "",
                    "tooltip": "Absolute path or filename under models/LLM. Used when model is Local GGUF.",
                }),
                "llama_server": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "Path to llama-server. Empty auto-finds H3_STUDIO_LLAMA_SERVER, PATH, "
                        "llama-cli sibling, or ComfyUI/user/**/llama-server."
                    ),
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("prompts", "clip_count", "notes")
    OUTPUT_TOOLTIPS = (
        "One H3 Studio prompt for Auto Chain. Shared subject_definitions plus ## Clip sections.",
        "Number of generated prompt bodies (N, or N+1 when loop is on).",
        "Model path, binary used, and leftover validator notes after one repair pass.",
    )
    FUNCTION = "generate_prompts"
    CATEGORY = "H3 Studio"
    DESCRIPTION = (
        "Start local llama.cpp on a catalog or local GGUF, write Auto Chain Ref2VA prompts "
        "from a Builder dump plus plan, then stop the server. Queue without H3 loaded. "
        "27B Q4_K_M and H3 cannot share 32 GB VRAM."
    )

    @classmethod
    def IS_CHANGED(cls, dump="", plan="", model=CATALOG_LABEL, segments=2, duration=10.0,
                   loop=False, allow_download=False, n_ctx=16384, n_gpu_layers=99,
                   temperature=0.6, pack=None, gguf_path="", llama_server="", **_kwargs):
        pack_dump = ""
        if isinstance(pack, dict):
            pack_dump = format_builder_dump(
                pack.get("models") or [], pack.get("pictures") or [],
                pack.get("videos") or [], pack.get("audios") or [],
                plan=pack.get("plan") or "",
            )
        raw = "|".join((
            str(dump or ""), str(plan or ""), str(model or ""), str(int(segments)),
            f"{float(duration):.3f}", str(bool(loop)), str(bool(allow_download)),
            str(int(n_ctx)), str(int(n_gpu_layers)), f"{float(temperature):.3f}",
            str(gguf_path or ""), str(llama_server or ""), pack_dump,
        ))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def generate_prompts(self, dump, plan, model, segments, duration, loop, allow_download,
                         n_ctx, n_gpu_layers, temperature, pack=None, gguf_path="",
                         llama_server="", unique_id=None):
        segments = max(1, min(int(MAX_SEGMENTS), int(segments)))
        duration = float(duration)
        loop = bool(loop)
        clip_total = segments + (1 if loop else 0)
        inventory = parse_builder_dump(_dump_text(dump, pack))
        if not inventory["raw"]:
            raise ValueError("h3_studio: paste a Builder dump or connect pack")
        plan = str(plan or "").strip() or str(inventory.get("plan") or "").strip()

        def progress(text):
            _progress(unique_id, text)

        gguf = resolve_gguf(
            model, gguf_path=gguf_path, allow_download=bool(allow_download), progress=progress,
        )
        session = None
        server_exe = None
        cli_exe = None
        try:
            server_exe = find_llama_server(llama_server)
        except RuntimeError:
            if clip_total > 1:
                raise RuntimeError(
                    "h3_studio: llama-server is required for more than one clip. "
                    "Install llama.cpp so llama-server is on PATH, or set llama_server."
                )
            cli_exe = find_llama_cli()

        def chat(messages):
            if session is not None:
                return session.chat(messages, temperature=temperature)
            system, user = _flatten_cli_messages(messages)
            return llama_cli_complete(
                cli_exe, gguf, system, user, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers,
                temperature=temperature,
            )

        unload_comfy_models()
        try:
            if server_exe:
                progress(f"Starting llama-server on 127.0.0.1 ({os.path.basename(gguf)})")
                session = LlamaServerSession(
                    server_exe, gguf, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers,
                )
                session.start()
            else:
                progress(f"llama-cli one-shot for clip 1 ({os.path.basename(gguf)})")
            bodies, issues = generate_clip_bodies(
                inventory, plan, segments, duration, loop, chat,
            )
        finally:
            if session is not None:
                session.close()
                progress("Stopped llama-server")

        prompts = assemble_auto_chain_document(
            duration, segments, loop,
            [(role, body, role == "Loop") for _heading, body, role in bodies],
        )
        used = server_exe or cli_exe
        note_lines = [
            f"model={gguf}",
            f"binary={used}",
            f"clips={len(bodies)}",
        ]
        note_lines.extend(issues)
        return (prompts, len(bodies), "\n".join(note_lines))
