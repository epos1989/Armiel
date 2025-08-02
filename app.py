from flask import Flask, request, render_template, send_file
from playwright.sync_api import sync_playwright
import os
import shutil
import requests
import zipfile

app = Flask(__name__)

def download_image(url, path):
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(path, "wb") as f:
            shutil.copyfileobj(r.raw, f)

def scrape_images(chapter_url, folder):
    os.makedirs(folder, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(chapter_url)
        page.wait_for_selector("img.img-fluid")
        imgs = page.query_selector_all("img.img-fluid")
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

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    url = request.form.get("url")
    if url:
        folder = "temp_images"
        zip_path = "output.zip"
        if os.path.exists(folder):
            shutil.rmtree(folder)
        scrape_images(url, folder)
        make_zip(folder, zip_path)
        return render_template("index.html", zip_url="/download")
    return render_template("index.html", zip_url=None)

@app.route("/download")
def download():
    path = "output.zip"
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "Datei nicht gefunden", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
