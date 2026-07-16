"""Shared helpers for preserving an ordered script rewrite structure."""

from __future__ import annotations

import re
from typing import Iterable


BEAT_MARKER_TEMPLATE = "[[BEAT_{index}]]"
_BEAT_MARKER_RE = re.compile(r"\[\[BEAT_(\d+)\]\]")
_TIMESTAMP_RE = re.compile(
    r"^\s*(?P<time>\d{1,2}[:：]\d{2}(?::\d{2})?)\s*"
    r"(?:[-—~至到]\s*\d{1,2}[:：]\d{2}(?::\d{2})?)?\s*(?P<text>.+?)\s*$"
)
_VISUAL_NOTE_HINTS = (
    "镜头", "画面", "分镜", "字幕", "场景", "特写", "近景", "远景", "中景",
    "俯拍", "拍摄", "拍", "展示", "切换", "推近", "拉远", "定格", "音效",
    "手部", "主播", "出镜", "产品", "包装", "成品", "切面", "用户体验",
    "入嘴", "试吃", "夹馅", "倒出", "捧起", "抓一把", "划开", "拆包", "文字",
)
_PARENTHETICAL_RE = re.compile(r"[（(]([^（）()\n]{1,180})[）)]")
_SEPARATOR_ONLY_RE = re.compile(r"[-—_=~·.。…\s]{3,}")
_UNCLOSED_VISUAL_SUFFIX_RE = re.compile(
    r"[（(]\s*(?:镜头|画面|分镜|字幕|场景|特写|近景|远景|中景|俯拍|拍摄|"
    r"展示|切换|推近|拉远|定格|音效|手部|主播|出镜|一镜到底|成品|包装|"
    r"切面|用户体验|入嘴|试吃|夹馅|倒出|捧起|抓一把|划开|拆包|凸出文字)"
    r"[^\n]*$"
)


def strip_visual_notes(text: str) -> str:
    """Remove camera/action parentheticals while retaining spoken information."""

    def replace(match: re.Match) -> str:
        note = match.group(1)
        if any(hint in note for hint in _VISUAL_NOTE_HINTS):
            return ""
        return match.group(0)

    cleaned = _PARENTHETICAL_RE.sub(replace, text or "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def strip_known_script_prefixes(text: str) -> str:
    """Remove timing/section wrappers and visual notes from one source beat."""

    cleaned = (text or "").strip()
    if _SEPARATOR_ONLY_RE.fullmatch(cleaned):
        return ""
    cleaned = re.sub(r"^\s*【[^】\n]{1,30}】\s*", "", cleaned)
    cleaned = re.sub(r"^\s*[（(][^）)\n]{1,60}[）)]\s*", "", cleaned)
    cleaned = re.sub(
        r"^\s*(?:\d{1,2}[:：]\d{2}(?::\d{2})?|\d{1,2})\s*"
        r"(?:[-—~至到]\s*(?:\d{1,2}[:：]\d{2}(?::\d{2})?|\d{1,2}))?"
        r"\s*[s秒]?\s*[:：-]?\s*",
        "",
        cleaned,
    )
    cleaned = strip_visual_notes(cleaned)
    cleaned = _UNCLOSED_VISUAL_SUFFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if _SEPARATOR_ONLY_RE.fullmatch(cleaned):
        return ""
    return cleaned


def extract_script_beats(script: str, limit: int = 45) -> list[dict]:
    """Extract ordered beats from timestamped, line-based, or paragraph scripts."""

    text = (script or "").strip()
    if not text:
        return []

    beats: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _TIMESTAMP_RE.match(line)
        if match:
            content = match.group("text").strip()
            if content:
                beats.append({
                    "time": match.group("time").replace("：", ":"),
                    "text": content,
                })

    if not beats:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1:
            beats = [{"time": "", "text": line} for line in lines]
        else:
            parts = re.split(r"(?<=[。！？!?；;])\s*", text)
            beats = [{"time": "", "text": part} for part in parts if part.strip()]

    normalized = []
    for beat in beats:
        content = strip_known_script_prefixes(beat["text"])
        if content:
            normalized.append({"time": beat.get("time", ""), "text": content})
        if len(normalized) >= limit:
            break
    return normalized


def format_indexed_script_beats(beats: Iterable[dict]) -> str:
    lines = []
    for index, beat in enumerate(beats, 1):
        marker = BEAT_MARKER_TEMPLATE.format(index=index)
        timestamp = f" [{beat['time']}]" if beat.get("time") else ""
        lines.append(f"{marker}{timestamp} {beat.get('text', '').strip()}")
    return "\n".join(lines)


def parse_indexed_rewrite(text: str, expected_count: int) -> tuple[list[str], list[str]]:
    """Parse model-only beat markers and report structural protocol violations."""

    value = (text or "").strip()
    matches = list(_BEAT_MARKER_RE.finditer(value))
    reasons: list[str] = []
    expected = list(range(1, expected_count + 1))
    actual = [int(match.group(1)) for match in matches]
    if actual != expected:
        reasons.append("表达点序号缺失、重复或顺序错误")

    if matches and value[:matches[0].start()].strip():
        reasons.append("表达点序号前存在额外内容")

    segments = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        segments.append(value[match.end():end].strip())
    if matches and any(not segment for segment in segments):
        reasons.append("存在空表达点")
    return segments, list(dict.fromkeys(reasons))
