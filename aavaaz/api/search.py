"""
Full-text search over transcript segments.
"""

import re


def search_segments(
    segments: list[dict],
    query: str,
    case_sensitive: bool = False,
) -> list[dict]:
    """Search through transcript segments for matching text.

    Args:
        segments: List of segment dicts with "text", "start", "end" keys.
        query: Search query string.
        case_sensitive: Whether to match case.

    Returns:
        List of matching segments with match highlights.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)
    results = []
    for seg in segments:
        text = seg.get("text", "")
        matches = list(pattern.finditer(text))
        if matches:
            # use the matched text (preserves casing) and avoids treating the
            # query as a replacement template with backslash escapes
            highlighted = pattern.sub(lambda m: f"**{m.group(0)}**", text)
            results.append(
                {
                    **seg,
                    "highlighted": highlighted,
                    "match_count": len(matches),
                }
            )
    return results
