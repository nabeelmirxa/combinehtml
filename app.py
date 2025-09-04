from flask import Flask, request, send_file, render_template_string
from werkzeug.utils import secure_filename
import os
import zipfile
from bs4 import BeautifulSoup
import tempfile
import aiohttp
import asyncio
import logging
from urllib.parse import urljoin

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Temporary directory to store uploaded files
UPLOAD_FOLDER = tempfile.mkdtemp()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Constants for HTTP requests
HTTP_TIMEOUT = 10  # 10 seconds timeout for HTTP requests

def combine_html_from_zip(zip_file_path):
    logging.info("Processing ZIP file...")
    # Extract the zip file to a temporary directory
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        extract_path = tempfile.mkdtemp()
        zip_ref.extractall(extract_path)

    # Find the main HTML file
    html_file_path = None
    for root, _, files in os.walk(extract_path):
        for file in files:
            if file.endswith('.html'):
                html_file_path = os.path.join(root, file)
                break
        if html_file_path:
            break

    if not html_file_path:
        raise FileNotFoundError("No HTML file found in the uploaded ZIP archive.")

    # Parse the HTML file
    with open(html_file_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    # Inline CSS
    css_files = [os.path.join(root, file) for root, _, files in os.walk(extract_path) for file in files if file.endswith('.css')]
    for css_file in css_files:
        with open(css_file, 'r', encoding='utf-8') as file:
            css_content = file.read()
            style_tag = soup.new_tag('style')
            style_tag.string = css_content
            soup.head.append(style_tag)

    # Inline JavaScript
    js_files = [os.path.join(root, file) for root, _, files in os.walk(extract_path) for file in files if file.endswith('.js')]
    for js_file in js_files:
        with open(js_file, 'r', encoding='utf-8') as file:
            js_content = file.read()
            script_tag = soup.new_tag('script')
            script_tag.string = js_content
            soup.body.append(script_tag)

    # Save the modified HTML to a new file
    combined_html_path = tempfile.mktemp(suffix=".html")
    with open(combined_html_path, 'w', encoding='utf-8') as file:
        file.write(str(soup))

    logging.info("ZIP processing complete.")
    return combined_html_path

async def fetch_and_inline(session, url, tag, attr, tag_name):
    logging.info(f"Fetching {tag_name} from {url}")
    try:
        async with session.get(url, timeout=HTTP_TIMEOUT) as response:
            if response.status == 200:
                content = await response.text()
                new_tag = soup.new_tag(tag_name)
                new_tag.string = content
                tag.replace_with(new_tag)
                logging.debug(f"Inlined {tag_name} from {url}")
            else:
                logging.warning(f"Failed to fetch {tag_name} from {url}: Status {response.status}")
    except Exception as e:
        logging.warning(f"Error fetching {tag_name} from {url}: {e}")

async def fetch_and_combine_url(url):
    async with aiohttp.ClientSession() as session:
        response = await session.get(url, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        html_content = await response.text()
        soup = BeautifulSoup(html_content, 'html.parser')

        tasks = []

        # Inline CSS from <link> tags
        for link in soup.find_all('link', href=True):
            href = link['href']
            if 'stylesheet' in link.get('rel', []):
                css_url = urljoin(url, href)
                tasks.append(fetch_and_inline(session, css_url, link, 'href', 'style'))

        # Inline JavaScript from <script> tags
        for script in soup.find_all('script', src=True):
            src = script['src']
            js_url = urljoin(url, src)
            tasks.append(fetch_and_inline(session, js_url, script, 'src', 'script'))

        await asyncio.gather(*tasks)

        # Save the modified HTML to a new file
        combined_html_path = tempfile.mktemp(suffix=".html")
        with open(combined_html_path, 'w', encoding='utf-8') as file:
            file.write(str(soup))

    logging.info(f"URL processing complete for {url}.")
    return combined_html_path

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' in request.files and request.files['file'].filename != '':
            # Handle ZIP file upload
            file = request.files['file']
            filename = secure_filename(file.filename)
            zip_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(zip_file_path)

            try:
                combined_html_path = combine_html_from_zip(zip_file_path)
                return send_file(combined_html_path, as_attachment=True, download_name='combined_from_zip.html')
            except Exception as e:
                logging.error(f"Error processing ZIP: {e}")
                return f"An error occurred: {e}"

        elif 'url' in request.form and request.form['url']:
            # Handle URL input
            url = request.form['url']
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                combined_html_path = loop.run_until_complete(fetch_and_combine_url(url))
                return send_file(combined_html_path, as_attachment=True, download_name='combined_from_url.html')
            except Exception as e:
                logging.error(f"Error processing URL: {e}")
                return f"An error occurred: {e}"

    # Enhanced HTML form for file upload with CSS styling
    html_form = '''
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Upload ZIP File or Enter URL</title>
        <style>
            body {
                background: linear-gradient(135deg, #ececec, #f8f8f8);
                font-family: Arial, sans-serif;
                height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 0;
            }
            .upload-form {
                background: rgba(255, 255, 255, 0.8);
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
                border-radius: 12px;
                padding: 30px;
                max-width: 400px;
                width: 100%;
                text-align: center;
            }
            input[type="file"],
            input[type="text"],
            input[type="submit"] {
                display: block;
                width: calc(100% - 40px);
                margin: 10px auto;
                padding: 10px;
                font-size: 16px;
                border: none;
                border-radius: 5px;
            }
            input[type="file"] {
                display: none;
            }
            label {
                background-color: #4caf50;
                color: white;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                transition: background-color 0.3s;
            }
            label:hover {
                background-color: #45a049;
            }
            input[type="submit"] {
                background-color: #008cba;
                color: white;
                cursor: pointer;
                transition: background-color 0.3s;
                margin-top: 20px;
            }
            input[type="submit"]:hover {
                background-color: #007bb5;
            }
            h1 {
                color: #333;
            }
        </style>
    </head>
    <body>
        <div class="upload-form">
            <h1>Upload a ZIP File or Enter a URL</h1>
            <form method="post" enctype="multipart/form-data">
                <label for="file">Choose File</label>
                <input type="file" name="file" id="file">
                <input type="text" name="url" placeholder="Enter URL">
                <input type="submit" value="Process">
            </form>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_form)

if __name__ == '__main__':
    app.run(debug=True)
