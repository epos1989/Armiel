import os
import sys
from PIL import Image
import pytesseract
from deep_translator import GoogleTranslator
from fpdf import FPDF

def inspect_images(image_dir):
    images = sorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    info = []
    for img in images:
        path = os.path.join(image_dir, img)
        try:
            size = os.path.getsize(path)
            with Image.open(path) as im:
                mode = im.mode
                size_px = im.size
            info.append((img, size, mode, size_px))
        except Exception as e:
            info.append((img, None, None, None, f"ERROR: {e}"))
    return info

def ocr_on_image(image_path, lang='auto'):
    try:
        if lang == 'auto':
            text = pytesseract.image_to_string(Image.open(image_path))
        else:
            text = pytesseract.image_to_string(Image.open(image_path), lang=lang)
        return text.strip()
    except Exception as e:
        return f"[OCR ERROR] {e}"

def translate_text(text, target='de'):
    try:
        if not text:
            return ""
        translated = GoogleTranslator(source='auto', target=target).translate(text)
        return translated
    except Exception as e:
        return f"[TRANSLATE ERROR] {e}"

def make_preview_pdf(ocr_text, translated_text, output_path):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Debug Vorschau: OCR + Übersetzung", ln=1)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Original (OCR):", ln=1)
    pdf.set_font("Arial", "", 11)
    for line in ocr_text.split("\n"):
        pdf.multi_cell(0, 7, line)
    pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Übersetzt (Deutsch):", ln=1)
    pdf.set_font("Arial", "", 11)
    for line in translated_text.split("\n"):
        pdf.multi_cell(0, 7, line)
    pdf.output(output_path)

def main():
    if len(sys.argv) != 2:
        print("Usage: python debug_helper.py <chapter_image_directory>")
        sys.exit(1)
    image_dir = sys.argv[1]
    if not os.path.isdir(image_dir):
        print(f"Directory not found: {image_dir}")
        sys.exit(1)

    summary_lines = []
    summary_lines.append(f"Debug für Verzeichnis: {image_dir}\n")

    # 1. Inspect images
    summary_lines.append("1. Gefundene Bilder:\n")
    images_info = inspect_images(image_dir)
    if not images_info:
        summary_lines.append("  Keine Bilddateien gefunden.\n")
    else:
        for info in images_info[:10]:
            if len(info) == 4:
                name, size, mode, dims = info
                summary_lines.append(f"  {name}: {size} bytes, mode={mode}, dims={dims}\n")
            else:
                summary_lines.append(f"  {info}\n")
        if len(images_info) > 10:
            summary_lines.append(f"  ... noch {len(images_info)-10} weitere Bilder\n")

    # 2. OCR auf erstem Bild
    if images_info:
        first_image = images_info[0][0]
        summary_lines.append("\n2. OCR auf erstem Bild:\n")
        ocr_text = ocr_on_image(os.path.join(image_dir, first_image))
        summary_lines.append(ocr_text + "\n")

        # 3. Übersetzung
        summary_lines.append("\n3. Übersetzung ins Deutsche:\n")
        translated = translate_text(ocr_text, target='de')
        summary_lines.append(translated + "\n")

        # 4. Vorschau-PDF erstellen
        preview_pdf = os.path.join(image_dir, "debug_preview.pdf")
        make_preview_pdf(ocr_text, translated, preview_pdf)
        summary_lines.append(f"\n4. Vorschau-PDF erstellt: {preview_pdf}\n")
    else:
        summary_lines.append("Keine OCR/Übersetzung möglich, da keine Bilder vorhanden.\n")

    # 5. Speichere Zusammenfassung
    summary_path = os.path.join(image_dir, "debug_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.writelines(summary_lines)
    print("Fertig. Summary gespeichert in:", summary_path)
    if images_info:
        print("OCR Text Beispiel:\n", ocr_text[:400])
        print("Übersetzung Beispiel:\n", translated[:400])
    print("Preview PDF:", preview_pdf if images_info else "nicht erstellt")

if __name__ == "__main__":
    main()
