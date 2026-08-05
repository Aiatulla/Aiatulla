from pathlib import Path

NOTES_FILE = Path("notes.txt")


def add_note(text: str) -> None:
    with NOTES_FILE.open("a") as handle:
        handle.write(text + "\n")


def read_notes() -> list[str]:
    if not NOTES_FILE.exists():
        return []
    return NOTES_FILE.read_text().splitlines()
