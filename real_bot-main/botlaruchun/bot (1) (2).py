import logging
import random
import string
import asyncio
import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode, ChatAction
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand, BotCommandScopeDefault
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

# Video funksiyasini yoqish/o'chirish uchun global sozlama
VIDEOS_ENABLED = True  # Videolarni yoqish uchun True qiymati bering                                                                                                                                      
# Videoni yuborish - protect_content=True qo'shildi
# 
# Bot tokeni va adminlar ro'yxati
TOKEN = "8075883424:AAG_YIGTkefoBY60AHoCl5rNUUU3tF3cVx4"
CONTROLLER_ID = 8113300476  # Asosiy admin (controller) ID 8113300476 1586890780
ADMIN_IDS = [987654321]  # O'qituvchilar ID raqamlari
    
# Data fayllari
DATA_DIR = "data"
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
TEMP_LINKS_FILE = os.path.join(DATA_DIR, "temp_links.json")
BOT_CONFIG_FILE = os.path.join(DATA_DIR, "bot_config.json")

# Bot va Dispatcher
storage = MemoryStorage()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher(storage=storage)

# Ma'lumotlar uchun konteynerlar    
darsliklar = {}
foydalanuvchilar = {}
statistics = {}
temp_links = {}
bot_config = {
    "access_code": "123456",  # Default access code
    "verified_users": []  # List of user IDs who have verified with the access code
}

# Logger sozlash
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Function to generate a new random 6-digit code
def generate_new_code():
    while True:
        new_code = ''.join(random.choices(string.digits, k=6))
        if new_code not in darsliklar:  # Ensure the code doesn't already exist
            return new_code

# Function to generate a new random bot access code
def generate_new_bot_access_code():
    return ''.join(random.choices(string.digits, k=6))

# States for conversation
class LessonStates(StatesGroup):
    waiting_for_lesson_name = State()
    waiting_for_lesson_id = State()
    waiting_for_video = State()
    waiting_for_more_videos = State()  # New state for asking if more videos should be added
    waiting_for_video_title = State()  # New state for video title
    waiting_for_code = State()
    waiting_for_new_code = State()
    waiting_for_teacher_id = State()
    waiting_for_student_id = State()
    waiting_for_lesson_code = State()  # New state for lesson-specific code
    waiting_for_bot_access_code = State()  # New state for bot access code

# Data fayllarini saqlash va yuklash funksiyalari
def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def save_data():
    try:
        ensure_data_dir()
        
        # Darsliklarni saqlash
        with open(LESSONS_FILE, 'w', encoding='utf-8') as f:
            # video_id ni string sifatida saqlash
            lessons_data = {}
            for k, v in darsliklar.items():
                lessons_copy = v.copy()
                if "videos" in lessons_copy:
                    # Convert each video's file_id to string if needed
                    videos_copy = []
                    for video in lessons_copy["videos"]:
                        video_copy = video.copy()
                        if "file_id" in video_copy:
                            video_copy["file_id"] = str(video_copy["file_id"])
                        videos_copy.append(video_copy)
                    lessons_copy["videos"] = videos_copy
                lessons_data[k] = lessons_copy
            json.dump(lessons_data, f, ensure_ascii=False, indent=2)
        
        # Foydalanuvchilarni saqlash
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(foydalanuvchilar, f, ensure_ascii=False, indent=2)
        
        # Statistikani saqlash
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            # set ni list ga o'zgartirish
            stats_data = {}
            for k, v in statistics.items():
                stats_copy = {}
                for video_id, video_stats in v.items():
                    if "viewers" in video_stats and isinstance(video_stats["viewers"], set):
                        stats_copy[video_id] = {**video_stats, "viewers": list(video_stats["viewers"])}
                    else:
                        stats_copy[video_id] = video_stats
                stats_data[k] = stats_copy
            json.dump(stats_data, f, ensure_ascii=False, indent=2)
        
        # Vaqtinchalik havolalarni saqlash
        with open(TEMP_LINKS_FILE, 'w', encoding='utf-8') as f:
            # datetime ni string ga o'zgartirish
            links_data = {}
            for k, v in temp_links.items():
                if "expires_at" in v and isinstance(v["expires_at"], datetime):
                    links_data[k] = {**v, "expires_at": v["expires_at"].isoformat()}
                else:
                    links_data[k] = v
            json.dump(links_data, f, ensure_ascii=False, indent=2)
        
        # Bot konfiguratsiyasini saqlash
        with open(BOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(bot_config, f, ensure_ascii=False, indent=2)
        
        logger.info("Data saved successfully")
    except Exception as e:
        logger.error(f"Error saving data: {e}")

def load_data():
    global darsliklar, foydalanuvchilar, statistics, temp_links, bot_config
    try:
        ensure_data_dir()
        
        # Darsliklarni yuklash
        if os.path.exists(LESSONS_FILE):
            with open(LESSONS_FILE, 'r', encoding='utf-8') as f:
                darsliklar = json.load(f)
                
                # Convert old format to new format if needed
                for kod, darslik in darsliklar.items():
                    if "video" in darslik and "videos" not in darslik:
                        # Convert old single video format to new multiple videos format
                        darslik["videos"] = [{
                            "title": darslik.get("nomi", "Video"),
                            "file_id": darslik["video"]
                        }]
                        # Keep the old video field for backward compatibility
                        # but we'll use videos array going forward
        
        # Foydalanuvchilarni yuklash
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                foydalanuvchilar = json.load(f)
        
        # Statistikani yuklash
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                stats_data = json.load(f)
                # Convert old format to new format if needed
                for kod, stats in stats_data.items():
                    if isinstance(stats, dict) and "views" in stats:
                        # Old format - convert to new format
                        video_id = darsliklar.get(kod, {}).get("video", "unknown")
                        statistics[kod] = {
                            video_id: {
                                "views": stats.get("views", 0),
                                "viewers": set(stats.get("viewers", [])),
                                "last_viewed": stats.get("last_viewed")
                            }
                        }
                    else:
                        # New format - just convert lists to sets
                        statistics[kod] = {}
                        for video_id, video_stats in stats.items():
                            if "viewers" in video_stats and isinstance(video_stats["viewers"], list):
                                statistics[kod][video_id] = {
                                    **video_stats, 
                                    "viewers": set(video_stats["viewers"])
                                }
                            else:
                                statistics[kod][video_id] = video_stats
        
        # Vaqtinchalik havolalarni yuklash
        if os.path.exists(TEMP_LINKS_FILE):
            with open(TEMP_LINKS_FILE, 'r', encoding='utf-8') as f:
                links_data = json.load(f)
                # string ni datetime ga o'zgartirish
                for k, v in links_data.items():
                    if "expires_at" in v and isinstance(v["expires_at"], str):
                        try:
                            temp_links[k] = {**v, "expires_at": datetime.fromisoformat(v["expires_at"])}
                        except ValueError:
                            # Agar format noto'g'ri bo'lsa, hozirgi vaqtdan 24 soat keyingi vaqtni belgilash
                            temp_links[k] = {**v, "expires_at": datetime.now() + timedelta(hours=24)}
                    else:
                        temp_links[k] = v
        
        # Bot konfiguratsiyasini yuklash
        if os.path.exists(BOT_CONFIG_FILE):
            with open(BOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                bot_config = json.load(f)
        else:
            # If config file doesn't exist, create a new access code
            bot_config["access_code"] = generate_new_bot_access_code()
            save_data()
        
        logger.info("Data loaded successfully")
    except Exception as e:
        logger.error(f"Error loading data: {e}")

# Avtomatik saqlash funksiyasi
async def auto_save_data():
    while True:
        try:
            await asyncio.sleep(300)  # Har 5 daqiqada saqlash
            save_data()
            logger.info("Data automatically saved")
        except Exception as e:
            logger.error(f"Error in auto save: {e}")

# Muddati o'tgan narsalar
# Muddati o'tgan vaqtinchalik havolalarni tozalash
async def cleanup_expired_links():
    while True:
        try:
            await asyncio.sleep(3600)  # Har soatda bir marta tekshirish
            current_time = datetime.now()
            expired_links = []
            
            for link_id, link_data in temp_links.items():
                if "expires_at" in link_data and isinstance(link_data["expires_at"], datetime):
                    if current_time > link_data["expires_at"]:
                        expired_links.append(link_id)
            
            # The line below was commented out to prevent automatic deletion of videos
            # for link_id in expired_links:
            #     del temp_links[link_id]
            
            if expired_links:
                logger.info(f"Removed {len(expired_links)} expired links")
                save_data()
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")

# Foydalanuvchi turini aniqlash
def get_user_type(user_id):
    # CRITICAL FIX: Convert user_id to int for comparison
    user_id = int(user_id) if isinstance(user_id, str) else user_id
    
    if user_id == CONTROLLER_ID:
        return "controller"
    elif user_id in ADMIN_IDS:
        return "teacher"
    else:                                                                                                                                                                                    
        return "student"

# Check if user is verified with the bot access code
def is_user_verified(user_id):
    user_id = str(user_id) if not isinstance(user_id, str) else user_id
    return user_id in bot_config.get("verified_users", [])

# Inline tugmalar - Controller uchun
def get_controller_buttons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Dars qo'shish", callback_data="add_lesson")],
        [InlineKeyboardButton(text="👨‍🏫 O'qituvchilar", callback_data="manage_teachers")],
        [InlineKeyboardButton(text="👨‍🎓 O'quvchilar", callback_data="manage_students")],
        [InlineKeyboardButton(text="📂 Videolar", callback_data="view_videos")],
        [InlineKeyboardButton(text="🔢 Kodlar", callback_data="view_codes")],
        [InlineKeyboardButton(text="🔐 Kirish kodi", callback_data="view_access_code")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="view_stats")]
    ])

