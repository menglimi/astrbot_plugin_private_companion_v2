"""Keep speech performance controls out of display and intact across chunks."""

import re


VOICE_TAG_NAME_PATTERN = r"(?:p[\s._-]*c{1,2}[\s._-]*tts|tts)"
VOICE_PROTOCOL_LT = r"(?:<|&lt;|&#0*60;|&#x0*3c;)"
VOICE_PROTOCOL_GT = r"(?:>|&gt;|&#0*62;|&#x0*3e;)"


def canonical_voice_tag(name):
    """Normalize common separator and doubled-letter slips in voice tags."""
    normalized = re.sub(r"[\s._-]+", "", str(name).casefold())
    return "pc_tts" if normalized in {"pctts", "pcctts"} else normalized


_TAG_NAMES = ("whisper", "emphasis", "soft", "fast", "slow", "stress", "forceful",
              "french", "spanish", "german", "japanese", "chinese", "korean", "italian")
_LT = VOICE_PROTOCOL_LT
_GT = VOICE_PROTOCOL_GT
_CONTROLS = re.compile(
    rf"{_LT}\s*(?P<close>/?)\s*(?P<tag>{'|'.join(_TAG_NAMES)})\s*{_GT}"
    r"|(?P<cue>(?<!\[)\[[^\[\]\r\n]+\](?!\]|\s*\())", re.I)


def visible_speech(text):
    """Unwrap known delivery tags and directions in an authored speech span."""
    return _CONTROLS.sub("", text)


def slice_speech(text, start, end):
    """Slice by visible character offsets, balancing active delivery tags."""
    if end <= start:
        return ""
    output, active, pending = [], [], []
    position = cursor = 0
    begun = False

    def begin():
        nonlocal begun
        if not begun:
            output.extend(pending)
            output.extend(f"<{tag}>" for tag in active)
            begun = True

    def plain(run):
        nonlocal position
        left, right = max(start - position, 0), min(end - position, len(run))
        if right > left:
            begin()
            output.append(run[left:right])
        elif run.strip():
            pending.clear()
        position += len(run)

    for match in _CONTROLS.finditer(text):
        plain(text[cursor:match.start()])
        if position >= end:
            break
        tag = match.group("tag")
        closing = bool(match.group("close"))
        if start <= position:
            begin()
        if tag:
            tag = tag.lower()
            if closing:
                if tag in active:
                    # Well-formed input is nested; finish inner tags if a
                    # generated closing tag omitted them.
                    while active:
                        popped = active.pop()
                        if begun:
                            output.append(f"</{popped}>")
                        if popped == tag:
                            break
            else:
                active.append(tag)
                if begun:
                    output.append(f"<{tag}>")
        elif begun:
            output.append(match.group("cue"))
        else:
            pending.append(match.group("cue"))
        cursor = match.end()
    else:
        plain(text[cursor:])
    if begun:
        output.extend(f"</{tag}>" for tag in reversed(active))
    return "".join(output)
