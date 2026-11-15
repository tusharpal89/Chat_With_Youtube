def format_timestamp(seconds: float) -> str:
    """Convert seconds to a human-readable MM:SS or H:MM:SS string."""
    total = int(max(0, seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
