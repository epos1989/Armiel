import os
import re
import zipfile
import uuid
import sys
import requests
from flask import Flask, request, render_template, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
from deep_translator import GoogleTranslator
from fpdf import FPDF
import io

# Logging helper, damit Ausgaben sofort im Render-Log auftauchen
def log(s):
    print(s)
    sys.stdout.flush()

# Tesseract-Pfad (falls nötig anpassen, auf Render sollte "tesseract" funktionieren)
pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", "tesseract")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "output"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def download_images_from_chapter(url, outdir):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": url
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log(f"[DOWNLOAD ERROR] Kapitel-URL laden fehlgeschlagen: {e}")
        return 0

    soup = BeautifulSoup(r.text, "html.parser")
    os.makedirs(outdir, exist_ok=True)
    count = 1
    seen = set()

    def save_image_from_url(src_url):
        nonlocal count
        if src_url in seen:
            return
        seen.add(src_url)
        try:
            img_resp = requests.get(src_url, headers=headers, timeout=15)
            img_resp.raise_for_status()
            content = img_resp.content
            ext = src_url.split("?")[0].split(".")[-1].lower()
            if ext == "webp":
                try:
                    im = Image.open(io.BytesIO(content)).convert("RGB")
                    fname = f"{count:03}.jpg"
                    im.save(os.path.join(outdir, fname), format="JPEG")
                except Exception as e:
                    log(f"[CONVERT ERROR] WebP zu JPG fehlgeschlagen: {e}")
                    return
            else:
                fname = f"{count:03}.{ext if ext in ['jpg','jpeg','png'] else 'jpg'}"
                with open(os.path.join(outdir, fname), "wb") as f:
                    f.write(content)
            log(f"[DOWNLOAD] Bild gespeichert: {fname} from {src_url}")
            count += 1
        except Exception as e:
            log(f"[IMAGE ERROR] {e} bei {src_url}")

    # Versuch 1: direkte <img>-Quellen
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src")
        if not src or not src.lower().startswith("http"):
            continue
        save_image_from_url(src)

    # Versuch 2: Fallback via Regex (wenn noch keine Bilder)
    if count == 1:
        pattern = re.compile(r'(https?://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?)', re.IGNORECASE)
        matches = pattern.findall(r.text)
        for src in sorted(set(matches)):
            if count > 200:
                break
            save_image_from_url(src)

    log(f"[RESULT] {count-1} Bilder für {url} gespeichert.")
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
