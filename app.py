from flask import Flask, request, render_template, send_from_directory, jsonify
import os, zipfile, uuid
from werkzeug.utils import secure_filename
import requests
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
from deep_translator import GoogleTranslator
from fpdf import FPDF

# Tesseract-Pfad (wenn lokal installiert, reicht "tesseract"; bei portablem fallback ggf anpassen)
pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", "tesseract")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "output"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def download_images_from_chapter(url, outdir):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        print(f"Fehler beim Laden der Kapitel-URL {url}: {e}")
        return 0
    soup = BeautifulSoup(r.text, 'html.parser')
    os.makedirs(outdir, exist_ok=True)
    count = 1

    # Versuch 1: alle sichtbaren <img>-Tags
    img_tags = soup.find_all("img")
    for img in img_tags:
        src = img.get("data-src") or img.get("src")
        if not src or not src.startswith("http"):
            continue
        try:
            data = requests.get(src, headers=headers, timeout=15).content
            fname = f"{count:03}.jpg"
            with open(os.path.join(outdir, fname), "wb") as f:
                f.write(data)
            count += 1
        except:
            continue

    # Versuch 2: falls JS-Rendering nötig, suche in scripts nach Bild-URLs (einfacher Fall)
    if count == 1:
        text = r.text
        possible = set()
        for part in text.split('"'):
            if part.lower().startswith("http") and any(ext in part.lower() for ext in [".jpg", ".jpeg", ".png"]):
                possible.add(part)
        for src in sorted(possible):
            if count > 200:  # Sicherheitslimit
                break
            try:
                data = requests.get(src, headers=headers, timeout=15).content
                fname = f"{count:03}.jpg"
                with open(os.path.join(outdir, fname), "wb") as f:
                    f.write(data)
                count += 1
            except:
                continue

    return count - 1

def ocr_translate_images(image_dir, src, tgt):
    results = []
    files = sorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    for f in files:
        path = os.path.join(image_dir, f)
        try:
            text = pytesseract.image_to_string(Image.open(path), lang=None if src == 'auto' else src)
        except Exception:
            text = ""
        if text.strip():
            try:
                translated = GoogleTranslator(source='auto' if src == 'auto' else src, target=tgt).translate(text)
            except:
                translated = "[Übersetzung fehlgeschlagen]"
        else:
            translated = ""
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

def create_cbz(image_dir, outcbz):
    with zipfile.ZipFile(outcbz, 'w') as z:
        for f in sorted(os.listdir(image_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                z.write(os.path.join(image_dir, f), arcname=f)

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
    return jsonify({"zip": zip_path})

@app.route("/download/<path:filename>")
def dl(filename):
    return send_from_directory(".", filename, as_attachment=True)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