# Inline tugmalar - O'qituvchi uchun
def get_teacher_buttons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Dars qo'shish", callback_data="add_lesson")],
        [InlineKeyboardButton(text="📂 Videolar", callback_data="view_videos")],
        [InlineKeyboardButton(text="🔢 Kodlar", callback_data="view_codes")],
        [InlineKeyboardButton(text="🔐 Kirish kodi", callback_data="view_access_code")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="view_users")]
    ])

# Inline tugmalar - Talaba uchun (UPDATED)
def get_student_buttons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Darslar ro'yxati", callback_data="student_lessons_list")],
        [InlineKeyboardButton(text="👤 Shaxsiy kabinet", callback_data="personal_account")]
    ])

# Darslik boshqarish tugmalari
def get_lesson_management_buttons(lesson_code):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Video qo'shish", callback_data=f"add_video:{lesson_code}")],
        [InlineKeyboardButton(text="🗑️ Darsni o'chirish", callback_data=f"delete_lesson:{lesson_code}")],
        [InlineKeyboardButton(text="🔄 Kodni o'zgartirish", callback_data=f"change_code:{lesson_code}")],
        [InlineKeyboardButton(text="🎬 Videolarni ko'rish", callback_data=f"admin_view_videos:{lesson_code}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")]
    ])

# O'qituvchilar boshqarish tugmalari
def get_teacher_management_buttons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 O'qituvchilar ro'yxati", callback_data="list_teachers")],
        [InlineKeyboardButton(text="➕ O'qituvchi qo'shish", callback_data="add_teacher")],
        [InlineKeyboardButton(text="➖ O'qituvchi o'chirish", callback_data="remove_teacher")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")]
    ])

# O'quvchilar boshqarish tugmalari
def get_student_management_buttons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➖ O'quvchini o'chirish", callback_data="remove_student")],
        [InlineKeyboardButton(text="📋 O'quvchilar ro'yxati", callback_data="list_students")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")]
    ])

# Bot komandalarini sozlash
async def set_commands():
    # Set global commands for all users
    commands = [
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="help", description="Yordam olish"),
        BotCommand(command="myid", description="ID raqamingizni bilish")
    ]
    
    try:
        await bot.set_my_commands(commands)
        logger.info("Global commands set successfully")
    except Exception as e:
        logger.error(f"Error setting global commands: {e}")

# Add this function to set user-specific commands when they interact with the bot
async def set_user_commands(user_id):
    user_type = get_user_type(user_id)
    
    try:
        if user_type == "controller":
            controller_commands = [
                BotCommand(command="start", description="Botni ishga tushirish"),
                BotCommand(command="help", description="Yordam olish"),
                BotCommand(command="myid", description="ID raqamingizni bilish"),
                BotCommand(command="add", description="Darslik qo'shish"),
                BotCommand(command="codes", description="Kodlar ro'yxati"),
                BotCommand(command="stats", description="Statistika"),
                BotCommand(command="teachers", description="O'qituvchilarni boshqarish"),
                BotCommand(command="students", description="O'quvchilarni boshqarish")
            ]
            
            await bot.set_my_commands(
                controller_commands,
                scope=types.BotCommandScopeChat(chat_id=user_id)
            )
            logger.info(f"Controller commands set for user {user_id}")
            
        elif user_type == "teacher":
            admin_commands = [
                BotCommand(command="start", description="Botni ishga tushirish"),
                BotCommand(command="help", description="Yordam olish"),
                BotCommand(command="myid", description="ID raqamingizni bilish"),
                BotCommand(command="add", description="Darslik qo'shish"),
                BotCommand(command="codes", description="Kodlar ro'yxati"),
                BotCommand(command="stats", description="Statistika")
            ]
            
            await bot.set_my_commands(
                admin_commands,
                scope=types.BotCommandScopeChat(chat_id=user_id)
            )
            logger.info(f"Teacher commands set for user {user_id}")
    
    except Exception as e:
        logger.error(f"Error setting commands for user {user_id}: {e}")

