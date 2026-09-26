import csv
import html
import json
from collections import defaultdict
from datetime import datetime, timezone
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


def parse_date(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def format_date(value):
    dt = parse_date(value)

    if dt is None:
        return ""

    return dt.strftime("%d/%m/%Y")


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


def weighted_median(series, end_dt):
    if not series:
        return None

    periods = []

    for i, point in enumerate(series):
        start = parse_date(point["iso"])

        if start is None:
            continue

        if i + 1 < len(series):
            end = parse_date(series[i + 1]["iso"])
        else:
            end = end_dt

        if end is None:
            continue

        seconds = max((end - start).total_seconds(), 0)

        periods.append({
            "value": point["value"],
            "weight": seconds,
        })

    total_weight = sum(p["weight"] for p in periods)

    if total_weight <= 0:
        return series[-1]["value"]

    periods.sort(key=lambda p: p["value"])

    accumulated = 0

    for period in periods:
        accumulated += period["weight"]

        if accumulated >= total_weight / 2:
            return period["value"]

    return periods[-1]["value"]


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

            if unit != current_unit:
                continue

            comparable.append({
                "value": value,
                "iso": row["captured_at"],
                "date": format_date(row["captured_at"]),
            })

        comparable.sort(
            key=lambda x: parse_date(x["iso"])
            or datetime.min.replace(tzinfo=timezone.utc)
        )

        current_capture = product.get("captured_at", "")
        current_dt = parse_date(current_capture)

        if current_dt is None:
            current_dt = datetime.now(timezone.utc)

        if current_value is not None:
            if not comparable:
                comparable.append({
                    "value": current_value,
                    "iso": current_capture,
                    "date": format_date(current_capture),
                })

            elif abs(comparable[-1]["value"] - current_value) > 1e-12:
                comparable.append({
                    "value": current_value,
                    "iso": current_capture,
                    "date": format_date(current_capture),
                })

        values = [point["value"] for point in comparable]

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
            last_change = comparable[-1]["date"]
        else:
            last_change = "-"

        if comparable:
            first_observation = comparable[0]["date"]

            last_dt = parse_date(comparable[-1]["iso"])

            if last_dt is not None:
                days_current = max(
                    int((current_dt - last_dt).total_seconds() / 86400),
                    0,
                )
            else:
                days_current = None

        else:
            first_observation = "-"
            days_current = None

        median_price = weighted_median(
            comparable,
            current_dt,
        )

        result.append({
            "id": product_id,
            "name": product.get("name", ""),
            "thumbnail": product.get("thumbnail", ""),
            "category": product.get("category", ""),
            "packaging": product.get("packaging", ""),
            "unit_price": unit_price,
            "reference_price": current_value,
            "reference_format": current_unit,
            "minimum": minimum,
            "maximum": maximum,
            "median": median_price,
            "position": position,
            "status": status,
            "changes": max(len(comparable) - 1, 0),
            "last_change": last_change,
            "first_observation": first_observation,
            "days_current": days_current,
            "history": comparable,
            "history_end": current_capture,
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

    # Endurecer el JSON antes de incrustarlo dentro de <script>.
    # Evita que caracteres especiales puedan cerrar el bloque script
    # o introducir HTML/JavaScript inesperado.
    data_json = (
        data_json
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    categories_html = "\n".join(
        f'<option value="{html.escape(category)}">'
        f'{html.escape(category)}</option>'
        for category in categories
    )

    page = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>Mercadona Price Tracker</title>

<style>
body {
    font-family: Arial, sans-serif;
    margin: 0;
    background: #f5f6f7;
    color: #222;
}

header {
    background: #008c63;
    color: white;
    padding: 20px;
}

main {
    max-width: 1650px;
    margin: auto;
    padding: 20px;
}

.controls {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    gap: 10px;
    margin-bottom: 20px;
}

input, select {
    padding: 10px;
    font-size: 16px;
}

.summary {
    margin-bottom: 15px;
    font-weight: bold;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: white;
}

th, td {
    padding: 9px;
    border-bottom: 1px solid #ddd;
    text-align: left;
    vertical-align: middle;
}

th {
    background: #eee;
    position: sticky;
    top: 0;
    cursor: pointer;
    z-index: 2;
}

tr:hover {
    background: #f3f8f6;
}

.image-column {
    width: 64px;
    text-align: center;
}

.product-image {
    display: block;
    width: 54px;
    height: 54px;
    margin: auto;
    object-fit: contain;
    background: white;
}

.product-link {
    border: 0;
    background: none;
    padding: 0;
    margin: 0;
    color: #007c59;
    text-decoration: underline;
    cursor: pointer;
    font: inherit;
    text-align: left;
}

.mercadona-link {
    color: #007c59;
    text-decoration: underline;
    white-space: nowrap;
}

.price {
    text-align: right;
    white-space: nowrap;
}

.minimum {
    background: #d9f5df;
}

.maximum {
    background: #ffd9d9;
}

.low {
    background: #e8f6e8;
}

.high {
    background: #fff0d2;
}

.nohistory {
    color: #777;
}

a {
    color: #007c59;
}

.modal {
    display: none;
    position: fixed;
    z-index: 1000;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    padding: 30px;
    overflow-y: auto;
}

.modal.open {
    display: block;
}

.modal-card {
    position: relative;
    max-width: 1100px;
    margin: 20px auto;
    background: white;
    border-radius: 8px;
    padding: 28px;
    box-shadow: 0 15px 50px rgba(0, 0, 0, 0.3);
}

.modal-close {
    position: absolute;
    top: 12px;
    right: 15px;
    border: 0;
    background: none;
    font-size: 28px;
    cursor: pointer;
    color: #555;
}

.detail-header {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 25px;
    align-items: center;
    margin-bottom: 25px;
}

.detail-image {
    width: 170px;
    height: 170px;
    object-fit: contain;
}

.detail-header h2 {
    margin: 0 0 8px 0;
}

.detail-category {
    color: #666;
    margin-bottom: 12px;
}

.metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin: 20px 0 30px 0;
}

.metric {
    background: #f5f6f7;
    border-radius: 6px;
    padding: 14px;
}

.metric-label {
    font-size: 13px;
    color: #666;
    margin-bottom: 5px;
}

.metric-value {
    font-size: 20px;
    font-weight: bold;
}

.chart-title {
    margin-top: 10px;
}

.chart-container {
    width: 100%;
    min-height: 340px;
    border: 1px solid #ddd;
    background: #fff;
    border-radius: 5px;
    margin-top: 10px;
}

.chart-note {
    color: #666;
    font-size: 13px;
    margin-top: 8px;
}

@media (max-width: 800px) {
    .controls {
        grid-template-columns: 1fr;
    }

    table {
        font-size: 12px;
    }

    .product-image {
        width: 42px;
        height: 42px;
    }

    .image-column {
        width: 48px;
    }

    .modal {
        padding: 5px;
    }

    .modal-card {
        margin: 5px auto;
        padding: 18px;
    }

    .detail-header {
        grid-template-columns: 90px 1fr;
    }

    .detail-image {
        width: 90px;
        height: 90px;
    }

    .metrics {
        grid-template-columns: repeat(2, 1fr);
    }
}
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
        __CATEGORIES__
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
    <th class="image-column">Imagen</th>
    <th onclick="sortBy('category')">Categoría</th>
    <th onclick="sortBy('unit_price')">Precio</th>
    <th onclick="sortBy('reference_price')">Precio ref.</th>
    <th onclick="sortBy('minimum')">Mínimo</th>
    <th onclick="sortBy('maximum')">Máximo</th>
    <th onclick="sortBy('position')">Posición</th>
    <th onclick="sortBy('status')">Situación</th>
    <th onclick="sortBy('changes')">Cambios</th>
    <th>Último cambio</th>
    <th>Enlace</th>
</tr>
</thead>

<tbody id="tableBody"></tbody>
</table>

</main>

<div
    id="productModal"
    class="modal"
    onclick="closeModalFromBackdrop(event)"
>
    <div class="modal-card">
        <button
            class="modal-close"
            onclick="closeProductDetail()"
            aria-label="Cerrar"
        >
            ×
        </button>

        <div id="detailContent"></div>
    </div>
</div>

<script>
const products = __DATA__;

const productMap = Object.fromEntries(
    products.map(product => [product.id, product])
);

let sortField = "name";
let ascending = true;


function escapeHtml(value) {
    if (value === null || value === undefined) return "";

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function euro(value) {
    if (value === null || value === undefined) return "-";

    return value.toFixed(2) + " €";
}


function referencePrice(value, unit) {
    if (value === null || value === undefined) return "-";

    if (!unit || unit === "unidad") {
        return value.toFixed(2) + " €";
    }

    const normalized = unit.toLowerCase();

    if (normalized === "kg") {
        return value.toFixed(2) + " €/kg";
    }

    if (normalized === "l") {
        return value.toFixed(2) + " €/L";
    }

    return value.toFixed(2) + " €/" + unit;
}


function positionText(value) {
    if (value === null || value === undefined) return "-";

    return value.toFixed(0) + " %";
}


function rowClass(status) {
    if (status === "Mínimo") return "minimum";
    if (status === "Máximo") return "maximum";
    if (status === "Zona baja") return "low";
    if (status === "Zona alta") return "high";
    if (status === "Sin histórico") return "nohistory";

    return "";
}


function imageHtml(product) {
    if (!product.thumbnail) {
        return "";
    }

    return `
        <img
            src="${escapeHtml(product.thumbnail)}"
            class="product-image"
            alt="${escapeHtml(product.name)}"
            loading="lazy"
        >
    `;
}


function mercadonaLink(product) {
    if (!product.url) {
        return "-";
    }

    return `
        <a
            class="mercadona-link"
            href="${escapeHtml(product.url)}"
            target="_blank"
            rel="noopener noreferrer"
        >
            Mercadona
        </a>
    `;
}


function sortBy(field) {
    if (sortField === field) {
        ascending = !ascending;
    } else {
        sortField = field;
        ascending = true;
    }

    render();
}


function render() {
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

    let filtered = products.filter(p => {
        const matchesSearch =
            p.name.toLowerCase().includes(search);

        const matchesCategory =
            !category || p.category === category;

        const matchesStatus =
            !status || p.status === status;

        return matchesSearch &&
               matchesCategory &&
               matchesStatus;
    });

    filtered.sort((a, b) => {
        let av = a[sortField];
        let bv = b[sortField];

        if (av === null || av === undefined) av = "";
        if (bv === null || bv === undefined) bv = "";

        if (typeof av === "string") {
            return ascending
                ? av.localeCompare(bv)
                : bv.localeCompare(av);
        }

        return ascending ? av - bv : bv - av;
    });

    document.getElementById("summary").textContent =
        filtered.length +
        " productos mostrados de " +
        products.length;

    const tbody = document.getElementById("tableBody");

    tbody.innerHTML = filtered.map(p => `
        <tr class="${rowClass(p.status)}">

            <td>
                <button
                    class="product-link"
                    data-id="${escapeHtml(p.id)}"
                    onclick="openProductDetail(this.dataset.id)"
                >
                    ${escapeHtml(p.name)}
                </button>
            </td>

            <td class="image-column">
                ${imageHtml(p)}
            </td>

            <td>${escapeHtml(p.category)}</td>

            <td class="price">
                ${euro(p.unit_price)}
            </td>

            <td class="price">
                ${referencePrice(
                    p.reference_price,
                    p.reference_format
                )}
            </td>

            <td class="price">
                ${referencePrice(
                    p.minimum,
                    p.reference_format
                )}
            </td>

            <td class="price">
                ${referencePrice(
                    p.maximum,
                    p.reference_format
                )}
            </td>

            <td class="price">
                ${positionText(p.position)}
            </td>

            <td>${escapeHtml(p.status)}</td>

            <td class="price">
                ${p.changes}
            </td>

            <td>
                ${escapeHtml(p.last_change)}
            </td>

            <td>
                ${mercadonaLink(p)}
            </td>

        </tr>
    `).join("");
}


function openProductDetail(productId) {
    const product = productMap[productId];

    if (!product) return;

    const image = product.thumbnail
        ? `
            <img
                class="detail-image"
                src="${escapeHtml(product.thumbnail)}"
                alt="${escapeHtml(product.name)}"
            >
        `
        : "";

    const daysCurrent =
        product.days_current === null ||
        product.days_current === undefined
            ? "-"
            : product.days_current + " días";

    document.getElementById("detailContent").innerHTML = `
        <div class="detail-header">

            <div>
                ${image}
            </div>

            <div>
                <h2>${escapeHtml(product.name)}</h2>

                <div class="detail-category">
                    ${escapeHtml(product.category)}
                    ${
                        product.packaging
                            ? " · " + escapeHtml(product.packaging)
                            : ""
                    }
                </div>

                <div>
                    <strong>Situación:</strong>
                    ${escapeHtml(product.status)}
                </div>

                <p>
                    <a
                        href="${escapeHtml(product.url)}"
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        Abrir producto en Mercadona
                    </a>
                </p>
            </div>

        </div>

        <div class="metrics">

            <div class="metric">
                <div class="metric-label">
                    Precio
                </div>
                <div class="metric-value">
                    ${euro(product.unit_price)}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Precio de referencia
                </div>
                <div class="metric-value">
                    ${referencePrice(
                        product.reference_price,
                        product.reference_format
                    )}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Mínimo histórico
                </div>
                <div class="metric-value">
                    ${referencePrice(
                        product.minimum,
                        product.reference_format
                    )}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Máximo histórico
                </div>
                <div class="metric-value">
                    ${referencePrice(
                        product.maximum,
                        product.reference_format
                    )}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Mediana histórica
                </div>
                <div class="metric-value">
                    ${referencePrice(
                        product.median,
                        product.reference_format
                    )}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Días al precio actual
                </div>
                <div class="metric-value">
                    ${daysCurrent}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Último cambio
                </div>
                <div class="metric-value">
                    ${escapeHtml(product.last_change)}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Cambios registrados
                </div>
                <div class="metric-value">
                    ${product.changes}
                </div>
            </div>

        </div>

        <h3 class="chart-title">
            Evolución del precio
        </h3>

        <div
            id="priceChart"
            class="chart-container"
        ></div>

        <div class="chart-note">
            Primera observación:
            ${escapeHtml(product.first_observation)}.
            La gráfica utiliza el precio de referencia
            cuando Mercadona lo proporciona.
        </div>
    `;

    document
        .getElementById("productModal")
        .classList
        .add("open");

    document.body.style.overflow = "hidden";

    drawPriceChart(product);
}


function closeProductDetail() {
    document
        .getElementById("productModal")
        .classList
        .remove("open");

    document.body.style.overflow = "";
}


function closeModalFromBackdrop(event) {
    if (event.target.id === "productModal") {
        closeProductDetail();
    }
}


document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
        closeProductDetail();
    }
});


function drawPriceChart(product) {
    const container = document.getElementById("priceChart");

    const series = product.history || [];

    if (!series.length) {
        container.innerHTML =
            "<p style='padding:20px'>Sin histórico disponible.</p>";

        return;
    }

    const width = Math.max(
        container.clientWidth || 800,
        500
    );

    const height = 340;

    const margin = {
        left: 75,
        right: 25,
        top: 25,
        bottom: 45,
    };

    const plotWidth =
        width - margin.left - margin.right;

    const plotHeight =
        height - margin.top - margin.bottom;

    const points = series.map(point => ({
        value: point.value,
        date: point.date,
        time: new Date(point.iso).getTime(),
    }));

    let xMin = points[0].time;

    let xMax = product.history_end
        ? new Date(product.history_end).getTime()
        : Date.now();

    if (!Number.isFinite(xMax) || xMax <= xMin) {
        xMax = xMin + 24 * 60 * 60 * 1000;
    }

    const values = points.map(point => point.value);

    let yMin = Math.min(...values);
    let yMax = Math.max(...values);

    if (Math.abs(yMax - yMin) < 1e-12) {
        const padding = Math.max(
            Math.abs(yMin) * 0.05,
            0.10
        );

        yMin -= padding;
        yMax += padding;
    } else {
        const padding = (yMax - yMin) * 0.12;

        yMin -= padding;
        yMax += padding;
    }

    function xScale(time) {
        return margin.left +
            ((time - xMin) / (xMax - xMin)) *
            plotWidth;
    }

    function yScale(value) {
        return margin.top +
            (1 - (value - yMin) / (yMax - yMin)) *
            plotHeight;
    }

    let svg = `
        <svg
            width="100%"
            height="${height}"
            viewBox="0 0 ${width} ${height}"
            xmlns="http://www.w3.org/2000/svg"
        >
    `;

    for (let i = 0; i <= 4; i++) {
        const ratio = i / 4;

        const y =
            margin.top +
            ratio * plotHeight;

        const value =
            yMax -
            ratio * (yMax - yMin);

        svg += `
            <line
                x1="${margin.left}"
                x2="${width - margin.right}"
                y1="${y}"
                y2="${y}"
                stroke="#dddddd"
                stroke-width="1"
            />

            <text
                x="${margin.left - 10}"
                y="${y + 4}"
                text-anchor="end"
                font-size="12"
                fill="#555"
            >
                ${value.toFixed(2)}
            </text>
        `;
    }

    let path = "";

    points.forEach((point, index) => {
        const x = xScale(point.time);
        const y = yScale(point.value);

        if (index === 0) {
            path += `M ${x} ${y}`;
        } else {
            path += ` H ${x} V ${y}`;
        }
    });

    path += `
        H ${xScale(xMax)}
    `;

    svg += `
        <path
            d="${path}"
            fill="none"
            stroke="#008c63"
            stroke-width="3"
        />
    `;

    points.forEach(point => {
        const x = xScale(point.time);
        const y = yScale(point.value);

        svg += `
            <circle
                cx="${x}"
                cy="${y}"
                r="5"
                fill="#008c63"
            >
                <title>
                    ${escapeHtml(point.date)}
                    ·
                    ${escapeHtml(
                        referencePrice(
                            point.value,
                            product.reference_format
                        )
                    )}
                </title>
            </circle>
        `;
    });

    svg += `
        <text
            x="${margin.left}"
            y="${height - 12}"
            text-anchor="start"
            font-size="12"
            fill="#555"
        >
            ${escapeHtml(points[0].date)}
        </text>

        <text
            x="${width - margin.right}"
            y="${height - 12}"
            text-anchor="end"
            font-size="12"
            fill="#555"
        >
            Hoy
        </text>

        </svg>
    `;

    container.innerHTML = svg;
}


render();
</script>

</body>
</html>
"""

    page = page.replace(
        "__CATEGORIES__",
        categories_html,
    )

    page = page.replace(
        "__DATA__",
        data_json,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)

    OUTPUT_FILE.write_text(
        page,
        encoding="utf-8",
    )

    print(f"Productos incluidos: {len(products)}")
    print(f"Panel generado: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
