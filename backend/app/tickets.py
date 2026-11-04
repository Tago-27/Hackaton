"""PDF de boletos de la demo (no oficiales): una página por boleto, con código único y QR."""

import io
from datetime import datetime

import segno
from fpdf import FPDF

from app.catalogs import DISCLAIMER, TICKET_TIERS
from app.models import Order

NAVY = (30, 58, 95)  # azul oscuro
PASTEL = (219, 234, 254)  # azul pastel
PASTEL_LINE = (147, 197, 253)
MUTED = (91, 107, 128)
RED = (185, 28, 28)


def _latin1(s: str) -> str:
    # Las fuentes base de PDF solo cubren latin-1 (incluye tildes y ñ).
    return s.encode("latin-1", "replace").decode("latin-1")


_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def human_date(value: str | None) -> str:
    """'2026-11-20T21:00:00' -> '20 nov 2026, 9:00 p. m.' (hora local del evento)."""
    if not value:
        return "Por confirmar"
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    text = f"{d.day} {_MESES[d.month - 1]} {d.year}"
    if "T" in value:
        h = d.hour % 12 or 12
        text += f", {h}:{d.minute:02d} {'a. m.' if d.hour < 12 else 'p. m.'}"
    return text


def ticket_codes(order: Order) -> list[str]:
    """Código único por boleto, derivado de la referencia de la orden."""
    return [f"{order.reference_code}-{i:02d}" for i in range(1, order.quantity + 1)]


def _qr_png(data: str) -> io.BytesIO:
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=8, border=2,
                                    dark="#1e3a5f", light="#ffffff")
    buf.seek(0)
    return buf


def simple_pdf(lines: list[str]) -> bytes:
    pdf = FPDF(format="A5")
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in lines:
        pdf.multi_cell(0, 8, _latin1(line), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _ticket_page(pdf: FPDF, order: Order, code: str, n: int) -> None:
    pdf.add_page()
    w = pdf.w - pdf.l_margin - pdf.r_margin

    # Franja superior de aviso
    pdf.set_fill_color(*RED)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.multi_cell(w, 5, _latin1("BOLETO DE DEMOSTRACIÓN - NO OFICIAL"), fill=True, align="C",
                   new_x="LMARGIN", new_y="NEXT")

    # Encabezado azul oscuro
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(w, 7, _latin1(f"  TURISMO MUSICAL  ·  Boleto {n} de {order.quantity}"), fill=True,
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 15)
    pdf.multi_cell(w, 7, _latin1(order.event_name), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(w, 2, "", fill=True, new_x="LMARGIN", new_y="NEXT")

    # Cuerpo en azul pastel
    top = pdf.get_y() + 4
    pdf.set_fill_color(*PASTEL)
    pdf.set_draw_color(*PASTEL_LINE)
    box_h = 66
    pdf.rect(pdf.l_margin, top, w, box_h, style="DF")
    pdf.set_xy(pdf.l_margin + 4, top + 4)
    info_w = w - 58
    for label, value in [
        ("Fecha", human_date(order.event_date)),
        ("Lugar", ", ".join(x for x in [order.event_venue, order.event_city] if x) or "-"),
        ("Localidad", TICKET_TIERS.get(order.ticket_tier or "general", ("General", 1))[0]),
        ("Titular", order.customer_names),
        ("Orden", order.reference_code),
        ("Factura", order.invoice_number or "En proceso"),
    ]:
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_text_color(*MUTED)
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(info_w, 4, _latin1(label.upper()), new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_text_color(*NAVY)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(info_w, 5, _latin1(value), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    qr_size = 48
    qr_x = pdf.l_margin + w - qr_size - 4
    pdf.image(_qr_png(f"TM-DEMO|{code}|{order.event_id}"), x=qr_x, y=top + 6, w=qr_size)
    pdf.set_xy(qr_x - 2, top + 6 + qr_size + 1)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Courier", "B", 9)
    pdf.cell(qr_size + 4, 5, code, align="C")

    # Pie
    pdf.set_xy(pdf.l_margin, top + box_h + 4)
    pdf.set_text_color(*MUTED)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(w, 4, _latin1(DISCLAIMER), new_x="LMARGIN", new_y="NEXT")


def ticket_pdf(order: Order) -> bytes:
    pdf = FPDF(format=(148, 140))  # ancho A5, alto ajustado al boleto
    pdf.set_auto_page_break(False)
    pdf.set_title(_latin1(f"Boletos {order.reference_code}"))
    for n, code in enumerate(ticket_codes(order), start=1):
        _ticket_page(pdf, order, code, n)
    return bytes(pdf.output())