# 🟢 /start komandasi - MODIFIED
@dp.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    
    # Log user ID for debugging
    logger.info(f"User {user_id} ({user_name}) started the bot")
    
    # Foydalanuvchini ro'yxatga qo'shish
    if str(user_id) not in foydalanuvchilar:
        foydalanuvchilar[str(user_id)] = {
            "name": user_name,
            "accessed_lessons": [],
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": get_user_type(user_id)
        }
    else:
        # Faollikni yangilash
        foydalanuvchilar[str(user_id)]["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Set user-specific commands
    await set_user_commands(user_id)
    
    user_type = get_user_type(user_id)
    logger.info(f"User type: {user_type}")
    
    if user_type == "controller":
        await message.answer("👋 Assalomu alaykum, Bosh admin!", reply_markup=get_controller_buttons())
    elif user_type == "teacher":
        await message.answer("👋 Assalomu alaykum, ustoz!", reply_markup=get_teacher_buttons())
    else:
        # Check if student is verified
        if is_user_verified(user_id):
            await message.answer("👋 Assalomu alaykum!\nDarslik olish uchun quyidagi tugmalardan foydalaning.", 
                                reply_markup=get_student_buttons())
        else:
            # Send bot information and ask for access code
            await message.answer(
                "👋 Assalomu alaykum! Botimizga xush kelibsiz!\n\n"
                "Bu bot orqali siz o'quv videolarini ko'rishingiz mumkin. "
                "Botdan to'liq foydalanish uchun maxsus kirish kodini kiritishingiz kerak.\n\n"
                "Iltimos, kirish kodini kiriting:"
            )
            await state.set_state(LessonStates.waiting_for_bot_access_code)
    
    # Ma'lumotlarni saqlash
    save_data()

# 🟢 NEW: Bot access code verification
@dp.message(LessonStates.waiting_for_bot_access_code)
async def verify_bot_access_code(message: Message, state: FSMContext):
    entered_code = message.text.strip()
    user_id = str(message.from_user.id)
    
    # Check if the entered code matches the bot access code
    if entered_code == bot_config["access_code"]:
        # Add user to verified users list
        if "verified_users" not in bot_config:
            bot_config["verified_users"] = []
        
        if user_id not in bot_config["verified_users"]:
            bot_config["verified_users"].append(user_id)
        
        # Generate a new access code for the next user
        bot_config["access_code"] = generate_new_bot_access_code()
        
        # Save the updated config
        save_data()
        
        # Notify admins about the new code
        for admin_id in [CONTROLLER_ID] + ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"🔄 Bot kirish kodi o'zgartirildi!\n"
                         f"🔑 Yangi kod: `{bot_config['access_code']}`\n"
                         f"👤 Foydalanuvchi: {message.from_user.full_name} (`{user_id}`)",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Error notifying admin {admin_id}: {e}")
        
        # Welcome the user
        await message.answer(
            "✅ Kirish kodi to'g'ri! Botdan to'liq foydalanishingiz mumkin.\n\n"
            "Darslik olish uchun quyidagi tugmalardan foydalaning.",
            reply_markup=get_student_buttons()
        )
    else:
        await message.answer(
            "❌ Kirish kodi noto'g'ri! Iltimos, qaytadan urinib ko'ring:"
        )
        # Keep the state to wait for another attempt
        return
    
    await state.clear()

# 🟢 NEW: Kirish kodini ko'rish
@dp.callback_query(lambda call: call.data == "view_access_code")
async def view_access_code(call: CallbackQuery):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    # Get the current access code
    current_code = bot_config.get("access_code", "Kod topilmadi")
    
    # Get the list of verified users
    verified_users = bot_config.get("verified_users", [])
    verified_count = len(verified_users)
    
    # Create a button to generate a new access code
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Yangi kod yaratish", callback_data="generate_new_access_code")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")]
    ])
    
    await call.message.answer(
        f"🔐 *Bot kirish kodi ma'lumotlari*\n\n"
        f"🔑 Joriy kirish kodi: `{current_code}`\n"
        f"✅ Tasdiqlangan foydalanuvchilar: {verified_count} ta\n\n"
        f"⚠️ Eslatma: Har bir foydalanuvchi kirish kodini kiritganda, "
        f"yangi kod avtomatik ravishda yaratiladi.",
        reply_markup=markup
    )
    
    await call.answer()

# 🟢 NEW: Yangi kirish kodi yaratish
@dp.callback_query(lambda call: call.data == "generate_new_access_code")
async def generate_new_access_code_handler(call: CallbackQuery):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    # Generate a new access code
    old_code = bot_config.get("access_code", "Noma'lum")
    bot_config["access_code"] = generate_new_bot_access_code()
    
    # Save the updated config
    save_data()
    
    # Create a button to go back
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")]
    ])
    
    await call.message.answer(
        f"✅ Yangi kirish kodi yaratildi!\n\n"
        f"🔑 Eski kod: `{old_code}`\n"
        f"🔑 Yangi kod: `{bot_config['access_code']}`\n\n"
        f"Bu kodni o'quvchilarga tarqating.",
        reply_markup=markup
    )
    
    await call.answer()

# 🟢 /help komandasi
@dp.message(Command("help"))
async def help_command(message: Message):
    user_type = get_user_type(message.from_user.id)
    
    if user_type == "controller":
        help_text = (
            "*🔍 Yordam - Bosh admin uchun*\n\n"
            "• /start - Botni ishga tushirish\n"
            "• /add - Yangi darslik qo'shish\n"
            "• /codes - Kodlar ro'yxati\n"
            "• /stats - Statistika ko'rish\n"
            "• /teachers - O'qituvchilarni boshqarish\n"
            "• /students - O'quvchilarni boshqarish\n"
            "• /myid - ID raqamingizni bilish\n"
        )
    elif user_type == "teacher":
        help_text = (
            "*🔍 Yordam - O'qituvchi uchun*\n\n"
            "• /start - Botni ishga tushirish\n"
            "• /add - Yangi darslik qo'shish\n"
            "• /codes - Kodlar ro'yxati\n"
            "• /stats - Statistika ko'rish\n"
            "• /myid - ID raqamingizni bilish\n"
        )
    else:
        help_text = (
            "*🔍 Yordam - O'quvchi uchun*\n\n"
            "• /start - Botni ishga tushirish\n"
            "• /myid - ID raqamingizni bilish\n\n"
            "Darsliklarni ko'rish uchun asosiy menyudagi tugmalardan foydalaning."
        )
    
    await message.answer(help_text)

# 🟢 /myid - Foydalanuvchining ID sini bilish
@dp.message(Command("myid"))
async def get_my_id(message: Message):
    await message.answer(f"🆔 Sizning Telegram ID: `{message.from_user.id}`")

# 🟢 /add - Darslik qo'shish
@dp.message(Command("add"))
async def add_lesson_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_type = get_user_type(user_id)
    
    if user_type in ["controller", "teacher"]:
        await message.answer("📌 Darslik nomini kiriting:")
        await state.set_state(LessonStates.waiting_for_lesson_name)
    else:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")

# 🟢 /codes - Kodlar ro'yxati
@dp.message(Command("codes"))
async def view_codes_command(message: Message):
    user_id = message.from_user.id
    user_type = get_user_type(user_id)
    
    if user_type in ["controller", "teacher"]:
        await view_codes_handler(message)
    else:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")

# 🟢 /stats - Statistika
@dp.message(Command("stats"))
async def view_stats_command(message: Message):
    user_id = message.from_user.id
    user_type = get_user_type(user_id)
    
    if user_type in ["controller", "teacher"]:
        await view_stats_handler(message)
    else:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")

# 🟢 /teachers - O'qituvchilarni boshqarish
@dp.message(Command("teachers"))
async def manage_teachers_command(message: Message):
    user_id = message.from_user.id
    
    if user_id == CONTROLLER_ID:
        await message.answer("👨‍🏫 O'qituvchilarni boshqarish:", reply_markup=get_teacher_management_buttons())
    else:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")

