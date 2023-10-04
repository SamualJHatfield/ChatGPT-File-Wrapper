from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import openai
import traceback
import os
import re
from PyPDF2 import PdfReader
from pptx import Presentation
from werkzeug.utils import secure_filename
from pptx.util import Inches, Pt
import time
import fitz  # Import PyMuPDF
import io
from PIL import Image

global file_path

app = Flask(__name__)
CORS(app)

openai.api_key = "your api key here"


def split_text_by_separator(text, separator="$!$"):
    return text.split(separator)


def convert_pdf_to_images(pdf_path):
    doc = fitz.open(pdf_path)
    images = []
    for i in range(len(doc)):
        page = doc.load_page(i)
        pixmap = page.get_pixmap()
        temp_file_name = f"temp_image_{i}.png"
        pixmap.save(temp_file_name)  # Save the pixmap to a temporary file
        with open(temp_file_name, "rb") as image_file:
            image_bytes = io.BytesIO(image_file.read())  # Read the image file into a BytesIO buffer
        image = Image.open(image_bytes)  # Now open the image using PIL
        images.append(image)
        os.remove(temp_file_name)  # Delete the temporary file
    return images

def generate_pptx(processed_chunks, original_chunks, file_path, output_filename):
    prs = Presentation()
    prs.slide_width = Inches(8.5)  # Set width
    prs.slide_height = Inches(11)  # Set height
    images = convert_pdf_to_images(file_path)  # convert all pdf pages to images
    print(file_path)

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

        # This loop should be inside the loop over processed_chunks
        for idx, ((q, a), e) in enumerate(zip(questions_with_answers, explanations_with_correct_answers)):
            # Create slides
            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)
            title = slide.shapes.title
            content = slide.placeholders[1]
            title.text = f"Slide {i+1}-{idx+1} - Question"
            content.text = f"{q.strip()}\nAnswer Choices:{a.strip()}"
            content.top = Inches(1.5)
            content.width = Inches(7.5)
            content.height = Inches(8)
            for paragraph in content.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(24)

            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)
            title = slide.shapes.title
            content = slide.placeholders[1]
            title.text = f"Slide {i+1}-{idx+1} - Answer"
            content.text = f"{e.strip()}"
            content.top = Inches(1.5)
            content.width = Inches(7.5)
            content.height = Inches(8)
            for paragraph in content.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(20)

        # Image handling code should also be inside the loop over processed_chunks
        image = images[i]  # assuming each processed_chunk corresponds to a page
        image_path = f'temp_page_{i}.png'
        image.save(image_path)

        slide_layout = prs.slide_layouts[5]  # use the blank slide layout
        slide = prs.slides.add_slide(slide_layout)

        left = Inches(0)
        top = Inches(0)
        height = Inches(11)  # setting height to maintain aspect ratio
        pic = slide.shapes.add_picture(image_path, left, top, height=height)

    prs.save(output_filename)
    
    # Get the directory of the saved PowerPoint file
    output_dir = os.path.dirname(os.path.abspath(output_filename))
    
    # Iterate through all files in the output directory
    for filename in os.listdir(output_dir):
        # Check if the file is a temporary image file (by checking its name pattern)
        if filename.startswith('temp_page_') and filename.endswith('.png'):
            # Get the full path of the file
            file_path = os.path.join(output_dir, filename)
            
            # Delete the file
            os.remove(file_path)




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

        # New line to split transcript by separator "$!$"
        transcript_chunks = split_text_by_separator(transcript)

        processed_chunks = []
        for chunk in transcript_chunks:
            full_prompt = f"\n\nPrompt: {prompt}\n\nUploaded Material:\n\n{chunk}"

            organized_chunk = process_text(full_prompt)
            processed_chunks.append(organized_chunk)

        organized_text = ' '.join(processed_chunks)
        result = {"processed_text": organized_text}
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
@app.route('/process_practice_questions', methods=['POST'])
def process_practice_questions():
    try:
        transcript = request.json['transcript']
        transcript_chunks = split_text_by_separator(transcript)

        processed_chunks = []
        for chunk in transcript_chunks:
            full_prompt = f'''Prompt: " Please create a case-based practice question for a medical school exam. The question should be based on the slide details provided (don't reference the slide or images). The answer choices should delve into the mentioned mutations, imaging, hitologic findings, specific treatments, pharmacology, or distinct pathogenic/clinical features from the slide.  

Your response should use the following format:

Question: [Question]
Answer Choices: [A-E]
Correct answer: [correct answer]
Explanation: [Explanation]

Below please find an example of the style of question and explanation which should be asked:

Example:

Question:
A 35-year-old woman presents with joint pain for 3 months. This started first in her right 1-3 MCPs, then developed consecutively in the left 2nd & 3rd MCPs and bilateral 4th and 5th MTPs. Pain is worse in the mornings, improves with use, and is associated with 1.5 hours of morning stiffness. Her exam shows swelling in the affected joints. What is the clinical pattern of her joint complaints?

Answer Choices:
A Acute non-inflammatory symmetric polyarthritis of small and large joints 
B Chronic inflammatory symmetric polyarthritis of small joints 
C Acute inflammatory asymmetric oligoarthritis of small joints 
D Chronic non-inflammatory symmetric polyarthritis of small joints 
E Chronic non-inflammatory symmetric oligoarthritis of small joints 

Correct answer: B Chronic inflammatory symmetric polyarthritis of small joints

Explanation: 
This patient has a chronic presentation (> 6 weeks) of a symmetric (affects MCPs and MTPs on both sides of the body) polyarthritis (> 5 joints) affecting the small joints of the hands and feet (MCPs and MTPs). It is inflammatory since morning stiffness is > 1 hour. Therefore, option B is correct. She may have rheumatoid arthritis or one of its mimickers. Options D and E are incorrect due to the duration of morning stiffness. Duration of 3 months makes options A and C incorrect - acute is usually hours to days of symptoms at presentation. Options C and E are also incorrect due to the number of joints involved (oligoarthritis = 2-4 joints).

Explanations should state why the correct response is correct, as well as the specific reason why the incorrect answers are incorrect. Avoid stating "These options are incorrect as they do not match the description" or other things of that nature"\nUploaded Material: {chunk}'''

            organized_chunk = process_text(full_prompt)
            processed_chunks.append(organized_chunk)

        original_filename = os.path.basename(file_path).rsplit('.', 1)[0]  # Extract name without extension
        output_filename = f"{original_filename} practice questions.pptx"
        generate_pptx(processed_chunks, transcript_chunks, file_path, output_filename)
        return "File Saved"

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
    pages_text = []
    with open(file_path, 'rb') as file:
        pdf = PdfReader(file)
        n_pages = len(pdf.pages)
        for page_number in range(n_pages):
            page = pdf.pages[page_number]
            pages_text.append(page.extract_text())
    text = "$!$".join(pages_text)  # separator will not be added at the end
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
    global file_path  # Indicate that we're using the global file_path variable

    # Clear everything in the uploads folder
    folder = app.config['UPLOAD_FOLDER']
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400
    filename = secure_filename(file.filename)
    file.save(os.path.join(folder, filename))

    file_path = os.path.join(folder, filename)  # Assign to global file_path
    file_extension = filename.rsplit('.', 1)[1].lower()

    if file_extension == 'pdf':
        text = extract_text_from_pdf(file_path)
    elif file_extension == 'pptx':
        text = extract_text_from_pptx(file_path)
    else:
        os.remove(file_path)
        return jsonify({"error": "Unsupported file type"}), 400

    return jsonify({"text": text})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)
