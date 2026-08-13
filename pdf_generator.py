import fitz # PyMuPDF
import io
import datetime

# Exact Column X-Cell Boundaries (min_x, max_x) across ERP document layouts (page width = 595.2)
COLUMN_BOUNDS = {
    "SLI": {
        "value": (485.0, 550.0),
        "total_value_usd": (485.0, 550.0),
        "value_usd": (485.0, 550.0),
        "net_weight": (442.0, 502.0),
        "net_weight_kg": (442.0, 502.0),
        "gross_weight": (380.0, 438.0),
        "gross_weight_kg": (380.0, 438.0),
        "qty": (330.0, 377.0),
        "quantity": (330.0, 377.0),
    },
    "CIV": {
        "value": (480.0, 555.0),
        "total_value": (480.0, 555.0),
        "total_amount": (480.0, 555.0),
        "unit_price": (415.0, 480.0),
        "qty": (330.0, 410.0),
    },
    "PKL": {
        "gross_weight": (365.0, 455.0),
        "gross_weight_kg": (365.0, 455.0),
        "net_weight": (460.0, 550.0),
        "net_weight_kg": (460.0, 550.0),
        "qty": (280.0, 360.0),
    },
    "VGM": {
        "weight": (320.0, 520.0),
        "vgm_weight": (320.0, 520.0),
        "gross_weight_kg": (320.0, 520.0),
    }
}

def get_field_column_bounds(doc_type, field_name):
    """
    Returns (min_x, target_x1) bounding box tuple for a field if it belongs to a table column,
    else returns None (no column restriction).
    """
    doc_bounds = COLUMN_BOUNDS.get(doc_type.upper(), {})
    field_lower = field_name.lower()
    
    # Check exact match
    if field_lower in doc_bounds:
        return doc_bounds[field_lower]
        
    # Check partial match for nested item fields (e.g. items_0_value_usd -> value_usd)
    for sub, bounds in doc_bounds.items():
        if sub in field_lower:
            return bounds
            
    return None

def get_candidates(field, val):
    """
    Generates potential string formatting candidates for numeric/text values
    to locate them on the PDF page vector.
    """
    candidates = []
    val_str = str(val).strip()
    if val_str and val_str not in ["0.0", "0", "None"]:
        candidates.append((val_str, lambda x: f"{float(x):.3f}" if "." in val_str else str(x)))

    try:
        val_float = float(val)
        val_int = int(val_float)
        
        candidates.append((f"{val_float:.3f}", lambda x: f"{float(x):.3f}"))
        candidates.append((f"{val_float:.2f}", lambda x: f"{float(x):.2f}"))
        candidates.append((f"{val_float:.1f}", lambda x: f"{float(x):.1f}"))
        
        if abs(val_float) >= 1000:
            candidates.append((f"{val_int:,}", lambda x: f"{int(float(x)):,}"))
            candidates.append((f"{val_float:,.2f}", lambda x: f"{float(x):,.2f}"))
            candidates.append((f"{val_float:,.3f}", lambda x: f"{float(x):,.3f}"))
            candidates.append((f"{val_int}", lambda x: f"{int(float(x))}"))
        else:
            candidates.append((f"{val_int}", lambda x: f"{int(float(x))}"))
    except (ValueError, TypeError):
        pass
        
    seen = set()
    unique_candidates = []
    for search_str, formatter in candidates:
        if search_str not in seen and search_str != "" and search_str != "0.0" and search_str != "0":
            if isinstance(val, (int, float)) and abs(float(val)) >= 100 and len(search_str) < 3:
                continue
            seen.add(search_str)
            unique_candidates.append((search_str, formatter))
            
    unique_candidates.sort(key=lambda x: len(x[0]), reverse=True)
    return unique_candidates