# 🟢 /students - O'quvchilarni boshqarish
@dp.message(Command("students"))
async def manage_students_command(message: Message):
    user_id = message.from_user.id
    
    if user_id == CONTROLLER_ID:
        await message.answer("👨‍🎓 O'quvchilarni boshqarish:", reply_markup=get_student_management_buttons())
    else:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")

# 🟢 Ustoz darslik qo'shishi
@dp.callback_query(lambda call: call.data == "add_lesson")
async def add_lesson(call: CallbackQuery, state: FSMContext):
    user_type = get_user_type(call.from_user.id)
    
    if user_type in ["controller", "teacher"]:
        await call.message.answer("📌 Darslik nomini kiriting:")
        await state.set_state(LessonStates.waiting_for_lesson_name)
    else:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
    
    await call.answer()

# 🟢 Ustoz darslik nomini yuborishi
@dp.message(LessonStates.waiting_for_lesson_name)
async def get_lesson_name(message: Message, state: FSMContext):
    dars_nomi = message.text
    
    await state.update_data(lesson_name=dars_nomi)
    await message.answer(f"✅ Darslik nomi saqlandi!\nEndi darslik uchun ID kiriting (6 ta raqam):")
    await state.set_state(LessonStates.waiting_for_lesson_id)

# 🟢 Ustoz darslik ID sini yuborishi
@dp.message(LessonStates.waiting_for_lesson_id)
async def get_lesson_id(message: Message, state: FSMContext):
    kod = message.text.strip()
    
    # Validate the ID format
    if not kod.isdigit() or len(kod) != 6:
        await message.answer("❌ ID 6 ta raqamdan iborat bo'lishi kerak! Qaytadan kiriting:")
        return
    
    # Check if ID already exists
    if kod in darsliklar:
        await message.answer("❌ Bu ID allaqachon mavjud! Boshqa ID kiriting:")
        return
    
    await state.update_data(lesson_code=kod)
    await message.answer(f"✅ Darslik ID saqlandi!\nEndi birinchi video uchun sarlavha kiriting:")
    await state.set_state(LessonStates.waiting_for_video_title)

# 🟢 Ustoz video sarlavhasini yuborishi
@dp.message(LessonStates.waiting_for_video_title)
async def get_video_title(message: Message, state: FSMContext):
    video_title = message.text.strip()
    
    await state.update_data(current_video_title=video_title)
    await message.answer(f"✅ Video sarlavhasi saqlandi: '{video_title}'\nEndi video faylini yuboring:")
    await state.set_state(LessonStates.waiting_for_video)

# 🟢 Ustoz video yuborishi
@dp.message(LessonStates.waiting_for_video)
async def get_video(message: Message, state: FSMContext):
    if not message.video:
        await message.answer("❌ Iltimos, video yuboring!")
        return
    
    data = await state.get_data()
    dars_nomi = data.get("lesson_name")
    kod = data.get("lesson_code")
    video_title = data.get("current_video_title")
    
    # Initialize videos list if this is the first video
    if kod not in darsliklar:
        darsliklar[kod] = {
            "nomi": dars_nomi,
            "videos": [],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "created_by": str(message.from_user.id)
        }
    
    # Add the video to the videos list
    video_data = {
        "title": video_title,
        "file_id": message.video.file_id,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    darsliklar[kod]["videos"].append(video_data)
    
    # For backward compatibility
    if len(darsliklar[kod]["videos"]) == 1:
        darsliklar[kod]["video"] = message.video.file_id
    
    # Initialize statistics for this video
    if kod not in statistics:
        statistics[kod] = {}
    
    statistics[kod][message.video.file_id] = {
        "views": 0,
        "viewers": set(),
        "last_viewed": None
    }
    
    # Ask if more videos should be added
    more_videos_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha", callback_data=f"add_more_videos:{kod}")],
        [InlineKeyboardButton(text="❌ Yo'q", callback_data=f"finish_adding_videos:{kod}")]
    ])
    
    await message.answer(
        f"✅ Video muvaffaqiyatli qo'shildi!\n"
        f"📌 Video sarlavhasi: *{video_title}*\n"
        f"🔑 Kod: `{kod}`\n\n"
        f"Yana video qo'shmoqchimisiz?",
        reply_markup=more_videos_markup
    )
    
    # Ma'lumotlarni saqlash
    save_data()
    await state.update_data(current_lesson_code=kod)

# 🟢 Yana video qo'shish
@dp.callback_query(lambda call: call.data.startswith("add_more_videos:"))
async def add_more_videos(call: CallbackQuery, state: FSMContext):
    kod = call.data.split(":")[1]
    
    await state.update_data(current_lesson_code=kod)
    await call.message.answer("📌 Yangi video uchun sarlavha kiriting:")
    await state.set_state(LessonStates.waiting_for_video_title)
    await call.answer()

# 🟢 Video qo'shishni yakunlash
@dp.callback_query(lambda call: call.data.startswith("finish_adding_videos:"))
async def finish_adding_videos(call: CallbackQuery, state: FSMContext):
    kod = call.data.split(":")[1]
    
    if kod in darsliklar:
        videos_count = len(darsliklar[kod].get("videos", []))
        
        await call.message.answer(
            f"✅ Darslik muvaffaqiyatli qo'shildi!\n"
            f"📌 Darslik nomi: *{darsliklar[kod]['nomi']}*\n"
            f"🔑 Kod: `{kod}`\n"
            f"🎬 Videolar soni: {videos_count}\n\n"
            f"O'quvchilarga kodni tarqating.",
            reply_markup=get_lesson_management_buttons(kod)
        )
    
    await state.clear()
    await call.answer()

# 🟢 Mavjud darslikka video qo'shish
@dp.callback_query(lambda call: call.data.startswith("add_video:"))
async def add_video_to_lesson(call: CallbackQuery, state: FSMContext):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    kod = call.data.split(":")[1]
    
    if kod in darsliklar:
        await state.update_data(current_lesson_code=kod)
        await call.message.answer("📌 Yangi video uchun sarlavha kiriting:")
        await state.set_state(LessonStates.waiting_for_video_title)
    else:
        await call.message.answer("❌ Darslik topilmadi!")
    
    await call.answer()

# 🟢 Darsni o'chirish
@dp.callback_query(lambda call: call.data.startswith("delete_lesson:"))
async def delete_lesson(call: CallbackQuery):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    kod = call.data.split(":")[1]
    if kod in darsliklar:
        del darsliklar[kod]
        if kod in statistics:
            del statistics[kod]
        await call.message.answer(f"✅ Darslik muvaffaqiyatli o'chirildi!")
        
        if user_type == "controller":
            await call.message.answer("Bosh menyu:", reply_markup=get_controller_buttons())
        else:
            await call.message.answer("Bosh menyu:", reply_markup=get_teacher_buttons())
        
        # Ma'lumotlarni saqlash
        save_data()
    else:
        await call.message.answer("❌ Darslik topilmadi!")
    
    await call.answer()

# 🟢 Kodni o'zgartirish
@dp.callback_query(lambda call: call.data.startswith("change_code:"))
async def change_code_request(call: CallbackQuery, state: FSMContext):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    old_kod = call.data.split(":")[1]
    if old_kod in darsliklar:
        await state.update_data(old_code=old_kod)
        await call.message.answer("🔄 Yangi kodni kiriting (6 ta raqam):")
        await state.set_state(LessonStates.waiting_for_new_code)
    else:
        await call.message.answer("❌ Darslik topilmadi!")
    
    await call.answer()

