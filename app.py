from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import re
import traceback
from flask import render_template
import pdfplumber
from werkzeug.utils import secure_filename
import io
import os
import pypdfium2 as pdfium 
import pytesseract 
import cv2
from PyPDF2 import PdfReader

app = Flask(__name__)
CORS(app)

openai.api_key = "your open AI key here"

def split_text(text, max_length):
    words = text.split(' ')
    chunks = []
    current_chunk = []

    for word in words:
        if len(' '.join(current_chunk + [word])) <= max_length:
            current_chunk.append(word)
        else:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks

def process_text(full_prompt):
    system_message = {
        "role": "system",
        "content": f"You are Document GPT. Your job is to take the uploaded material and do with it what the user prompts you to."
    }
    user_message = {
        "role": "user",
        "content": full_prompt
    }

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[system_message, user_message],
        max_tokens=1000,
        n=1,
        stop=None,
        temperature=0.5,
    )
    return response.choices[0].message['content'].strip()

@app.route('/process_transcript', methods=['POST'])
def process_transcript():
    try:
        transcript = request.json['transcript']
        prompt = request.json['gptPrompt'] 

        # Split the transcript into smaller chunks
        max_length = 3500  # Adjust this value based on the token limit
        transcript_chunks = split_text(transcript, max_length)

        processed_chunks = []
        for chunk in transcript_chunks:
            full_prompt = f"\n\nPrompt: {prompt}\n\nUploaded Material:\n\n{chunk}"

            organized_chunk = process_text(full_prompt)
            processed_chunks.append(organized_chunk)

        # Merge the processed chunks
        organized_text = ' '.join(processed_chunks)

        result = {"processed_text": organized_text}
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        print(e)
        return jsonify({"error": str(e)}), 500

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(file_path):
    text = ""
    with open(file_path, 'rb') as file:
        pdf = PdfReader(file)
        n_pages = len(pdf.pages)
        for page_number in range(n_pages):  # converts the PDF to an image
            page = pdf.pages[page_number]
            text += page.extract_text()
    return text


@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    text = extract_text_from_pdf(file_path)
    os.remove(file_path)

    return jsonify({"text": text})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)