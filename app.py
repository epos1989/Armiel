from flask import Flask, request, render_template_string, send_file
from playwright.sync_api import sync_playwright
import os
import shutil
import requests
import zipfile

app = Flask(__name__)

HTML = """
<!doctype html>
<title>Toongod Downloader</title>
<h1>Toongod Kapitel Downloader</h1>
<form method=post>
  Kapitel-URL: <input type=text name=url style="width: 500px;">
  <input type=submit value=Download>
</form>
{% if zip_url %}
  <p>Download fertig: <a href="{{ zip_url }}">Hier klicken</a></p>
{% endif %}
"""

def download_image(url, path):
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(path, "wb") as f:
            shutil.copyfileobj(r.raw, f)
        print(f"Downloaded {url}")
    else:
        print(f"Failed to download {url}")

def scrape_images(chapter_url, folder):
    os.makedirs(folder, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(chapter_url)
        page.wait_for_selector("img.img-fluid")
        imgs = page.query_selector_all("img.img-fluid")
        print(f"Gefundene Bilder: {len(imgs)}")
        for i, img in enumerate(imgs, start=1):
            src = img.get_attribute("src")
            if src:
                download_image(src, os.path.join(folder, f"page_{i}.jpg"))
        browser.close()

def make_zip(folder, zip_path):
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            zipf.write(file_path, filename)
    print(f"ZIP erstellt: {zip_path}")

@app.route("/", methods=["GET", "POST"])
def index():
    zip_url = None
    if request.method == "POST":
        url = request.form.get("url")
        if url:
            folder = "temp_images"
            zip_path = "output.zip"
            if os.path.exists(folder):
                shutil.rmtree(folder)
            scrape_images(url, folder)
            make_zip(folder, zip_path)
            zip_url = "/download"
    return render_template_string(HTML, zip_url=zip_url)

@app.route("/download")
def download():
    path = "output.zip"
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "Datei nicht gefunden", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