# 🟢 Yangi kodni saqlash
@dp.message(LessonStates.waiting_for_new_code)
async def save_new_code(message: Message, state: FSMContext):
    new_code = message.text.strip()
    user_type = get_user_type(message.from_user.id)
    
    if not new_code.isdigit() or len(new_code) != 6:
        await message.answer("❌ Kod 6 ta raqamdan iborat bo'lishi kerak!")
        return
    
    if new_code in darsliklar:
        await message.answer("❌ Bu kod allaqachon mavjud! Boshqa kod kiriting:")
        return
    
    data = await state.get_data()
    old_code = data.get("old_code")
    
    if old_code in darsliklar:
        darsliklar[new_code] = darsliklar[old_code]
        statistics[new_code] = statistics.get(old_code, {})
        
        del darsliklar[old_code]
        if old_code in statistics:
            del statistics[old_code]
        
        await message.answer(
            f"✅ Kod muvaffaqiyatli o'zgartirildi!\n"
            f"🔑 Yangi kod: `{new_code}`"
        )
        
        if user_type == "controller":
            await message.answer("Bosh menyu:", reply_markup=get_controller_buttons())
        else:
            await message.answer("Bosh menyu:", reply_markup=get_teacher_buttons())
        
        # Ma'lumotlarni saqlash
        save_data()
    else:
        await message.answer("❌ Darslik topilmadi!")
    
    await state.clear()

# 🟢 O'qituvchilarni boshqarish
@dp.callback_query(lambda call: call.data == "manage_teachers")
async def manage_teachers(call: CallbackQuery):
    if call.from_user.id != CONTROLLER_ID:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    await call.message.answer("👨‍🏫 O'qituvchilarni boshqarish:", reply_markup=get_teacher_management_buttons())
    await call.answer()

# 🟢 O'qituvchi qo'shish
@dp.callback_query(lambda call: call.data == "add_teacher")
async def add_teacher_request(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != CONTROLLER_ID:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    await call.message.answer("👨‍🏫 Yangi o'qituvchining Telegram ID raqamini kiriting:")
    await state.set_state(LessonStates.waiting_for_teacher_id)
    await call.answer()

# 🟢 O'qituvchi ID sini saqlash
@dp.message(LessonStates.waiting_for_teacher_id)
async def save_teacher_id(message: Message, state: FSMContext):
    if message.from_user.id != CONTROLLER_ID:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await state.clear()
        return
    
    try:
        teacher_id = int(message.text.strip())
        
        if teacher_id == CONTROLLER_ID:
            await message.answer("❌ Bu ID raqami Bosh admin (controller) ga tegishli!")
            return
        
        if teacher_id in ADMIN_IDS:
            await message.answer("❌ Bu o'qituvchi allaqachon mavjud!")
            return
        
        # O'qituvchini qo'shish
        ADMIN_IDS.append(teacher_id)
        
        # Foydalanuvchilar ro'yxatida bo'lsa, turini yangilash
        if str(teacher_id) in foydalanuvchilar:
            foydalanuvchilar[str(teacher_id)]["type"] = "teacher"
        
        await message.answer(f"✅ O'qituvchi muvaffaqiyatli qo'shildi!\nID: `{teacher_id}`")
        await message.answer("👨‍🏫 O'qituvchilarni boshqarish:", reply_markup=get_teacher_management_buttons())
        
        # Ma'lumotlarni saqlash
        save_data()
    except ValueError:
        await message.answer("❌ Noto'g'ri format! ID raqami faqat sonlardan iborat bo'lishi kerak.")
    
    await state.clear()

# 🟢 O'qituvchini o'chirish
@dp.callback_query(lambda call: call.data == "remove_teacher")
async def remove_teacher_request(call: CallbackQuery):
    if call.from_user.id != CONTROLLER_ID:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    if not ADMIN_IDS:
        await call.message.answer("❌ O'qituvchilar ro'yxati bo'sh!")
        await call.answer()
        return
    
    teacher_buttons = []
    
    for teacher_id in ADMIN_IDS:
        teacher_name = "Noma'lum"
        if str(teacher_id) in foydalanuvchilar:
            teacher_name = foydalanuvchilar[str(teacher_id)].get("name", "Noma'lum")
        
        teacher_buttons.append([InlineKeyboardButton(
            text=f"❌ {teacher_name} ({teacher_id})", 
            callback_data=f"remove_teacher:{teacher_id}"
        )])
    
    teacher_buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_teachers")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=teacher_buttons)
    await call.message.answer("🗑️ O'chirish uchun o'qituvchini tanlang:", reply_markup=markup)
    await call.answer()

# 🟢 O'qituvchini o'chirish (tasdiqlash)
@dp.callback_query(lambda call: call.data.startswith("remove_teacher:"))
async def remove_teacher_confirm(call: CallbackQuery):
    if call.from_user.id != CONTROLLER_ID:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    teacher_id = int(call.data.split(":")[1])
    
    if teacher_id in ADMIN_IDS:
        ADMIN_IDS.remove(teacher_id)
        
        # Foydalanuvchilar ro'yxatida bo'lsa, turini yangilash
        if str(teacher_id) in foydalanuvchilar:
            foydalanuvchilar[str(teacher_id)]["type"] = "student"
        
        await call.message.answer(f"✅ O'qituvchi muvaffaqiyatli o'chirildi!\nID: `{teacher_id}`")
        await call.message.answer("👨‍🏫 O'qituvchilarni boshqarish:", reply_markup=get_teacher_management_buttons())
        
        # Ma'lumotlarni saqlash
        save_data()
    else:
        await call.message.answer("❌ O'qituvchi topilmadi!")
    
    await call.answer()

# 🟢 O'qituvchilar ro'yxati
@dp.callback_query(lambda call: call.data == "list_teachers")
async def list_teachers(call: CallbackQuery):
    if call.from_user.id != CONTROLLER_ID:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    if not ADMIN_IDS:
        await call.message.answer("📂 O'qituvchilar ro'yxati bo'sh!")
        await call.answer()
        return
    
    response = "👨‍🏫 *O'qituvchilar ro'yxati:*\n\n"
    
    for teacher_id in ADMIN_IDS:
        teacher_name = "Noma'lum"
        if str(teacher_id) in foydalanuvchilar:
            teacher_name = foydalanuvchilar[str(teacher_id)].get("name", "Noma'lum")
        
        response += f"👤 {teacher_name} - `{teacher_id}`\n"
    
    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_teachers")]
    ])
    
    await call.message.answer(response, reply_markup=back_button)
    await call.answer()

# 🟢 O'quvchilarni boshqarish
@dp.callback_query(lambda call: call.data == "manage_students")
async def manage_students(call: CallbackQuery):
    if call.from_user.id != CONTROLLER_ID:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    await call.message.answer("👨‍🎓 O'quvchilarni boshqarish:", reply_markup=get_student_management_buttons())
    await call.answer()

