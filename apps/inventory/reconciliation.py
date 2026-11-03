from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from unicodedata import combining, normalize
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .models import Lot, LotBalance, Product

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_DATA_ROWS = 5000
HEADERS = ("codigo_producto", "lote", "vencimiento", "cantidad_contada")
HEADER_LABELS = ("Código producto", "Lote", "Vencimiento", "Cantidad contada")


def _normalize_header(value):
    text = normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not combining(char))
    return "_".join(text.casefold().replace("_", " ").split())


def _cell_text(value):
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value)).strip()
    return str(value).strip()


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(value.strip(), date_format).date()
            except ValueError:
                continue
    raise ValueError("Usa una fecha válida (dd/mm/aaaa).")


def _parse_quantity(value):
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("Ingresa una cantidad contada.")
    try:
        quantity = Decimal(str(value).strip())
    except InvalidOperation, ValueError:
        raise ValueError("La cantidad debe ser numérica.") from None
    if not quantity.is_finite() or quantity < 0:
        raise ValueError("La cantidad debe ser un número igual o mayor que cero.")
    try:
        return LotBalance._meta.get_field("quantity").clean(quantity, None)
    except ValidationError:
        raise ValueError("La cantidad admite hasta 15 enteros y 3 decimales.") from None


def count_template():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conteo"
    sheet.append(HEADER_LABELS)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:D1"
    for column, width in zip("ABCD", (24, 20, 18, 22)):
        sheet.column_dimensions[column].width = width
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def compare_inventory_count(*, warehouse, uploaded_file):
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValidationError("El archivo no puede superar 5 MB.")
    if not uploaded_file.name.lower().endswith(".xlsx"):
        raise ValidationError("Carga un archivo Excel con formato .xlsx.")

    try:
        with ZipFile(uploaded_file) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ValidationError("El contenido descomprimido del archivo supera 20 MB.")
        uploaded_file.seek(0)
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
        sheet = workbook.active
        if sheet.max_row is not None and sheet.max_row > MAX_DATA_ROWS + 1:
            raise ValidationError(f"El archivo no puede superar {MAX_DATA_ROWS} filas de datos.")
        header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        if tuple(_normalize_header(value) for value in header_row[:4]) != HEADERS:
            raise ValidationError(
                "La primera fila debe contener: Código producto, Lote, Vencimiento y "
                "Cantidad contada. Descarga la plantilla para ver el formato."
            )

        records = []
        for row_number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            values = tuple(values) + (None,) * max(0, 4 - len(values))
            values = values[:4]
            if all(value is None or value == "" for value in values):
                continue
            if len(records) >= MAX_DATA_ROWS:
                raise ValidationError(
                    f"El archivo no puede superar {MAX_DATA_ROWS} filas de datos."
                )

            code, lot_code = _cell_text(values[0]), _cell_text(values[1])
            errors = []
            if not code:
                errors.append("Falta el código del producto.")
            if not lot_code:
                errors.append("Falta el lote.")
            try:
                expires_on = _parse_date(values[2])
            except ValueError as exc:
                expires_on = None
                errors.append(str(exc))
            try:
                counted_quantity = _parse_quantity(values[3])
            except ValueError as exc:
                counted_quantity = None
                errors.append(str(exc))
            records.append(
                {
                    "row_number": row_number,
                    "code": code,
                    "lot_code": lot_code,
                    "expires_on": expires_on,
                    "counted_quantity": counted_quantity,
                    "errors": errors,
                }
            )
        workbook.close()
    except ValidationError:
        raise
    except BadZipFile, InvalidFileException, OSError, ValueError, KeyError:
        raise ValidationError(
            "No se pudo leer el archivo. Verifica que sea un .xlsx válido."
        ) from None

    if not records:
        raise ValidationError("El archivo no contiene filas de conteo.")

    for record in records:
        record["key"] = (
            (record["code"].casefold(), record["lot_code"].casefold())
            if record["code"] and record["lot_code"]
            else None
        )
    key_counts = Counter(record["key"] for record in records if record["key"] is not None)
    products = {product.code.casefold(): product for product in Product.objects.all()}
    product_ids = {products[key[0]].pk for key in key_counts if key[0] in products}
    lots = {
        (lot.product.code.casefold(), lot.code.casefold()): lot
        for lot in Lot.objects.filter(product_id__in=product_ids).select_related("product")
    }
    lot_ids = [lot.pk for lot in lots.values()]
    quantities = dict(
        LotBalance.objects.filter(warehouse=warehouse, lot_id__in=lot_ids).values_list(
            "lot_id", "quantity"
        )
    )

    results = []
    listed_lot_ids = set()
    for record in records:
        key = record["key"]
        product = products.get(record["code"].casefold()) if record["code"] else None
        lot = lots.get(key) if key else None
        if lot:
            listed_lot_ids.add(lot.pk)
        duplicate = key is not None and key_counts[key] > 1
        system_quantity = quantities.get(lot.pk, Decimal("0")) if lot else None
        difference = None
        if duplicate:
            status = "Duplicado en Excel"
            detail = "El mismo producto y lote aparece más de una vez."
        elif record["errors"]:
            status = "Dato inválido"
            detail = " ".join(record["errors"])
        elif product is None:
            status = "Producto no encontrado"
            detail = "El código no está registrado en el catálogo."
        elif lot is None:
            status = "Lote no registrado"
            detail = "No existe ese lote para el producto indicado."
        else:
            difference = record["counted_quantity"] - system_quantity
            if lot.expires_on != record["expires_on"]:
                status = "Vencimiento distinto"
                detail = f"Vencimiento registrado: {lot.expires_on:%d/%m/%Y}."
            elif difference:
                status = "Diferencia"
                detail = "La cantidad contada no coincide con el saldo registrado."
            else:
                status = "Coincide"
                detail = ""
        results.append(
            {
                "row_number": record["row_number"],
                "product_code": product.code if product else record["code"],
                "product_name": product.name if product else "",
                "lot_code": lot.code if lot else record["lot_code"],
                "expires_on": record["expires_on"],
                "system_quantity": system_quantity,
                "counted_quantity": record["counted_quantity"],
                "difference": difference,
                "status": status,
                "detail": detail,
            }
        )

    balances = (
        LotBalance.objects.filter(warehouse=warehouse, quantity__gt=0)
        .exclude(lot_id__in=listed_lot_ids)
        .select_related("lot__product")
        .order_by("lot__product__name", "lot__code")
    )
    for balance in balances:
        results.append(
            {
                "row_number": None,
                "product_code": balance.lot.product.code,
                "product_name": balance.lot.product.name,
                "lot_code": balance.lot.code,
                "expires_on": balance.lot.expires_on,
                "system_quantity": balance.quantity,
                "counted_quantity": None,
                "difference": None,
                "status": "No incluido en Excel",
                "detail": "Este lote tiene stock registrado y no aparece en el archivo.",
            }
        )
    return results
