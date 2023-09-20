from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import openai
import traceback
import os
import re
from PyPDF2 import PdfReader
from pptx import Presentation
from werkzeug.utils import secure_filename
from pptx.util import Pt
import time

app = Flask(__name__)
CORS(app)

openai.api_key = "your api key here"

def split_text_by_separator(text, separator="$!$"):
    return text.split(separator)

from pptx import Presentation
from pptx.util import Pt
import re

def generate_pptx(processed_chunks, original_chunks):
    prs = Presentation()
    for i, processed_chunk in enumerate(processed_chunks):
        print(f"Processed chunk {i}:\n{processed_chunk}\n")  # Debug print

        # Updated regular expressions
        questions_with_answers = re.findall(r"Question([\s\S]+?)Answer Choices:([\s\S]+?)Correct answer:", processed_chunk)
        explanations = re.findall(r"Explanation:([\s\S]+?)(Question|$)", processed_chunk)
        correct_answers = re.findall(r"Correct answer: ([^\n]+)", processed_chunk)

        # Combine the correct answers with explanations
        explanations_with_correct_answers = []
        for idx, (exp, _) in enumerate(explanations):
            correct_answer = f"Correct Answer: {correct_answers[idx]}\n" if idx < len(correct_answers) else ""
            updated_exp = correct_answer + "Explanation: " + exp.strip()
            explanations_with_correct_answers.append(updated_exp)

        print(f"Questions with Answers:\n{questions_with_answers}\n")  # Debug print
        print(f"Explanations with Correct Answers:\n{explanations_with_correct_answers}\n")  # Debug print

        for idx, ((q, a), e) in enumerate(zip(questions_with_answers, explanations_with_correct_answers)):
            # Create slides
            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)
            title = slide.shapes.title
            content = slide.placeholders[1]
            title.text = f"Slide {i+1}-{idx+1} - Question"
            content.text = f"{q.strip()}\nAnswer Choices:{a.strip()}"
            for paragraph in content.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(20)

            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)
            title = slide.shapes.title
            content = slide.placeholders[1]
            title.text = f"Slide {i+1}-{idx+1} - Answer & Explanation"
            content.text = f"{e.strip()}"
            for paragraph in content.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(20)

        # Add the original slide content
        slide_layout = prs.slide_layouts[1]
        slide = prs.slides.add_slide(slide_layout)
        title = slide.shapes.title
        content = slide.placeholders[1]
        title.text = f"Slide {i+1} - Original Content"
        content.text = original_chunks[i].strip()
        for paragraph in content.text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(20)

    prs.save("generated_presentation.pptx")



MAX_RETRIES = 5  # Max number of retries for API calls
DELAY_BETWEEN_RETRIES = 5  # Time delay in seconds between retries

def process_text(full_prompt):
    retries = 0
    while retries < MAX_RETRIES:
        try:
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
                max_tokens=2000,
                n=1,
                stop=None,
                temperature=0.5,
            )
            return response.choices[0].message['content'].strip()

        except Exception as e:
            retries += 1
            print(f"An error occurred: {e}. Retrying {retries}/{MAX_RETRIES}...")
            time.sleep(DELAY_BETWEEN_RETRIES)

    # If the code reaches here, all retries have failed.
    raise Exception(f"Failed to process text after {MAX_RETRIES} retries.")

@app.route('/process_transcript', methods=['POST'])
def process_transcript():
    try:
        transcript = request.json['transcript']
        prompt = request.json['gptPrompt']
        transcript_chunks = split_text_by_separator(transcript)

        processed_chunks = []
        for chunk in transcript_chunks:
            full_prompt = f"Prompt: {prompt}\nUploaded Material: {chunk}"
            organized_chunk = process_text(full_prompt)
            processed_chunks.append(organized_chunk)

        generate_pptx(processed_chunks, transcript_chunks)
        
        return send_file('generated_presentation.pptx', as_attachment=True, download_name='generated_presentation.pptx')
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'pptx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Modified function to include separator "$!$"
def extract_text_from_pdf(file_path):
    text = ""
    with open(file_path, 'rb') as file:
        pdf = PdfReader(file)
        n_pages = len(pdf.pages)
        for page_number in range(n_pages):
            page = pdf.pages[page_number]
            text += page.extract_text()
            text += "$!$"  # Add the separator after each page
    return text

# Modified function to include separator "$!$"
def extract_text_from_pptx(file_path):
    text = ""
    prs = Presentation(file_path)

    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        text += run.text + ' '
        text += "$!$"  # Add the separator after each slide
    return text

@app.route('/upload_file', methods=['POST'])
def upload_file():
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
    file_extension = filename.rsplit('.', 1)[1].lower()

    if file_extension == 'pdf':
        text = extract_text_from_pdf(file_path)
    elif file_extension == 'pptx':
        text = extract_text_from_pptx(file_path)
    else:
        os.remove(file_path)
        return jsonify({"error": "Unsupported file type"}), 400

    os.remove(file_path)
    return jsonify({"text": text})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)