# 🟢 O'quvchini o'chirish
@dp.callback_query(lambda call: call.data == "remove_student")
async def remove_student_request(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != CONTROLLER_ID:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    await call.message.answer("👨‍🎓 O'chirish uchun o'quvchining Telegram ID raqamini kiriting:")
    await state.set_state(LessonStates.waiting_for_student_id)
    await call.answer()

# 🟢 O'quvchi ID sini o'chirish
@dp.message(LessonStates.waiting_for_student_id)
async def remove_student_by_id(message: Message, state: FSMContext):
    if message.from_user.id != CONTROLLER_ID:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await state.clear()
        return
    
    try:
        student_id = message.text.strip()
        
        if student_id == str(CONTROLLER_ID) or int(student_id) in ADMIN_IDS:
            await message.answer("❌ Bu ID raqami admin yoki o'qituvchiga tegishli!")
            return
        
        if student_id in foydalanuvchilar:
            del foydalanuvchilar[student_id]
            await message.answer(f"✅ O'quvchi muvaffaqiyatli o'chirildi!\nID: `{student_id}`")
            
            # Ma'lumotlarni saqlash
            save_data()
        else:
            await message.answer("❌ Bunday ID raqamli o'quvchi topilmadi!")
        
        await message.answer("👨‍🎓 O'quvchilarni boshqarish:", reply_markup=get_student_management_buttons())
    except ValueError:
        await message.answer("❌ Noto'g'ri format! ID raqami faqat sonlardan iborat bo'lishi kerak.")
    
    await state.clear()

# 🟢 O'quvchilar ro'yxati
@dp.callback_query(lambda call: call.data == "list_students")
async def list_students(call: CallbackQuery):
    if call.from_user.id != CONTROLLER_ID:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    students = {uid: info for uid, info in foydalanuvchilar.items() 
               if uid != str(CONTROLLER_ID) and int(uid) not in ADMIN_IDS}
    
    if not students:
        await call.message.answer("📂 O'quvchilar ro'yxati bo'sh!")
        await call.answer()
        return
    
    response = "👨‍🎓 *O'quvchilar ro'yxati:*\n\n"
    
    for student_id, student_info in students.items():
        lessons_count = len(student_info.get("accessed_lessons", []))
        response += f"👤 {student_info['name']} - `{student_id}` - Darsliklar: {lessons_count}\n"
    
    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_students")]
    ])
    
    await call.message.answer(response, reply_markup=back_button)
    await call.answer()

# 🟢 MODIFIED: Removed "enter_code" callback and related functions
# Students now directly access lessons without entering codes

# 🟢 MODIFIED: Darslar ro'yxati - Now directly shows all available lessons
@dp.callback_query(lambda call: call.data == "student_lessons_list")
async def student_lessons_list(call: CallbackQuery):
    # Check if user is verified
    if not is_user_verified(call.from_user.id):
        await call.message.answer(
            "⛔ Siz hali botdan to'liq foydalanish uchun ruxsat olmadingiz.\n"
            "Iltimos, /start buyrug'ini yuborib, kirish kodini kiriting."
        )
        await call.answer()
        return
        
    # Get all available lessons
    if not darsliklar:
        await call.message.answer("📂 Hali hech qanday darslik mavjud emas.")
        await call.answer()
        return
    
    response = "📚 *Mavjud darsliklar ro'yxati:*\n\n"
    
    lesson_buttons = []
    for kod, info in darsliklar.items():
        response += f"🔹 *{info['nomi']}*\n"
        # Changed to directly open the lesson instead of requesting a code
        lesson_buttons.append([InlineKeyboardButton(
            text=f"📚 {info['nomi']}", 
            callback_data=f"open_lesson:{kod}"
        )])
    
    lesson_buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_student")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=lesson_buttons)
    await call.message.answer(response, reply_markup=markup)
    await call.answer()

