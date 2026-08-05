import csv

from storage import read_notes


def export_to_csv(destination: str) -> None:
    with open(destination, "w", newline="") as handle:
        writer = csv.writer(handle)
        for note in read_notes():
            writer.writerow([note])


def export_to_tsv(destination: str) -> None:
    with open(destination, "w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        for note in read_notes():
            writer.writerow([note])
