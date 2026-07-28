import fitz # PyMuPDF
import io
import datetime

def get_candidates(field, val):
    """
    Generates potential string formatting candidates for numeric/text values
    to locate them on the PDF page vector, paired with formatting functions
    to replicate their exact visual style.
    """
    candidates = []
    try:
        val_float = float(val)
        val_int = int(val_float)
        
        # 1. Comma with 3 decimals (e.g., 14,210.500)
        candidates.append((f"{val_float:,.3f}", lambda x: f"{float(x):,.3f}"))
        
        # 2. Comma with 2 decimals (e.g., 94,725.00)
        candidates.append((f"{val_float:,.2f}", lambda x: f"{float(x):,.2f}"))
        
        # 3. Comma with 1 decimal (e.g., 14,210.5)
        candidates.append((f"{val_float:,.1f}", lambda x: f"{float(x):,.1f}"))
        
        # 4. No comma with 3 decimals (e.g., 14210.500)
        candidates.append((f"{val_float:.3f}", lambda x: f"{float(x):.3f}"))
        
        # 5. No comma with 2 decimals (e.g., 94725.00)
        candidates.append((f"{val_float:.2f}", lambda x: f"{float(x):.2f}"))
        
        # 6. No comma with 1 decimal (e.g., 14210.5)
        candidates.append((f"{val_float:.1f}", lambda x: f"{float(x):.1f}"))
        
        # 7. Comma with no decimals (e.g., 94,725)
        candidates.append((f"{val_int:,}", lambda x: f"{int(float(x)):,}"))
        
        # 8. Raw integer (e.g., 14)
        candidates.append((f"{val_int}", lambda x: f"{int(float(x))}"))
        
        # 9. Raw float string representation
        candidates.append((str(val), lambda x: str(x)))
    except (ValueError, TypeError):
        # String fallback
        val_str = str(val).strip()
        candidates.append((val_str, lambda x: str(x)))
        
    seen = set()
    unique_candidates = []
    for search_str, formatter in candidates:
        if search_str not in seen and search_str != "" and search_str != "0.0" and search_str != "0":
            seen.add(search_str)
            unique_candidates.append((search_str, formatter))
            
    # Sort candidates by length in descending order to match the longest (most precise) string first
    unique_candidates.sort(key=lambda x: len(x[0]), reverse=True)
    return unique_candidates

def generate_audited_pdf(shipment_id, document_type, resolved_data, original_data, original_pdf_bytes):
    """
    Direct Vector PDF Editing using PyMuPDF (fitz).
    Searches for the original values on the original PDF, redaction-masks them,
    and overlays the corrected values in-place.
    """
    # Open original PDF from bytes
    doc = fitz.open(stream=original_pdf_bytes, filetype="pdf")
    
    # We identify which fields are actually overridden/changed
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
            
    # Process nested item overrides (e.g. individual weights/values in CIV or SLI)
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
                            'audited': new_val
                        }
                        
    # If there are no overrides, we return the original bytes as is
    if not overrides:
        return original_pdf_bytes
        
    # Process each override
    for field, info in overrides.items():
        orig_val = info['original']
        audited_val = info['audited']
        
        # Generate candidates for searching
        candidates = get_candidates(field, orig_val)
        
        for search_str, formatter in candidates:
            found_any = False
            for page in doc:
                rects = page.search_for(search_str)
                if rects:
                    found_any = True
                    for rect in rects:
                        # 1. Redact / mask old text with white (adding a 4px padding on the right to cover any trailing unaligned decimal places)
                        redact_rect = fitz.Rect(rect.x0, rect.y0, rect.x1 + 4, rect.y1)
                        page.draw_rect(
                            redact_rect,
                            color=fitz.pdfcolor["white"],
                            fill=fitz.pdfcolor["white"]
                        )
                        
                        # 2. Format new audited value to match precision/style
                        new_text = formatter(audited_val)
                        
                        # 3. Stamp corrected value in place
                        h = rect.y1 - rect.y0
                        fontsize = max(8, min(11, h * 0.85)) # Dynamic font scaling
                        
                        # Select font based on document type (use Courier 'cour' for monospaced ERP grid layouts to match style and column alignment)
                        fontname = "cour" if document_type in ["SLI", "PKL", "CIV"] else "helv"
                        
                        page.insert_text(
                            fitz.Point(rect.x0, rect.y1 - 1.5), # Anchor at bottom-left
                            new_text,
                            fontsize=fontsize,
                            fontname=fontname,
                            color=(0.15, 0.15, 0.15) # Elegant corporate charcoal text
                        )
            # If we found and replaced this candidate on any page,
            # we don't need to try the other less-precise candidate formats for this field.
            if found_any:
                break
                
    # Save modified PDF to bytes
    out_buffer = io.BytesIO()
    doc.save(out_buffer)
    pdf_bytes = out_buffer.getvalue()
    out_buffer.close()
    doc.close()
    
    return pdf_bytes