# 🟢 Darsni ochish - MODIFIED for direct access without code
@dp.callback_query(lambda call: call.data.startswith("open_lesson:"))
async def open_lesson(call: CallbackQuery):
    # Check if user is verified
    if not is_user_verified(call.from_user.id):
        await call.message.answer(
            "⛔ Siz hali botdan to'liq foydalanish uchun ruxsat olmadingiz.\n"
            "Iltimos, /start buyrug'ini yuborib, kirish kodini kiriting."
        )
        await call.answer()
        return
        
    kod = call.data.split(":")[1]
    user_id = str(call.from_user.id)
    
    if kod in darsliklar and "videos" in darsliklar[kod] and darsliklar[kod]["videos"]:
        # Update user data - add this lesson to accessed lessons
        if user_id in foydalanuvchilar:
            if "accessed_lessons" not in foydalanuvchilar[user_id]:
                foydalanuvchilar[user_id]["accessed_lessons"] = []
            
            if kod not in foydalanuvchilar[user_id]["accessed_lessons"]:
                foydalanuvchilar[user_id]["accessed_lessons"].append(kod)
            
            foydalanuvchilar[user_id]["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create buttons for each video
        video_buttons = []
        for i, video in enumerate(darsliklar[kod]["videos"]):
            # Create a temporary link for each video
            temp_link_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            expiry_time = datetime.now() + timedelta(hours=24)  # 24 soatlik muddatga
            
            temp_links[temp_link_id] = {
                "video_id": video["file_id"],
                "video_title": video["title"],
                "lesson_name": darsliklar[kod]["nomi"],
                "lesson_code": kod,
                "expires_at": expiry_time,
                "user_id": user_id
            }
            
            # Add button for this video
            video_buttons.append([InlineKeyboardButton(
                text=f"🎬 {video['title']}", 
                callback_data=f"view_video:{temp_link_id}"
            )])
        
        video_buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_student")])
        videos_markup = InlineKeyboardMarkup(inline_keyboard=video_buttons)
        
        await call.message.answer(
            f"📚 Darslik: *{darsliklar[kod]['nomi']}*\n"
            f"🎬 Videolar soni: {len(darsliklar[kod]['videos'])}\n\n"
            f"Ko'rmoqchi bo'lgan videoni tanlang:",
            reply_markup=videos_markup
        )
        
        # Ma'lumotlarni saqlash
        save_data()
    else:
        await call.message.answer("❌ Darslik topilmadi!")
    
    await call.answer()

# 🟢 MODIFIED: Video viewing function - No code verification needed
@dp.callback_query(lambda call: call.data.startswith("view_video:"))
async def view_video(call: CallbackQuery):
    # Check if user is verified
    if not is_user_verified(call.from_user.id):
        await call.message.answer(
            "⛔ Siz hali botdan to'liq foydalanish uchun ruxsat olmadingiz.\n"
            "Iltimos, /start buyrug'ini yuborib, kirish kodini kiriting."
        )
        await call.answer()
        return
        
    # Video funksiyasi o'chirilgan bo'lsa
    if not VIDEOS_ENABLED:
        await call.message.answer("⛔ Video funksiyasi hozirda o'chirilgan.")
        await call.answer()
        return
        
    link_id = call.data.split(":")[1]
    user_id = str(call.from_user.id)
    
    if link_id in temp_links:
        link_data = temp_links[link_id]
        
        # Havola muddati o'tganmi tekshirish
        if isinstance(link_data["expires_at"], datetime) and datetime.now() > link_data["expires_at"]:
            await call.message.answer("❌ Havola muddati tugagan! Iltimos, qaytadan darsliklar ro'yxatidan tanlang.")
            del temp_links[link_id]
            await call.answer()
            return
        
        # Foydalanuvchi tekshirish
        if link_data["user_id"] != user_id:
            await call.message.answer("⛔ Bu havola sizga tegishli emas!")
            await call.answer()
            return
        
        try:
            # Typing action to show the bot is processing
            await bot.send_chat_action(chat_id=call.message.chat.id, action=ChatAction.UPLOAD_VIDEO)
            
            # Update statistics for this video view
            lesson_code = link_data["lesson_code"]
            video_id = link_data["video_id"]
            
            if lesson_code not in statistics:
                statistics[lesson_code] = {}
            
            if video_id not in statistics[lesson_code]:
                statistics[lesson_code][video_id] = {
                    "views": 0,
                    "viewers": set(),
                    "last_viewed": None
                }
            
            statistics[lesson_code][video_id]["views"] += 1
            statistics[lesson_code][video_id]["viewers"].add(user_id)
            statistics[lesson_code][video_id]["last_viewed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Videoni yuborish
            video_title = link_data.get("video_title", "")
            caption = f"📚 *{link_data['lesson_name']}*"
            if video_title:
                caption += f" - *{video_title}*"
            caption += f"\n\n⚠️ *MUHIM OGOHLANTIRISH*: Bu video faqat shaxsiy foydalanish uchun. Videoni tarqatish, nusxalash yoki uchinchi shaxslarga berish qat'iyan taqiqlanadi."
            
            await call.message.answer_video(
                link_data["video_id"], 
                caption=caption,
                protect_content=True  # Videoni forward qilishni cheklash
            )
            
            # Ma'lumotlarni saqlash
            save_data()
        except TelegramAPIError as e:
            logger.error(f"Error sending video: {e}")
            await call.message.answer("❌ Video yuborishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
    else:
        await call.message.answer("❌ Havola topilmadi yoki muddati tugagan!")
    
    await call.answer()

# 🟢 Shaxsiy kabinet
@dp.callback_query(lambda call: call.data == "personal_account")
async def personal_account(call: CallbackQuery):
    # Check if user is verified
    if not is_user_verified(call.from_user.id):
        await call.message.answer(
            "⛔ Siz hali botdan to'liq foydalanish uchun ruxsat olmadingiz.\n"
            "Iltimos, /start buyrug'ini yuborib, kirish kodini kiriting."
        )
        await call.answer()
        return
        
    user_id = str(call.from_user.id)
    
    if user_id not in foydalanuvchilar:
        await call.message.answer("❌ Ma'lumotlar topilmadi!")
        await call.answer()
        return
    
    user_data = foydalanuvchilar[user_id]
    lessons_count = len(user_data.get("accessed_lessons", []))
    
    response = (
        f"👤 *Shaxsiy kabinet*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Ism: {user_data['name']}\n"
        f"📚 Ko'rilgan darsliklar: {lessons_count} ta\n"
        f"🕒 Oxirgi faollik: {user_data.get('last_activity', 'Ma\'lumot yo\'q')}"
    )
    
    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_student")]
    ])
    
    await call.message.answer(response, reply_markup=back_button)
    await call.answer()

# 🟢 Videolar ro'yxati
@dp.callback_query(lambda call: call.data == "view_videos")
async def view_videos(call: CallbackQuery):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    if not darsliklar:
        await call.message.answer("📂 Hali hech qanday video yo'q.")
        await call.answer()
        return
    
    response = "📂 *Videolar ro'yxati:* \n\n"
    
    video_buttons = []
    for kod, info in darsliklar.items():
        if "videos" in info and info["videos"]:
            videos_count = len(info["videos"])
            response += f"🎬 *{info['nomi']}* - `{kod}` - {videos_count} ta video\n"
            video_buttons.append([InlineKeyboardButton(
                text=f"🎬 {info['nomi']} ({videos_count} video)", 
                callback_data=f"admin_view_videos:{kod}"
            )])
    
    video_buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=video_buttons)
    await call.message.answer(response, reply_markup=markup)
    await call.answer()

# 🟢 Kodlar ro'yxati
@dp.callback_query(lambda call: call.data == "view_codes")
async def view_codes(call: CallbackQuery):
    await view_codes_handler(call.message)
    await call.answer()

async def view_codes_handler(message: Message):
    user_id = message.from_user.id if isinstance(message, Message) else message.chat.id
    user_type = get_user_type(user_id)
    
    # Log for debugging
    logger.info(f"view_codes_handler called by user {user_id}, type: {user_type}")
    
    if user_type not in ["controller", "teacher"]:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        return
    
    if not darsliklar:
        await message.answer("📂 Hali hech qanday kod yo'q.")
        return
    
    response = "📜 *Mavjud kodlar:* \n\n"
    
    code_buttons = []
    for kod, info in darsliklar.items():
        videos_count = len(info.get("videos", []))
        response += f"🔹 *{info['nomi']}* - `{kod}` - {videos_count} ta video\n"
        code_buttons.append([InlineKeyboardButton(
            text=f"🔍 {info['nomi']} ({kod})", 
            callback_data=f"manage_lesson:{kod}"
        )])
    
    code_buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=code_buttons)
    await message.answer(response, reply_markup=markup)

# 🟢 Darslikni boshqarish
@dp.callback_query(lambda call: call.data.startswith("manage_lesson:"))
async def manage_lesson(call: CallbackQuery):
    user_id = call.from_user.id
    user_type = get_user_type(user_id)
    
    # Log for debugging
    logger.info(f"manage_lesson called by user {user_id}, type: {user_type}")
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    kod = call.data.split(":")[1]
    
    if kod in darsliklar:
        info = darsliklar[kod]
        videos_count = len(info.get("videos", []))
        
        # Calculate total views and unique viewers across all videos
        total_views = 0
        all_viewers = set()
        last_viewed = "Ma'lumot yo'q"
        
        if kod in statistics:
            for video_id, stats in statistics[kod].items():
                total_views += stats.get("views", 0)
                all_viewers.update(stats.get("viewers", set()))
                
                # Get the most recent view time
                if stats.get("last_viewed"):
                    if last_viewed == "Ma'lumot yo'q":
                        last_viewed = stats["last_viewed"]
                    else:
                        # Compare dates to find the most recent
                        current = datetime.strptime(last_viewed, "%Y-%m-%d %H:%M:%S")
                        new = datetime.strptime(stats["last_viewed"], "%Y-%m-%d %H:%M:%S")
                        if new > current:
                            last_viewed = stats["last_viewed"]
        
        response = (
            f"📚 *Darslik ma'lumotlari*\n\n"
            f"📌 Nomi: *{info['nomi']}*\n"
            f"🔑 Kod: `{kod}`\n"
            f"🎬 Videolar soni: {videos_count}\n"
            f"📊 Ko'rishlar soni: {total_views}\n"
            f"👥 Ko'rgan foydalanuvchilar: {len(all_viewers)}\n"
            f"🕒 Oxirgi ko'rilgan vaqt: {last_viewed}\n"
            f"📅 Yaratilgan vaqt: {info.get('created_at', 'Ma\'lumot yo\'q')}"
        )
        
        await call.message.answer(response, reply_markup=get_lesson_management_buttons(kod))
    else:
        await call.message.answer("❌ Darslik topilmadi!")
    
    await call.answer()

# 🟢 Statistika ko'rish - MODIFIED for multiple videos
@dp.callback_query(lambda call: call.data == "view_stats")
async def view_stats(call: CallbackQuery):
    await view_stats_handler(call.message)
    await call.answer()

