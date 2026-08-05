import sys

from storage import add_note, read_notes


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: main.py [add TEXT | list]")
        return 1

    command = sys.argv[1]

    if command == "add":
        add_note(" ".join(sys.argv[2:]))
        return 0

    if command == "list":
        for note in read_notes():
            print(note)
        return 0

    print(f"unknown command: {command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
