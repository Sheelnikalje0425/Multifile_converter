# pdf_fill.py
import os
import io
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple
import fitz  # PyMuPDF

# =========================
# TEMPORARY IN-MEMORY STORAGE
# =========================
pdf_storage = {}
PDF_SESSION_TIMEOUT = 3600  # 1 hour
MAX_MEMORY_MB = 500  # Maximum memory usage for PDF storage
MAX_PDF_SIZE_MB = 50  # Maximum individual PDF size


def save_pdf_temp(pdf_bytes: bytes) -> str:
    """Save PDF to temporary memory with size limits"""
    # Check individual PDF size
    pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
    if pdf_size_mb > MAX_PDF_SIZE_MB:
        raise ValueError(f"PDF too large: {pdf_size_mb:.1f}MB (max: {MAX_PDF_SIZE_MB}MB)")

    # Check total memory usage
    current_memory_mb = sum(len(data['data']) for data in pdf_storage.values()) / (1024 * 1024)
    if current_memory_mb + pdf_size_mb > MAX_MEMORY_MB:
        # Force cleanup before throwing error
        cleanup_old_pdfs(force=True)
        current_memory_mb = sum(len(data['data']) for data in pdf_storage.values()) / (1024 * 1024)
        if current_memory_mb + pdf_size_mb > MAX_MEMORY_MB:
            raise ValueError("Server memory limit reached for PDF storage")

    pdf_id = str(uuid.uuid4().hex)
    pdf_storage[pdf_id] = {
        'data': pdf_bytes,
        'timestamp': datetime.now(),
        'size_mb': pdf_size_mb
    }

    cleanup_old_pdfs()
    return pdf_id


def load_pdf_bytes(pdf_id: str) -> bytes:
    """Load PDF from temporary memory storage"""
    if pdf_id in pdf_storage:
        pdf_storage[pdf_id]['timestamp'] = datetime.now()
        return pdf_storage[pdf_id]['data']
    raise ValueError("PDF not found")


def cleanup_old_pdfs(force=False):
    """Cleanup old PDFs, or all if force=True"""
    current_time = datetime.now()
    pdfs_to_remove = []

    for pdf_id, pdf_data in pdf_storage.items():
        if force:
            pdfs_to_remove.append(pdf_id)
        else:
            time_diff = current_time - pdf_data['timestamp']
            if time_diff.total_seconds() > PDF_SESSION_TIMEOUT:
                pdfs_to_remove.append(pdf_id)

    for pdf_id in pdfs_to_remove:
        del pdf_storage[pdf_id]

    if pdfs_to_remove:
        print(f"Cleaned up {len(pdfs_to_remove)} temporary PDFs")


def get_storage_stats():
    """Get storage statistics"""
    total_size = sum(len(data['data']) for data in pdf_storage.values())
    total_count = len(pdf_storage)
    return {
        'total_pdfs': total_count,
        'total_size_mb': total_size / (1024 * 1024),
        'max_size_mb': MAX_MEMORY_MB
    }


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
    pdf_bytes = load_pdf_bytes(pdf_id)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        rect = page.rect  # fitz.Rect
        pages.append({"index": i, "width": float(rect.width), "height": float(rect.height)})
    doc.close()
    return {"pdf_id": pdf_id, "pages": pages}


def _parse_hex_color(hex_str: str) -> Tuple[float, float, float]:
    """
    Convert '#RRGGBB' to floats 0..1 for PyMuPDF.
    Enhanced with better error handling and default to black.
    """
    if not isinstance(hex_str, str):
        print(f"Warning: Invalid color type, using black. Got: {type(hex_str)}")
        return (0.0, 0.0, 0.0)  # Black

    s = hex_str.strip().lower()

    # Remove # if present
    if s.startswith("#"):
        s = s[1:]

    # Handle different color formats
    if len(s) == 6:  # RRGGBB
        try:
            r = int(s[0:2], 16) / 255.0
            g = int(s[2:4], 16) / 255.0
            b = int(s[4:6], 16) / 255.0
            print(f"Color parsed: {hex_str} -> RGB({r:.3f}, {g:.3f}, {b:.3f})")
            return (r, g, b)
        except Exception as e:
            print(f"Warning: Color parsing failed for '{hex_str}', using black. Error: {e}")

    elif len(s) == 3:  # RGB shorthand
        try:
            r = int(s[0] * 2, 16) / 255.0
            g = int(s[1] * 2, 16) / 255.0
            b = int(s[2] * 2, 16) / 255.0
            print(f"Color parsed: {hex_str} -> RGB({r:.3f}, {g:.3f}, {b:.3f})")
            return (r, g, b)
        except Exception as e:
            print(f"Warning: Color parsing failed for '{hex_str}', using black. Error: {e}")

    else:
        print(f"Warning: Unsupported color format '{hex_str}', using black")

    return (0.0, 0.0, 0.0)  # Default to black


