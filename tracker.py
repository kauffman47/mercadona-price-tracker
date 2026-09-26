import csv
import json
import os
import time
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import datetime, timezone
from pathlib import Path


BASE = "https://tienda.mercadona.es/api"
OUTPUT_DIR = Path("data")
OUTPUT_FILE = OUTPUT_DIR / "current_catalog.csv"


def create_opener():
    cookies = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies)
    )


def select_warehouse(opener, postcode):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(
        f"{BASE}/postal-codes/actions/change-pc/",
        data=json.dumps({"new_postal_code": postcode}).encode(),
        headers=headers,
        method="PUT",
    )

    with opener.open(req, timeout=30) as response:
        warehouse = response.headers.get("x-customer-wh")

    if not warehouse:
        raise RuntimeError("Mercadona no devolvió el almacén.")

    return warehouse


def get_json(opener, warehouse, path):
    query = urllib.parse.urlencode({
        "lang": "es",
        "wh": warehouse,
    })

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    req = urllib.request.Request(
        f"{BASE}{path}?{query}",
        headers=headers,
    )

    with opener.open(req, timeout=30) as response:
        return json.load(response)


def find_products(node, category_name, products):
    if isinstance(node, dict):
        node_products = node.get("products")

        if isinstance(node_products, list):
            for product in node_products:
                if not isinstance(product, dict):
                    continue

                product_id = str(product.get("id", ""))

                if not product_id or product_id in products:
                    continue

                price = product.get("price_instructions") or {}

                products[product_id] = {
                    "product_id": product_id,
                    "name": product.get("display_name", ""),
                    "slug": product.get("slug", ""),
                    "thumbnail": product.get("thumbnail", ""),
                    "category": category_name,
                    "packaging": product.get("packaging", ""),
                    "published": product.get("published", ""),
                    "unavailable_from": product.get("unavailable_from") or "",
                    "unit_size": price.get("unit_size"),
                    "size_format": price.get("size_format"),
                    "unit_price": price.get("unit_price"),
                    "bulk_price": price.get("bulk_price"),
                    "reference_price": price.get("reference_price"),
                    "reference_format": price.get("reference_format"),
                    "previous_unit_price": (
                        price.get("previous_unit_price") or ""
                    ).strip(),
                    "price_decreased": price.get("price_decreased"),
                    "selling_method": price.get("selling_method"),
                    "share_url": product.get("share_url", ""),
                }

        for key, value in node.items():
            if key != "products":
                find_products(value, category_name, products)

    elif isinstance(node, list):
        for item in node:
            find_products(item, category_name, products)


def main():
    postcode = os.environ.get("MERCADONA_POSTCODE")

    if not postcode:
        raise RuntimeError(
            "No existe la variable MERCADONA_POSTCODE."
        )

    opener = create_opener()
    warehouse = select_warehouse(opener, postcode)

    print(f"Almacén: {warehouse}")

    root = get_json(opener, warehouse, "/categories/")

    categories = []

    for top in root.get("results", []):
        for category in top.get("categories", []):
            category_id = category.get("id")

            if isinstance(category_id, int):
                categories.append({
                    "id": category_id,
                    "name": category.get("name", ""),
                })

    print(f"Categorías: {len(categories)}")

    products = {}

    for i, category in enumerate(categories, start=1):
        data = get_json(
            opener,
            warehouse,
            f"/categories/{category['id']}/",
        )

        find_products(
            data,
            category["name"],
            products,
        )

        print(
            f"[{i}/{len(categories)}] "
            f"{category['name']}: "
            f"{len(products)} productos"
        )

        time.sleep(0.2)

    OUTPUT_DIR.mkdir(exist_ok=True)

    captured_at = datetime.now(timezone.utc).isoformat()

    fields = [
        "captured_at",
        "warehouse",
        "product_id",
        "name",
        "slug",
        "thumbnail",
        "category",
        "packaging",
        "published",
        "unavailable_from",
        "unit_size",
        "size_format",
        "unit_price",
        "bulk_price",
        "reference_price",
        "reference_format",
        "previous_unit_price",
        "price_decreased",
        "selling_method",
        "share_url",
    ]

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for product_id in sorted(products):
            row = products[product_id].copy()
            row["captured_at"] = captured_at
            row["warehouse"] = warehouse
            writer.writerow(row)

    print("")
    print("CAPTURA COMPLETADA")
    print(f"Productos guardados: {len(products)}")
    print(f"Archivo: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
