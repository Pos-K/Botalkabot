import os
import random
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")


# === БАЗА ДАННЫХ ===
def init_db():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            score INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            tag TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            option1 TEXT,
            option2 TEXT,
            option3 TEXT,
            option4 TEXT,
            answer TEXT
        )
    """)
    conn.commit()
    conn.close()

def update_score(user_id, name, points):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        cursor.execute("UPDATE users SET score = score + ? WHERE user_id = ?", (points, user_id))
    else:
        cursor.execute("INSERT INTO users (user_id, name, score) VALUES (?, ?, ?)", (user_id, name, points))
    conn.commit()
    conn.close()

def get_top_players(limit=5):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, score FROM users ORDER BY score DESC LIMIT ?", (limit,))
    top = cursor.fetchall()
    conn.close()
    return top

def add_subscriber(user_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO subscribers (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def add_question(q_text, options, correct):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO questions (question, option1, option2, option3, option4, answer)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (q_text, *options, correct))
    conn.commit()
    conn.close()

def get_random_question():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "question": row[1],
            "options": [row[2], row[3], row[4], row[5]],
            "answer": row[6]
        }
    return None

async def send_daily_meme():
    print("Запускается ежедневная рассылка...")
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM subscribers")
    users = cursor.fetchall()
    conn.close()

    meme_folder = "memes"
    meme_list = os.listdir(meme_folder)

    if not meme_list:
        print("Нет мемов для рассылки.")
        return

    meme_file = random.choice(meme_list)

    for (user_id,) in users:
        try:
            await app.bot.send_photo(
                chat_id=user_id,
                photo=open(os.path.join(meme_folder, meme_file), "rb"),
                caption="🗓 Вот твой мем дня!"
            )
        except Exception as e:
            print(f"Ошибка при отправке мема пользователю {user_id}: {e}")

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    add_subscriber(user_id)
    await update.message.reply_text("Bonjour! Je suis un bot: créer des mèmes et passer des quiz 🤖")


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/menu — menü öffnen\n/start — Neustart\n/top — bestenliste")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_players = get_top_players()

    if not top_players:
        await update.message.reply_text("Пока никто не набрал очков 😢")
        return

    text = "🏆 Топ игроков:\n\n"
    for i, (name, score) in enumerate(top_players, start=1):
        text += f"{i}. {name} — {score} очков\n"

    await update.message.reply_text(text)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "привет" in text:
        await update.message.reply_text("Bonjour! Content de te voir. 👋")
    else:
        await update.message.reply_text(update.message.text)


# === МЕНЮ ===
keyboard = [
    [InlineKeyboardButton("🎲 Случайный Мем", callback_data="random_meme"),
     InlineKeyboardButton("🖼️ Создать Мем", callback_data="create_meme")],
    [InlineKeyboardButton("❓ Викторина", callback_data="quiz"),
     InlineKeyboardButton("🏆 Топ Игроков", callback_data="top")]
]
menu = InlineKeyboardMarkup(keyboard)


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wähle eine Aktion aus:", reply_markup=menu)


# === ОБРАБОТКА КНОПОК ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "random_meme":
        await query.edit_message_text("🎲 Мем будет здесь позже")
    elif data == "create_meme":
        await query.edit_message_text("🖼️ Пришли фото для мема")
        context.user_data["wait_for_photo"] = True
    elif data == "quiz":
        await send_quiz(update, context)
    elif data == "top":
        top_players = get_top_players()

        if not top_players:
            await query.edit_message_text("Пока никто не набрал очков 😢")
            return

        text = "🏆 Топ игроков:\n\n"
        for i, (name, score) in enumerate(top_players, start=1):
            text += f"{i}. {name} — {score} очков\n"

        await query.edit_message_text(text)
    elif data.startswith("answer_"):
        await check_answer(update, context, data)


# === ОБРАБОТКА ФОТО ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("wait_for_photo"):
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    os.makedirs("temp", exist_ok=True)
    await file.download_to_drive("temp/meme.jpg")

    context.user_data["wait_for_photo"] = False
    context.user_data["wait_for_text"] = True

    await update.message.reply_text("✏️ А теперь пришли текст для мема!")


# === ОБРАБОТКА ТЕКСТА ДЛЯ МЕМА ===
async def handle_meme_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("wait_for_text"):
        return

    text = update.message.text
    img = Image.open("temp/meme.jpg")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", size=40)
    except:
        font = ImageFont.load_default()

    width, height = img.size
    x, y = 20, height - 60

    for dx in range(-2, 3):
        for dy in range(-2, 3):
            draw.text((x + dx, y + dy), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill="white")

    img.save("temp/final_meme.jpg")
    await update.message.reply_photo(photo=open("temp/final_meme.jpg", "rb"))

    context.user_data["wait_for_text"] = False


async def send_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    q = get_random_question()
    if not q:
        await query.edit_message_text("😢 Вопросов пока нет в базе.")
        return
    context.user_data["correct_answer"] = q["answer"]
    buttons = [InlineKeyboardButton(opt, callback_data=f"answer_{opt}") for opt in q["options"]]
    markup = InlineKeyboardMarkup.from_column(buttons)
    await query.edit_message_text(q["question"], reply_markup=markup)

async def check_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    selected = data.replace("answer_", "")
    correct = context.user_data.get("correct_answer")
    if selected == correct:
        user_id = query.from_user.id
        name = query.from_user.first_name
        update_score(user_id, name, 10)
        await query.edit_message_text(f"✅ Richtig! Das ist {correct}. +10 очков 🧠")
    else:
        await query.edit_message_text(f"❌ Falsch! Richtige Antwort ist: {correct}.")

# === ЗАПУСК БОТА ===
init_db()
app = ApplicationBuilder().token(BOT_TOKEN).build()
scheduler = AsyncIOScheduler()
scheduler.add_job(send_daily_meme, CronTrigger(hour=18, minute=0))
scheduler.start()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help))
app.add_handler(CommandHandler("menu", menu_handler))
app.add_handler(CommandHandler("top", top))
app.add_handler(CallbackQueryHandler(handle_buttons))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_meme_text))
app.add_handler(MessageHandler(filters.TEXT, echo))

app.run_polling()