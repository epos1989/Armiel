import os
import re
import zipfile
import uuid
import sys
from flask import Flask, request, render_template, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
from deep_translator import GoogleTranslator
from fpdf import FPDF
import io
import requests
from requests_html import HTMLSession  # NEU

# Logging helper
def log(s):
    print(s)
    sys.stdout.flush()

# Tesseract konfigurieren
pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", "tesseract")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "output"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def download_images_from_chapter(url, outdir):
    os.makedirs(outdir, exist_ok=True)
    session = HTMLSession()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": url
    }

    log(f"[INFO] Lade Seite: {url}")
    try:
        r = session.get(url, headers=headers)
        r.html.render(timeout=20)  # JavaScript ausführen
    except Exception as e:
        log(f"[ERROR] render() fehlgeschlagen: {e}")
        return 0

    images = r.html.find("img")
    count = 1
    seen = set()

    for img in images:
        src = img.attrs.get("src") or img.attrs.get("data-src")
        if not src or not src.startswith("http") or "chapter" not in src:
            continue
        if src in seen:
            continue
        seen.add(src)
        try:
            img_data = requests.get(src, headers=headers, timeout=15).content
            ext = os.path.splitext(src.split("?")[0])[-1]
            if ext.lower() == ".webp":
                im = Image.open(io.BytesIO(img_data)).convert("RGB")
                fname = f"{count:03}.jpg"
                im.save(os.path.join(outdir, fname), format="JPEG")
            else:
                fname = f"{count:03}.{ext.lstrip('.')}" if ext else f"{count:03}.jpg"
                with open(os.path.join(outdir, fname), "wb") as f:
                    f.write(img_data)
            log(f"[✔️] Gespeichert: {fname}")
            count += 1
        except Exception as e:
            log(f"[FEHLER] Bild konnte nicht geladen werden: {e}")

    log(f"[RESULT] {count-1} Bilder gespeichert.")
    return count - 1

def ocr_translate_images(image_dir, src, tgt):
    results = []
    files = sorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    for f in files:
        path = os.path.join(image_dir, f)
        try:
            text = pytesseract.image_to_string(Image.open(path), lang=None if src == 'auto' else src)
        except Exception as e:
            log(f"[OCR ERROR] {e} bei {path}")
            text = ""
        translated = ""
        if text.strip():
            try:
                translated = GoogleTranslator(source='auto' if src == 'auto' else src, target=tgt).translate(text)
            except Exception as e:
                log(f"[TRANSLATE ERROR] {e} für Text von {f}")
                translated = "[Übersetzung fehlgeschlagen]"
        results.append((f, translated))
    return results

def create_pdf(translated_list, outpdf):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for fname, text in translated_list:
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, f"Seite: {fname}", ln=1)
        pdf.set_font("Arial", "", 12)
        for line in text.split("\n"):
            pdf.multi_cell(0, 8, line)
    pdf.output(outpdf)
    log(f"[PDF] Erstellt: {outpdf}")

def create_cbz(image_dir, outcbz):
    with zipfile.ZipFile(outcbz, 'w') as z:
        for f in sorted(os.listdir(image_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                z.write(os.path.join(image_dir, f), arcname=f)
    log(f"[CBZ] Erstellt: {outcbz}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    data = request.form
    url = data.get("url")
    start = int(data.get("start", 1))
    end = int(data.get("end", 1))
    src = data.get("src", "auto")
    tgt = data.get("tgt", "de")
    session_id = str(uuid.uuid4())[:8]
    title = secure_filename(url.strip("/").split("/")[-2])
    out_root = os.path.join(app.config['UPLOAD_FOLDER'], f"{title}_{session_id}")
    os.makedirs(out_root, exist_ok=True)
    combined = []

    for ch in range(start, end + 1):
        chapter_url = f"{url.rstrip('/')}/chapter-{ch}/"
        img_dir = os.path.join(out_root, f"chapter_{ch:02}")
        num = download_images_from_chapter(chapter_url, img_dir)
        if num == 0:
            log(f"[WARNUNG] Keine Bilder gefunden für Kapitel {ch}")
            continue
        translated = ocr_translate_images(img_dir, src, tgt)
        pdf_path = os.path.join(out_root, f"{title}_Kapitel{ch:02}.pdf")
        create_pdf(translated, pdf_path)
        cbz_path = os.path.join(out_root, f"{title}_Kapitel{ch:02}.cbz")
        create_cbz(img_dir, cbz_path)
        combined.extend([pdf_path, cbz_path])

        # Debug: Inhalt des Bildordners
        if os.path.isdir(img_dir):
            files = sorted(os.listdir(img_dir))
            log(f"[DEBUG] Inhalt von {img_dir}: {files}")
        else:
            log(f"[DEBUG] Ordner fehlt: {img_dir}")

    zip_name = f"{title}_{session_id}_export.zip"
    zip_path = os.path.join(out_root, zip_name)
    with zipfile.ZipFile(zip_path, 'w') as z:
        for p in combined:
            if os.path.exists(p):
                z.write(p, arcname=os.path.basename(p))
    log(f"[ZIP] Erstellt: {zip_path}")
    return jsonify({"zip": zip_path})

@app.route("/download/<path:filename>")
def dl(filename):
    return send_from_directory(".", filename, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