async def view_stats_handler(message: Message):
    user_id = message.from_user.id if isinstance(message, Message) else message.chat.id
    user_type = get_user_type(user_id)
    
    # Log for debugging
    logger.info(f"view_stats_handler called by user {user_id}, type: {user_type}")
    
    if user_type not in ["controller", "teacher"]:
        await message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        return
    
    if not statistics:
        await message.answer("📊 Hali statistika mavjud emas.")
        return
    
    response = "📊 *Darsliklar statistikasi:* \n\n"
    
    for kod, stats in statistics.items(): 
        if kod in darsliklar:
            # Calculate total views and unique viewers across all videos
            total_views = 0
            all_viewers = set()
            
            for video_id, video_stats in stats.items():
                total_views += video_stats.get("views", 0)
                all_viewers.update(video_stats.get("viewers", set()))
            
            response += (
                f"📚 *{darsliklar[kod]['nomi']}* (`{kod}`)\n"
                f"👁️ Ko'rishlar: {total_views}\n"
                f"👥 Foydalanuvchilar: {len(all_viewers)}\n"
                f"🎬 Videolar soni: {len(darsliklar[kod].get('videos', []))}\n\n"
            )
    
    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")]
    ])
    
    await message.answer(response, reply_markup=back_button)

# 🟢 Foydalanuvchilar ro'yxati (o'qituvchi uchun)
@dp.callback_query(lambda call: call.data == "view_users")
async def view_users(call: CallbackQuery):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    if not foydalanuvchilar:
        await call.message.answer("📂 Foydalanuvchilar ro'yxati bo'sh!")
        await call.answer()
        return
    
    response = "👥 *Foydalanuvchilar ro'yxati:*\n\n"
    
    for user_id, user_info in foydalanuvchilar.items():
        lessons_count = len(user_info.get("accessed_lessons", []))
        user_type_str = "👨‍🎓 O'quvchi"
        if int(user_id) == CONTROLLER_ID:
            user_type_str = "👑 Bosh admin"
        elif int(user_id) in ADMIN_IDS:
            user_type_str = "👨‍🏫 O'qituvchi"
        
        response += f"{user_type_str}: {user_info['name']} - `{user_id}` - Darsliklar: {lessons_count}\n"
    
    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="back_to_menu")]
    ])
    
    await call.message.answer(response, reply_markup=back_button)
    await call.answer()

# 🟢 Orqaga qaytish tugmalari
@dp.callback_query(lambda call: call.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    user_type = get_user_type(call.from_user.id)
    
    if user_type == "controller":
        await call.message.answer("Bosh menyu:", reply_markup=get_controller_buttons())
    elif user_type == "teacher":
        await call.message.answer("Bosh menyu:", reply_markup=get_teacher_buttons())
    else:
        await call.message.answer("Bosh menyu:", reply_markup=get_student_buttons())
    
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_student")
async def back_to_student(call: CallbackQuery):
    await call.message.answer("Bosh menyu:", reply_markup=get_student_buttons())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_teachers")
async def back_to_teachers(call: CallbackQuery):
    await call.message.answer("👨‍🏫 O'qituvchilarni boshqarish:", reply_markup=get_teacher_management_buttons())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_students")
async def back_to_students(call: CallbackQuery):
    await call.message.answer("👨‍🎓 O'quvchilarni boshqarish:", reply_markup=get_student_management_buttons())
    await call.answer()

# 🟢 Admin uchun videolarni ko'rish
@dp.callback_query(lambda call: call.data.startswith("admin_view_videos:"))
async def admin_view_videos(call: CallbackQuery):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    kod = call.data.split(":")[1]
    
    if kod in darsliklar and "videos" in darsliklar[kod] and darsliklar[kod]["videos"]:
        if not VIDEOS_ENABLED:
            await call.message.answer("⛔ Video funksiyasi hozirda o'chirilgan.")
            await call.answer()
            return
        
        # Create buttons for each video
        video_buttons = []
        for i, video in enumerate(darsliklar[kod]["videos"]):
            video_buttons.append([InlineKeyboardButton(
                text=f"🎬 {video['title']}", 
                callback_data=f"admin_view_single_video:{kod}:{i}"
            )])
        
        video_buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"manage_lesson:{kod}")])
        videos_markup = InlineKeyboardMarkup(inline_keyboard=video_buttons)
        
        await call.message.answer(
            f"📚 Darslik: *{darsliklar[kod]['nomi']}*\n"
            f"🎬 Videolar soni: {len(darsliklar[kod]['videos'])}\n\n"
            f"Ko'rmoqchi bo'lgan videoni tanlang:",
            reply_markup=videos_markup
        )
    else:
        await call.message.answer("❌ Darslik topilmadi yoki videolar mavjud emas!")
    
    await call.answer()

# 🟢 Admin uchun bitta videoni ko'rish
@dp.callback_query(lambda call: call.data.startswith("admin_view_single_video:"))
async def admin_view_single_video(call: CallbackQuery):
    user_type = get_user_type(call.from_user.id)
    
    if user_type not in ["controller", "teacher"]:
        await call.message.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q!")
        await call.answer()
        return
    
    parts = call.data.split(":")
    kod = parts[1]
    video_index = int(parts[2])
    
    if kod in darsliklar and "videos" in darsliklar[kod] and len(darsliklar[kod]["videos"]) > video_index:
        if not VIDEOS_ENABLED:
            await call.message.answer("⛔ Video funksiyasi hozirda o'chirilgan.")
            await call.answer()
            return
            
        try:
            video = darsliklar[kod]["videos"][video_index]
            
            # Typing action to show the bot is processing
            await bot.send_chat_action(chat_id=call.message.chat.id, action=ChatAction.UPLOAD_VIDEO)
            
            # Videoni yuborish
            await call.message.answer_video(
                video["file_id"], 
                caption=f"📚 *{darsliklar[kod]['nomi']}* - *{video['title']}*\n\n⚠️ *Admin ko'rinishi*"
            )
        except TelegramAPIError as e:
            logger.error(f"Error sending video: {e}")
            await call.message.answer("❌ Video yuborishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
    else:
        await call.message.answer("❌ Video topilmadi!")
    
    await call.answer()

# 🟢 Faqat ruxsat etilgan xabarlarni qabul qilish
@dp.message()
async def filter_messages(message: Message):
    # Faqat state bilan ishlayotgan yoki komanda bo'lgan xabarlarni qabul qilish
    # Boshqa barcha xabarlarni rad etish
    await message.answer("⚠️ Iltimos, faqat tugmalardan foydalaning yoki mavjud komandalarni kiriting.")

# 🟢 Botni ishga tushirish
async def main():
    try:
        # Ma'lumotlarni yuklash
        load_data()
        
        # Komandalarni sozlash
        await set_commands()
        
        # Avtomatik saqlash jarayonini boshlash
        auto_save_task = asyncio.create_task(auto_save_data())
        
        # Muddati o'tgan havolalarni tozalash
        cleanup_task = asyncio.create_task(cleanup_expired_links())
        
        # Botni ishga tushirish
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        # Save data before exiting
        save_data()
        logger.info("Bot stopped, data saved")

if __name__ == "__main__":
    asyncio.run(main())