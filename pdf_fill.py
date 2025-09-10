# pdf_fill.py
import os
import io
import uuid
import json
from typing import List, Dict, Any, Tuple
import fitz  # PyMuPDF


# Where to store temporary PDFs
UPLOAD_DIR = os.path.join("instance", "formfill")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _new_id() -> str:
    return uuid.uuid4().hex


def _pdf_path(pdf_id: str) -> str:
    # very basic guard
    if not pdf_id or len(pdf_id) > 64 or not pdf_id.isalnum():
        raise ValueError("Invalid pdf_id")
    return os.path.join(UPLOAD_DIR, f"{pdf_id}.pdf")


def save_pdf_temp(pdf_bytes: bytes) -> str:
    """
    Save bytes to a temp file and return a pdf_id.
    """
    pdf_id = _new_id()
    path = _pdf_path(pdf_id)
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    return pdf_id


def load_pdf_bytes(pdf_id: str) -> bytes:
    path = _pdf_path(pdf_id)
    with open(path, "rb") as f:
        return f.read()


def get_pdf_page_info(pdf_id: str) -> Dict[str, Any]:
    """
    Return page sizes for UI mapping.
    Output:
    {
      "pdf_id": "...",
      "pages": [
        {"index": 0, "width": 595.28, "height": 841.89},
        ...
      ]
    }
    Units are PDF points.
    """
    path = _pdf_path(pdf_id)
    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc):
        rect = page.rect  # fitz.Rect
        pages.append({"index": i, "width": float(rect.width), "height": float(rect.height)})
    doc.close()
    return {"pdf_id": pdf_id, "pages": pages}


def _parse_hex_color(hex_str: str) -> Tuple[float, float, float]:
    """
    Convert '#RRGGBB' to floats 0..1 for PyMuPDF.
    Default black if invalid.
    """
    if not isinstance(hex_str, str):
        return (0, 0, 0)
    s = hex_str.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6:
        return (0, 0, 0)
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
        return (r, g, b)
    except Exception:
        return (0, 0, 0)


def apply_text_overlays(
    pdf_id: str,
    overlays: List[Dict[str, Any]],
    default_font: str = "helv",   # built-in Helvetica
    default_size: float = 12.0,
    default_color: str = "#000000",
    write_debug_json: bool = False
) -> bytes:
    """
    Apply text overlays and return the new PDF bytes.

    overlays example (JSON-like):
    [
      {
        "page": 0,                 # 0-based page index
        "x": 0.25,                 # normalized (0..1) from left
        "y": 0.33,                 # normalized (0..1) from top
        "text": "Sheel Nikalje",
        "font_size": 14,           # optional (points)
        "color": "#1f2937",        # optional hex
        "align": "left"            # left|center|right (optional; default=left)
      }
    ]

    Notes:
    - Coordinates are **normalized** so UI can work at any zoom.
    - We align by computing text length for center/right.
    """
    path = _pdf_path(pdf_id)
    doc = fitz.open(path)

    if write_debug_json:
        # optional: save last overlays to a sidecar file for debugging
        with open(os.path.join(UPLOAD_DIR, f"{pdf_id}.overlays.json"), "w", encoding="utf-8") as f:
            json.dump(overlays, f, ensure_ascii=False, indent=2)

    for item in overlays:
        try:
            page_index = int(item.get("page", 0))
            page = doc[page_index]

            rect = page.rect
            page_w, page_h = float(rect.width), float(rect.height)

            # normalized coords -> absolute points
            nx = float(item.get("x", 0))
            ny = float(item.get("y", 0))
            x = max(0.0, min(1.0, nx)) * page_w
            y = max(0.0, min(1.0, ny)) * page_h

            text = str(item.get("text", ""))
            if not text:
                continue

            font_size = float(item.get("font_size", default_size))
            color = _parse_hex_color(item.get("color", default_color))
            align = (item.get("align") or "left").lower()

            # Text measurement for alignment
            try:
                text_len = page.get_text_length(text, fontname=default_font, fontsize=font_size)
            except Exception:
                # older/newer API fallback
                try:
                    text_len = fitz.get_text_length(text, fontname=default_font, fontsize=font_size)
                except Exception:
                    text_len = len(text) * (font_size * 0.5)  # rough fallback

            if align == "center":
                draw_x = x - (text_len / 2.0)
            elif align == "right":
                draw_x = x - text_len
            else:
                draw_x = x

            # Draw text (top-left baseline correction: PyMuPDF draws from baseline;
            # we nudge down a bit, so it looks like top-left anchor)
            baseline_adjust = font_size * 0.75
            draw_y = y + baseline_adjust

            page.insert_text(
                (draw_x, draw_y),
                text,
                fontsize=font_size,
                fontname=default_font,
                fill=color,
                render_mode=0  # fill text
            )
        except Exception as e:
            # Continue with others even if one fails
            print("Overlay error:", e)

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    out.seek(0)
    return out.read()
