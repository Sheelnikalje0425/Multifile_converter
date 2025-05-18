from flask import Flask, request, render_template, send_file, after_this_request
import tempfile
import os
import shutil
from werkzeug.utils import secure_filename

# Libraries for conversion
from docx2pdf import convert as docx2pdf_convert
from pdf2docx import Converter as PDF2DocxConverter
import img2pdf
import zipfile
from pdf2image import convert_from_path
from PIL import Image
from PyPDF2 import PdfMerger, PdfReader, PdfWriter

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return 'No files uploaded.'

    files = request.files.getlist('file')
    conversion_type = request.form.get('conversion_type')

    tmpdir = tempfile.mkdtemp()

    try:
        output_files = []

        if conversion_type == 'merge_pdfs':
            for file in files:
                if not file.filename.endswith('.pdf'):
                    return 'All files must be PDF for merging.'

            merger = PdfMerger()
            for file in files:
                input_path = os.path.join(tmpdir, secure_filename(file.filename))
                file.save(input_path)
                merger.append(input_path)

            output_path = os.path.join(tmpdir, 'merged.pdf')
            merger.write(output_path)
            merger.close()
            output_files.append(output_path)

        elif conversion_type == 'protect_pdf':
            if len(files) != 1:
                return 'Upload only one PDF to protect.'

            password = request.form.get('password')
            if not password:
                return 'Please provide a password.'

            file = files[0]
            if not file.filename.endswith('.pdf'):
                return 'Please upload a PDF file.'

            input_path = os.path.join(tmpdir, secure_filename(file.filename))
            file.save(input_path)

            reader = PdfReader(input_path)
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            writer.encrypt(password)

            output_path = os.path.join(tmpdir, 'protected.pdf')
            with open(output_path, 'wb') as f:
                writer.write(f)

            output_files.append(output_path)

        else:
            for file in files:
                input_path = os.path.join(tmpdir, secure_filename(file.filename))
                file.save(input_path)

                output_path = ""

                if conversion_type == 'word_to_pdf':
                    if not input_path.endswith('.docx'):
                        return 'Please upload a .docx file.'
                    output_path = input_path.replace('.docx', '.pdf')
                    docx2pdf_convert(input_path, output_path)

                elif conversion_type == 'pdf_to_word':
                    if not input_path.endswith('.pdf'):
                        return 'Please upload a .pdf file.'
                    output_path = input_path.replace('.pdf', '.docx')
                    cv = PDF2DocxConverter(input_path)
                    cv.convert(output_path, start=0, end=None)
                    cv.close()

                elif conversion_type == 'jpg_to_pdf':
                    if not (input_path.endswith('.jpg') or input_path.endswith('.jpeg')):
                        return 'Please upload a .jpg file.'
                    output_path = input_path.replace('.jpg', '.pdf').replace('.jpeg', '.pdf')
                    with open(output_path, "wb") as f:
                        f.write(img2pdf.convert(input_path))

                elif conversion_type == 'pdf_to_jpg':
                    if not input_path.endswith('.pdf'):
                        return 'Please upload a .pdf file.'
                    images = convert_from_path(input_path)
                    zip_path = input_path.replace('.pdf', '.zip')
                    jpg_files = []
                    for idx, img in enumerate(images):
                        img_filename = os.path.join(tmpdir, f'page_{idx + 1}.jpg')
                        img.save(img_filename, 'JPEG')
                        jpg_files.append(img_filename)
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for jpg_file in jpg_files:
                            zipf.write(jpg_file, arcname=os.path.basename(jpg_file))
                    output_path = zip_path

                elif conversion_type == 'jpg_to_png':
                    if not (input_path.endswith('.jpg') or input_path.endswith('.jpeg')):
                        return 'Please upload a .jpg file.'
                    img = Image.open(input_path)
                    output_path = input_path.replace('.jpg', '.png').replace('.jpeg', '.png')
                    img.save(output_path, 'PNG')

                elif conversion_type == 'png_to_jpg':
                    if not input_path.endswith('.png'):
                        return 'Please upload a .png file.'
                    img = Image.open(input_path)
                    output_path = input_path.replace('.png', '.jpg')
                    img.convert('RGB').save(output_path, 'JPEG')

                else:
                    return 'Invalid conversion type selected.'

                output_files.append(output_path)

        if len(output_files) > 1:
            zip_path = os.path.join(tmpdir, 'converted_files.zip')
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for output_file in output_files:
                    zipf.write(output_file, arcname=os.path.basename(output_file))
            output_path = zip_path
        else:
            output_path = output_files[0]

        @after_this_request
        def cleanup(response):
            try:
                shutil.rmtree(tmpdir)
            except Exception as e:
                print(f'Error deleting temp files: {e}')
            return response

        return send_file(output_path, as_attachment=True, download_name=os.path.basename(output_path))

    except Exception as e:
        shutil.rmtree(tmpdir)
        return f"An error occurred: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True)