def generate_audited_pdf(shipment_id, document_type, resolved_data, original_data, original_pdf_bytes):
    """
    Surgical Vector PDF Editing using PyMuPDF (fitz) with Full Word Match Token Filtering.
    Searches for original values ONLY inside designated table column cells,
    verifies full word token matches to prevent partial digit corruption,
    and stamps 100% complete untruncated audited values.
    """
    doc = fitz.open(stream=original_pdf_bytes, filetype="pdf")
    document_type = document_type.upper()
    
    # Identify top-level field overrides
    overrides = {}
    for field, new_val in resolved_data.items():
        if field == "items":
            continue
        orig_val = original_data.get(field)
        if orig_val is not None and str(orig_val) != str(new_val):
            overrides[field] = {
                'original': orig_val,
                'audited': new_val
            }
            
    # Process nested item overrides (e.g. items_0_value_usd)
    resolved_items = resolved_data.get("items", [])
    original_items = original_data.get("items", [])
    if hasattr(resolved_items, "tolist"):
        resolved_items = resolved_items.tolist()
    if hasattr(original_items, "tolist"):
        original_items = original_items.tolist()
        
    if isinstance(resolved_items, list) and isinstance(original_items, list):
        for idx in range(min(len(resolved_items), len(original_items))):
            res_item = resolved_items[idx]
            orig_item = original_items[idx]
            if isinstance(res_item, dict) and isinstance(orig_item, dict):
                for subfield, new_val in res_item.items():
                    orig_val = orig_item.get(subfield)
                    if orig_val is not None and str(orig_val) != str(new_val):
                        item_key = f"items_{idx}_{subfield}"
                        overrides[item_key] = {
                            'original': orig_val,
                            'audited': new_val,
                            'item_index': idx
                        }
                        
    if not overrides:
        return original_pdf_bytes
        
    for field, info in overrides.items():
        orig_val = info['original']
        audited_val = info['audited']
        item_idx = info.get('item_index', None)
        
        # Determine column bounds if this field belongs to a table column
        bounds = get_field_column_bounds(document_type, field)
        candidates = get_candidates(field, orig_val)
        
        for search_str, formatter in candidates:
            found_any = False
            for page in doc:
                rects = page.search_for(search_str)
                if not rects:
                    continue
                    
                # Strict column cell bounding box filtering
                if bounds:
                    min_x, max_x = bounds
                    valid_rects = [r for r in rects if min_x <= r.x0 and r.x1 <= max_x + 5.0]
                else:
                    valid_rects = list(rects)
                    
                # Full word match token filtering to prevent partial digit replacement
                words = page.get_text("words")
                full_word_rects = []
                for vr in valid_rects:
                    for w in words:
                        w_text = w[4].strip()
                        w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
                        if vr.intersects(w_rect) and (search_str == w_text or search_str in w_text.split() or w_text.startswith(search_str)):
                            full_word_rects.append(vr)
                            break
                            
                if full_word_rects:
                    full_word_rects.sort(key=lambda r: r.y0)
                    
                    # Target rect selection for item row
                    target_rects = full_word_rects
                    if item_idx is not None and len(full_word_rects) > 1:
                        target_rects = [full_word_rects[min(item_idx, len(full_word_rects) - 1)]]
                        
                    found_any = True
                    for rect in target_rects:
                        new_text = formatter(audited_val)
                        h = rect.y1 - rect.y0
                        fontsize = max(8, min(8.5, h * 0.85))
                        fontname = "cour" if document_type in ["SLI", "PKL", "CIV"] else "helv"
                        
                        # Calculate exact string width for clean cell masking
                        text_width = fitz.get_text_length(new_text, fontname=fontname, fontsize=fontsize)
                        
                        # Anchor at exact original starting position rect.x0
                        x_pos = rect.x0
                        mask_rect = fitz.Rect(
                            rect.x0 - 2.0,
                            rect.y0 - 1.0,
                            max(rect.x1 + 3.0, rect.x0 + text_width + 3.0),
                            rect.y1 + 1.0
                        )
                        
                        # 1. Mask old text with clean white rectangle
                        page.draw_rect(
                            mask_rect,
                            color=fitz.pdfcolor["white"],
                            fill=fitz.pdfcolor["white"]
                        )
                        
                        # 2. Stamp complete untruncated text at rect.x0
                        page.insert_text(
                            fitz.Point(x_pos, rect.y1 - 1.5),
                            new_text,
                            fontsize=fontsize,
                            fontname=fontname,
                            color=(0.1, 0.1, 0.1)
                        )
            if found_any:
                break
                
    out_buffer = io.BytesIO()
    doc.save(out_buffer)
    pdf_bytes = out_buffer.getvalue()
    out_buffer.close()
    doc.close()
    
    return pdf_bytes

