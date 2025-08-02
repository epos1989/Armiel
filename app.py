import os
import re
import zipfile
import uuid
import sys
import io
from flask import Flask, request, render_template, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup
from PIL import Image
from requests_html import HTMLSession
import pytesseract
from deep_translator import GoogleTranslator
from fpdf import FPDF

# Debug-Print
def log(s):
    print(s)
    sys.stdout.flush()

# Flask Setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "output"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Tesseract
pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", "tesseract")

def download_images_from_chapter(url, outdir):
    log(f"[DOWNLOAD] Starte mit {url}")
    session = HTMLSession()
    try:
        r = session.get(url, timeout=15)
        r.html.render(timeout=20)
    except Exception as e:
        log(f"[RENDER ERROR] {e}")
        return 0

    os.makedirs(outdir, exist_ok=True)
    count = 1
    seen = set()

    for img in r.html.find("img"):
        src = img.attrs.get("data-src") or img.attrs.get("src")
        if not src or not src.startswith("http") or src in seen:
            continue
        seen.add(src)
        try:
            img_data = session.get(src).content
            ext = src.split("?")[0].split(".")[-1].lower()
            ext = ext if ext in ['jpg', 'jpeg', 'png'] else 'jpg'
            filename = f"{count:03}.{ext}"
            filepath = os.path.join(outdir, filename)
            with open(filepath, "wb") as f:
                f.write(img_data)
            log(f"[BILD] Gespeichert: {filename}")
            count += 1
        except Exception as e:
            log(f"[IMG ERROR] {e} bei {src}")

    return count - 1

def ocr_translate_images(image_dir, src, tgt):
    results = []
    files = sorted(f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png')))
    for fname in files:
        path = os.path.join(image_dir, fname)
        try:
            text = pytesseract.image_to_string(Image.open(path), lang=None if src == 'auto' else src)
        except Exception as e:
            log(f"[OCR ERROR] {e}")
            text = ""
        translated = ""
        if text.strip():
            try:
                translated = GoogleTranslator(source=src, target=tgt).translate(text)
            except Exception as e:
                log(f"[Übersetzung fehlgeschlagen] {e}")
                translated = "[Fehler bei Übersetzung]"
        results.append((fname, translated))
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
    log(f"[PDF] Fertig: {outpdf}")

def create_cbz(image_dir, outcbz):
    with zipfile.ZipFile(outcbz, 'w') as z:
        for f in sorted(os.listdir(image_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                z.write(os.path.join(image_dir, f), arcname=f)
    log(f"[CBZ] Fertig: {outcbz}")

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
        download_images_from_chapter(chapter_url, img_dir)
        translated = ocr_translate_images(img_dir, src, tgt)
        pdf_path = os.path.join(out_root, f"{title}_Kapitel{ch:02}.pdf")
        create_pdf(translated, pdf_path)
        cbz_path = os.path.join(out_root, f"{title}_Kapitel{ch:02}.cbz")
        create_cbz(img_dir, cbz_path)
        combined.extend([pdf_path, cbz_path])

    zip_name = f"{title}_{session_id}_export.zip"
    zip_path = os.path.join(out_root, zip_name)
    with zipfile.ZipFile(zip_path, 'w') as z:
        for p in combined:
            if os.path.exists(p):
                z.write(p, arcname=os.path.basename(p))
    log(f"[ZIP] Exportiert: {zip_path}")
    return jsonify({"zip": zip_path})

@app.route("/download/<path:filename>")
def dl(filename):
    return send_from_directory(".", filename, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
