"""Capture colour profiles reported by metadata; never guess a grading transform from pixels."""
import re


# Explicit versions precede family-only names. A family name is not sufficient
# to select a version-specific grading transform.
_PROFILES = [(re.compile(pattern, re.I), label) for pattern, label in (
    (r'\blog[ _-]?c[ _-]?4\b', 'ARRI LogC4'),
    (r'\blog[ _-]?c[ _-]?3\b', 'ARRI LogC3'),
    (r'\blog[ _-]?c\b', 'ARRI LogC (version unspecified)'),
    (r'\bs[ _-]?log[ _-]?3\b', 'Sony S-Log3'),
    (r'\bs[ _-]?log[ _-]?2\b', 'Sony S-Log2'),
    (r'\bs[ _-]?log\b', 'Sony S-Log (version unspecified)'),
    (r'\b(?:c|canon)[ _-]?log[ _-]?3\b', 'Canon C-Log3'),
    (r'\b(?:c|canon)[ _-]?log[ _-]?2\b', 'Canon C-Log2'),
    (r'\b(?:c|canon)[ _-]?log\b', 'Canon C-Log'),
    (r'\bv[ _-]?log[ _-]?l\b', 'Panasonic V-Log L'),
    (r'\bv[ _-]?log\b', 'Panasonic V-Log'),
    (r'\bf[ _-]?log[ _-]?2\b', 'Fujifilm F-Log2'),
    (r'\bf[ _-]?log\b', 'Fujifilm F-Log'),
    (r'\bn[ _-]?log\b', 'Nikon N-Log'),
    (r'\bd[ _-]?log[ _-]?m\b', 'DJI D-Log M'),
    (r'\bd[ _-]?log\b', 'DJI D-Log'),
    (r'\bapple[ _-]?log[ _-]?2\b', 'Apple Log 2'),
    (r'\bapple[ _-]?log\b', 'Apple Log'),
    (r'\b(?:blackmagic|bmd)[ _-]?film(?:[ _-]?gen(?:eration)?[ _-]?(\d))?\b', 'Blackmagic Film'),
)]


def capture_profile(tech: dict) -> dict:
    """Return a named profile and its exact metadata evidence, or explicitly unknown.

    Reusable on existing technical records so displaying better metadata does
    not invalidate and rerun an entire video analysis pipeline.
    """
    tags = {str(k).lower(): v for k, v in (tech.get('tags') or {}).items()}
    candidates = [('gamma', tech.get('gamma')), ('color_transfer', tech.get('color_transfer'))]
    candidates += [(key, value) for key, value in tags.items()
                   if any(word in key for word in ('gamma', 'transfer', 'captureprofile', 'capture_profile', 'pictureprofile', 'picture_profile'))]
    # Free-text comments can mention conversion *from* Log; keep them as hints,
    # never present them as a confirmed input transform.
    for key, value in candidates:
        if not isinstance(value, str):
            continue
        for pattern, label in _PROFILES:
            match = pattern.search(value)
            if match:
                if label == 'Blackmagic Film' and match.group(1):
                    label += f' Gen {match.group(1)}'
                return {'log_profile_name': label, 'log_profile_source': 'metadata',
                        'log_profile_evidence': {'field': key, 'value': value}, 'log_hint': label}
    hints = ' '.join(str(v) for _, v in candidates if v)
    hints += ' ' + str(tags.get('comment') or '')
    hint = next((label for pattern, label in _PROFILES if pattern.search(hints)), None)
    if not hint and re.search(r'\blog\b', hints, re.I):
        hint = 'Log (unspecified)'
    return {'log_profile_name': None, 'log_profile_source': None, 'log_profile_evidence': None,
            'log_hint': hint or tech.get('log_hint')}
