import os
from io import BytesIO
import fitz  # PyMuPDF
from PIL import Image
import telebot
from telebot import types
from telebot.types import InputFile

# OCR
import pytesseract

# AI Upscale
import torch
from realesrgan import RealESRGAN

API_TOKEN = 'YOUR_BOT_TOKEN_HERE'  # <-- REPLACE with your Telegram Bot Token!
ADMIN_ID = 1973627200  # Optional

bot = telebot.TeleBot(API_TOKEN)
user_sessions = {}

def main_menu(pdf_received=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('✅ Done')
    if pdf_received:
        markup.row('📂 Extract Images')
    markup.row('📝 Extract Text from Images')
    markup.row('🔼 Enhance Images (Simple)')
    markup.row('✨ Enhance Images (AI)')
    return markup

@bot.message_handler(commands=['start'])
def start_bot(message):
    user_sessions[message.chat.id] = {'images': [], 'pdf_file_id': None}
    bot.send_message(message.chat.id,
        "👋 Send images (photo or image document) to create PDF.\n"
        "Or send a PDF to extract images.\n\n"
        "Features:\n"
        "• OCR (extract text from images)\n"
        "• Simple and AI image upscaling\n",
        reply_markup=main_menu()
    )

@bot.message_handler(content_types=['photo', 'document'])
def handle_files(message):
    cid = message.chat.id
    session = user_sessions.setdefault(cid, {'images': [], 'pdf_file_id': None})

    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
        session['images'].append(file_id)
        bot.send_message(cid, f"✅ Photo added ({len(session['images'])})", reply_markup=main_menu())

    elif message.document:
        mime = message.document.mime_type
        if mime in ['image/jpeg', 'image/png']:
            session['images'].append(message.document.file_id)
            bot.send_message(cid, f"✅ Image added ({len(session['images'])})", reply_markup=main_menu())
        elif mime == 'application/pdf':
            session['pdf_file_id'] = message.document.file_id
            bot.send_message(cid, "📄 PDF received.", reply_markup=main_menu(pdf_received=True))
        else:
            bot.send_message(cid, "❗ Please send only JPEG/PNG images or a PDF.")

@bot.message_handler(func=lambda m: m.text == '✅ Done')
def generate_pdf(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session['images']:
        bot.send_message(cid, "❗ No images to convert.", reply_markup=main_menu())
        return

    images = []
    for file_id in session['images']:
        file_info = bot.get_file(file_id)
        file_data = bot.download_file(file_info.file_path)
        try:
            image = Image.open(BytesIO(file_data)).convert('RGB')
            images.append(image)
        except:
            bot.send_message(cid, "⚠️ Skipped an image (unreadable format).")

    if not images:
        bot.send_message(cid, "❗ No valid images to create PDF.")
        return

    output = BytesIO()
    images[0].save(output, format='PDF', save_all=True, append_images=images[1:])
    output.seek(0)

    try:
        input_file = InputFile(output, "converted.pdf")
        bot.send_document(
            cid,
            input_file,
            caption="📄 Your PDF is ready!"
        )
    except Exception as e:
        bot.send_message(cid, f"❌ Error sending PDF: {e}")

    session['images'] = []

@bot.message_handler(func=lambda m: m.text == '📂 Extract Images')
def extract_images_from_pdf(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session.get('pdf_file_id'):
        bot.send_message(cid, "❗ No PDF uploaded.", reply_markup=main_menu())
        return

    try:
        file_info = bot.get_file(session['pdf_file_id'])
        file_data = bot.download_file(file_info.file_path)

        doc = fitz.open(stream=file_data, filetype='pdf')
        count = 0

        for i in range(len(doc)):
            for img in doc.get_page_images(i):
                xref = img[0]
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                img_io = BytesIO(img_bytes)
                img_io.seek(0)
                bot.send_photo(cid, img_io)
                count += 1

        msg = f"✅ Done! Extracted {count} image(s)." if count else "⚠️ No images found."
        bot.send_message(cid, msg)
        session['pdf_file_id'] = None
    except Exception as e:
        bot.send_message(cid, f"❌ Error: {e}")

@bot.message_handler(func=lambda m: m.text == '📝 Extract Text from Images')
def extract_text_from_images(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session['images']:
        bot.send_message(cid, "❗ No images to extract text from.", reply_markup=main_menu())
        return

    texts = []
    for file_id in session['images']:
        file_info = bot.get_file(file_id)
        file_data = bot.download_file(file_info.file_path)
        try:
            image = Image.open(BytesIO(file_data))
            text = pytesseract.image_to_string(image)
            texts.append(text.strip())
        except Exception as e:
            bot.send_message(cid, f"⚠️ Error processing image: {e}")

    if texts:
        all_text = "\n\n---\n\n".join([txt if txt else "(no text found)" for txt in texts])
        bot.send_message(cid, f"📝 Extracted Text:\n{all_text[:4000]}")
    else:
        bot.send_message(cid, "❗ No text found in images.")

@bot.message_handler(func=lambda m: m.text == '🔼 Enhance Images (Simple)')
def enhance_images_simple(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session['images']:
        bot.send_message(cid, "❗ No images to enhance.", reply_markup=main_menu())
        return

    for file_id in session['images']:
        file_info = bot.get_file(file_id)
        file_data = bot.download_file(file_info.file_path)
        try:
            image = Image.open(BytesIO(file_data))
            new_size = (image.width * 2, image.height * 2)
            enhanced = image.resize(new_size, Image.LANCZOS)
            output = BytesIO()
            enhanced.save(output, format='JPEG')
            output.seek(0)
            bot.send_photo(cid, output, caption="🔼 Simple 2x Upscaled Image")
        except Exception as e:
            bot.send_message(cid, f"⚠️ Error enhancing image: {e}")
    bot.send_message(cid, "✅ All images enhanced! You can now convert them to PDF or extract text.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == '✨ Enhance Images (AI)')
def enhance_images_ai(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session['images']:
        bot.send_message(cid, "❗ No images to enhance.", reply_markup=main_menu())
        return

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    try:
        # Will auto-download weights on first use
        model = RealESRGAN(device, scale=4)
        model.load_weights('RealESRGAN_x4.pth')
    except Exception as e:
        bot.send_message(cid, f"❌ Model load error: {e}")
        return

    for file_id in session['images']:
        file_info = bot.get_file(file_id)
        file_data = bot.download_file(file_info.file_path)
        try:
            image = Image.open(BytesIO(file_data)).convert("RGB")
            sr_image = model.predict(image)
            output = BytesIO()
            sr_image.save(output, format='JPEG')
            output.seek(0)
            bot.send_photo(cid, output, caption="✨ AI Enhanced (Real-ESRGAN)")
        except Exception as e:
            bot.send_message(cid, f"⚠️ Error enhancing image: {e}")
    bot.send_message(cid, "✅ All images enhanced with AI!", reply_markup=main_menu())

bot.infinity_polling()