def apply_text_overlays(
        pdf_id: str,
        overlays: List[Dict[str, Any]],
        default_font: str = "helv",  # built-in Helvetica
        default_size: float = 14.0,  # Increased default size
        default_color: str = "#000000",  # Black for better visibility
        write_debug_json: bool = True
) -> bytes:
    """
    Enhanced version with better text visibility and debugging
    """
    pdf_bytes = load_pdf_bytes(pdf_id)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if write_debug_json:
        # Save debug information
        debug_dir = os.path.join("instance", "debug")
        os.makedirs(debug_dir, exist_ok=True)
        debug_file = os.path.join(debug_dir, f"{pdf_id}_overlays_debug.json")
        with open(debug_file, "w", encoding="utf-8") as f:
            json.dump({
                "overlays": overlays,
                "page_count": len(doc),
                "timestamp": datetime.now().isoformat(),
                "total_overlays": len(overlays)
            }, f, ensure_ascii=False, indent=2)
        print(f"📝 Debug data saved to: {debug_file}")

    print(f"🔄 Processing {len(overlays)} overlays on {len(doc)} pages")

    for item_idx, item in enumerate(overlays):
        try:
            page_index = int(item.get("page", 0))
            if page_index < 0 or page_index >= len(doc):
                print(f"⚠️ Warning: Invalid page index {page_index}, skipping overlay {item_idx}")
                continue

            page = doc[page_index]
            rect = page.rect
            page_w, page_h = float(rect.width), float(rect.height)

            # Normalized coordinates (0-1 from top-left) to absolute points
            nx = float(item.get("x", 0))
            ny = float(item.get("y", 0))

            # Validate coordinates
            if nx < 0 or nx > 1 or ny < 0 or ny > 1:
                print(f"⚠️ Warning: Invalid coordinates ({nx}, {ny}) for overlay {item_idx}, clamping to valid range")
                nx = max(0.0, min(1.0, nx))
                ny = max(0.0, min(1.0, ny))

            # Convert to PDF coordinates (0,0 is bottom-left)
            x = nx * page_w
            y = page_h - (ny * page_h)  # Flip Y coordinate

            text = str(item.get("text", ""))
            if not text.strip():
                print(f"⚠️ Warning: Empty text for overlay {item_idx} on page {page_index}")
                continue

            font_size = float(item.get("font_size", default_size))
            color = _parse_hex_color(item.get("color", default_color))
            align = (item.get("align") or "left").lower()

            print(f"📝 Adding text {item_idx}: '{text}' at ({x:.1f}, {y:.1f}) on page {page_index}")
            print(f"   Font size: {font_size}, Color: {color}, Align: {align}")

            # Method 1: Direct text insertion with explicit parameters
            try:
                page.insert_text(
                    point=(x, y),
                    text=text,
                    fontsize=font_size,
                    fontname=default_font,
                    color=color,
                    render_mode=0,  # Fill text (solid)
                    overlay=True,
                    rotate=0  # No rotation
                )
                print(f"✅ Text inserted successfully: '{text}'")

            except Exception as e:
                print(f"❌ Error inserting text: {e}")
                # Fallback method with simpler parameters
                try:
                    page.insert_text(
                        point=(x, y),
                        text=text,
                        fontsize=font_size,
                        fontname=default_font,
                        color=color
                    )
                    print(f"✅ Text inserted using fallback method: '{text}'")
                except Exception as fallback_error:
                    print(f"❌ Fallback also failed: {fallback_error}")
                    continue

        except Exception as e:
            print(f"❌ Overlay error on page {item.get('page', 0)}: {e}")
            import traceback
            traceback.print_exc()

    # Enhanced PDF saving with better compression settings
    out = io.BytesIO()

    # Try different save options for better compatibility
    try:
        doc.save(
            out,
            garbage=4,
            deflate=True,
            clean=True,
            pretty=True  # Better formatting
        )
    except Exception as save_error:
        print(f"⚠️ Standard save failed, trying alternative: {save_error}")
        # Alternative save method
        out = io.BytesIO()
        doc.save(out)

    doc.close()

    out.seek(0)
    result_bytes = out.read()

    print(f"✅ PDF saved successfully")
    print(f"📊 Original size: {len(pdf_bytes)} bytes")
    print(f"📊 Modified size: {len(result_bytes)} bytes")
    print(f"📊 Size change: {len(result_bytes) - len(pdf_bytes)} bytes")

    return result_bytes