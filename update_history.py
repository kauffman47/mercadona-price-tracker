import csv
from datetime import datetime, timezone
from pathlib import Path


CURRENT_FILE = Path("data/current_catalog.csv")
HISTORY_FILE = Path("data/price_history.csv")


FIELDS = [
    "captured_at",
    "warehouse",
    "product_id",
    "name",
    "category",
    "packaging",
    "unit_size",
    "size_format",
    "unit_price",
    "reference_price",
    "reference_format",
]


def load_current():
    with CURRENT_FILE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_last_history():
    if not HISTORY_FILE.exists():
        return {}

    last = {}

    with HISTORY_FILE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            last[row["product_id"]] = row

    return last


def changed(current, previous):
    if previous is None:
        return True

    fields = [
        "unit_price",
        "reference_price",
        "unit_size",
        "size_format",
        "reference_format",
        "packaging",
    ]

    return any(
        current.get(field, "") != previous.get(field, "")
        for field in fields
    )


def main():
    current = load_current()
    previous = load_last_history()

    timestamp = datetime.now(timezone.utc).isoformat()
    new_rows = []

    for product in current:
        product_id = product["product_id"]

        if changed(product, previous.get(product_id)):
            row = {field: product.get(field, "") for field in FIELDS}
            row["captured_at"] = timestamp
            new_rows.append(row)

    write_header = not HISTORY_FILE.exists()

    with HISTORY_FILE.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)

        if write_header:
            writer.writeheader()

        writer.writerows(new_rows)

    print(f"Productos actuales: {len(current)}")
    print(f"Nuevos registros históricos: {len(new_rows)}")
    print(f"Archivo histórico: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
