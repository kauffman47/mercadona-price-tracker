import csv
import html
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


CURRENT_FILE = Path("data/current_catalog.csv")
HISTORY_FILE = Path("data/price_history.csv")
OUTPUT_DIR = Path("docs")
OUTPUT_FILE = OUTPUT_DIR / "index.html"


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_date(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return ""


def load_current():
    with CURRENT_FILE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_history():
    history = defaultdict(list)

    if not HISTORY_FILE.exists():
        return history

    with HISTORY_FILE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            history[row["product_id"]].append(row)

    return history


def comparable_price(row):
    reference_price = to_float(row.get("reference_price"))

    if reference_price is not None:
        return reference_price, row.get("reference_format", "")

    unit_price = to_float(row.get("unit_price"))

    return unit_price, "unidad"


def build_products(current, history):
    result = []

    for product in current:
        product_id = product["product_id"]

        current_value, current_unit = comparable_price(product)

        history_rows = history.get(product_id, [])

        comparable = []

        for row in history_rows:
            value, unit = comparable_price(row)

            if value is None:
                continue

            if unit == current_unit:
                comparable.append((value, row["captured_at"]))

        values = [value for value, _ in comparable]

        if current_value is None:
            minimum = None
            maximum = None
            position = None
            status = "Sin precio"

        elif not values:
            minimum = current_value
            maximum = current_value
            position = None
            status = "Sin histórico"

        else:
            minimum = min(values)
            maximum = max(values)

            if abs(maximum - minimum) < 1e-12:
                position = None
                status = "Sin variación"

            else:
                position = (
                    (current_value - minimum)
                    / (maximum - minimum)
                    * 100
                )

                if current_value <= minimum + 1e-9:
                    status = "Mínimo"

                elif current_value >= maximum - 1e-9:
                    status = "Máximo"

                elif position <= 25:
                    status = "Zona baja"

                elif position >= 75:
                    status = "Zona alta"

                else:
                    status = "Intermedio"

        unit_price = to_float(product.get("unit_price"))

        if len(comparable) > 1:
            last_change = format_date(comparable[-1][1])
        else:
            last_change = "-"

        result.append({
            "id": product_id,
            "name": product.get("name", ""),
            "category": product.get("category", ""),
            "packaging": product.get("packaging", ""),
            "unit_price": unit_price,
            "reference_price": current_value,
            "reference_format": current_unit,
            "minimum": minimum,
            "maximum": maximum,
            "position": position,
            "status": status,
            "changes": max(len(comparable) - 1, 0),
            "last_change": last_change,
            "url": product.get("share_url", ""),
        })

    return result


def main():
    current = load_current()
    history = load_history()

    products = build_products(current, history)

    categories = sorted({
        p["category"]
        for p in products
        if p["category"]
    })

    data_json = json.dumps(
        products,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    categories_html = "\n".join(
        f'<option value="{html.escape(category)}">'
        f'{html.escape(category)}</option>'
        for category in categories
    )

    page = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>Mercadona Price Tracker</title>

<style>
body {{
    font-family: Arial, sans-serif;
    margin: 0;
    background: #f5f6f7;
    color: #222;
}}

header {{
    background: #008c63;
    color: white;
    padding: 20px;
}}

main {{
    max-width: 1500px;
    margin: auto;
    padding: 20px;
}}

.controls {{
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    gap: 10px;
    margin-bottom: 20px;
}}

input, select {{
    padding: 10px;
    font-size: 16px;
}}

.summary {{
    margin-bottom: 15px;
    font-weight: bold;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    background: white;
}}

th, td {{
    padding: 9px;
    border-bottom: 1px solid #ddd;
    text-align: left;
}}

th {{
    background: #eee;
    position: sticky;
    top: 0;
    cursor: pointer;
}}

tr:hover {{
    background: #f3f8f6;
}}

.price {{
    text-align: right;
    white-space: nowrap;
}}

.minimum {{
    background: #d9f5df;
}}

.maximum {{
    background: #ffd9d9;
}}

.low {{
    background: #e8f6e8;
}}

.high {{
    background: #fff0d2;
}}

.nohistory {{
    color: #777;
}}

a {{
    color: #007c59;
}}

@media (max-width: 800px) {{
    .controls {{
        grid-template-columns: 1fr;
    }}

    table {{
        font-size: 12px;
    }}
}}
</style>
</head>

<body>

<header>
    <h1>Mercadona Price Tracker</h1>
    <div>Situación actual de precios respecto al histórico</div>
</header>

<main>

<div class="controls">
    <input
        id="search"
        type="text"
        placeholder="Buscar producto..."
        oninput="render()"
    >

    <select id="category" onchange="render()">
        <option value="">Todas las categorías</option>
        {categories_html}
    </select>

    <select id="status" onchange="render()">
        <option value="">Todas las situaciones</option>
        <option value="Mínimo">En mínimo</option>
        <option value="Zona baja">Zona baja</option>
        <option value="Intermedio">Intermedio</option>
        <option value="Zona alta">Zona alta</option>
        <option value="Máximo">En máximo</option>
        <option value="Sin variación">Sin variación</option>
        <option value="Sin histórico">Sin histórico</option>
    </select>
</div>

<div class="summary" id="summary"></div>

<table>
<thead>
<tr>
    <th onclick="sortBy('name')">Producto</th>
    <th onclick="sortBy('category')">Categoría</th>
    <th onclick="sortBy('unit_price')">Precio</th>
    <th onclick="sortBy('reference_price')">Precio ref.</th>
    <th onclick="sortBy('minimum')">Mínimo</th>
    <th onclick="sortBy('maximum')">Máximo</th>
    <th onclick="sortBy('position')">Posición</th>
    <th onclick="sortBy('status')">Situación</th>
    <th onclick="sortBy('changes')">Cambios</th>
    <th>Último cambio</th>
</tr>
</thead>

<tbody id="tableBody"></tbody>
</table>

</main>

<script>
const products = {data_json};

let sortField = "name";
let ascending = true;

function euro(value) {{
    if (value === null || value === undefined) return "-";
    return value.toFixed(2) + " €";
}}

function referencePrice(value, unit) {{
    if (value === null || value === undefined) return "-";

    if (!unit || unit === "unidad") {{
        return value.toFixed(2) + " €";
    }}

    const normalized = unit.toLowerCase();

    if (normalized === "kg") {{
        return value.toFixed(2) + " €/kg";
    }}

    if (normalized === "l") {{
        return value.toFixed(2) + " €/L";
    }}

    return value.toFixed(2) + " €/" + unit;
}}

function positionText(value) {{
    if (value === null || value === undefined) return "-";
    return value.toFixed(0) + " %";
}}

function rowClass(status) {{
    if (status === "Mínimo") return "minimum";
    if (status === "Máximo") return "maximum";
    if (status === "Zona baja") return "low";
    if (status === "Zona alta") return "high";
    if (status === "Sin histórico") return "nohistory";
    return "";
}}

function sortBy(field) {{
    if (sortField === field) {{
        ascending = !ascending;
    }} else {{
        sortField = field;
        ascending = true;
    }}

    render();
}}

function render() {{
    const search = document
        .getElementById("search")
        .value
        .toLowerCase();

    const category = document
        .getElementById("category")
        .value;

    const status = document
        .getElementById("status")
        .value;

    let filtered = products.filter(p => {{
        const matchesSearch =
            p.name.toLowerCase().includes(search);

        const matchesCategory =
            !category || p.category === category;

        const matchesStatus =
            !status || p.status === status;

        return matchesSearch &&
               matchesCategory &&
               matchesStatus;
    }});

    filtered.sort((a, b) => {{
        let av = a[sortField];
        let bv = b[sortField];

        if (av === null || av === undefined) av = "";
        if (bv === null || bv === undefined) bv = "";

        if (typeof av === "string") {{
            return ascending
                ? av.localeCompare(bv)
                : bv.localeCompare(av);
        }}

        return ascending ? av - bv : bv - av;
    }});

    document.getElementById("summary").textContent =
        filtered.length +
        " productos mostrados de " +
        products.length;

    const tbody = document.getElementById("tableBody");

    tbody.innerHTML = filtered.map(p => `
        <tr class="${{rowClass(p.status)}}">
            <td>
                <a href="${{p.url}}" target="_blank">
                    ${{p.name}}
                </a>
            </td>
            <td>${{p.category}}</td>

            <td class="price">
                ${{euro(p.unit_price)}}
            </td>

            <td class="price">
                ${{referencePrice(
                    p.reference_price,
                    p.reference_format
                )}}
            </td>

            <td class="price">
                ${{referencePrice(
                    p.minimum,
                    p.reference_format
                )}}
            </td>

            <td class="price">
                ${{referencePrice(
                    p.maximum,
                    p.reference_format
                )}}
            </td>

            <td class="price">
                ${{positionText(p.position)}}
            </td>

            <td>${{p.status}}</td>

            <td class="price">
                ${{p.changes}}
            </td>

            <td>${{p.last_change}}</td>
        </tr>
    `).join("");
}}

render();
</script>

</body>
</html>
"""

    OUTPUT_DIR.mkdir(exist_ok=True)

    OUTPUT_FILE.write_text(
        page,
        encoding="utf-8",
    )

    print(f"Productos incluidos: {len(products)}")
    print(f"Panel generado: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
