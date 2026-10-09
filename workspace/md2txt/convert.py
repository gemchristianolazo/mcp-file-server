"""md2txt - convert markdown to plain text."""
import re


def md_to_text(md: str) -> str:
    md = re.sub(r"```.*?```", "", md, flags=re.DOTALL)
    md = re.sub(r"`([^`]*)`", r"\1", md)
    md = re.sub(r"^#{1,6}\s+", "", md, flags=re.MULTILINE)
    return md.strip()
