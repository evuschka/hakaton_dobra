#pip install aiogram
#pip install gigachat
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from gigachat import GigaChat
import requests
import json
# ==========================================
# НАСТРОЙКИ
# ==========================================

BOT_TOKEN = "8416315888:AAE4X1FcIHiQw1tf2ZXMQG1rt7a1q7JyJ4A"

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Структура: {user_id: {"name": "...", "description": "...", "tone": "..."}}
users_db = {}

# ==========================================
# МАШИНА СОСТОЯНИЙ (FSM)
# ==========================================

class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_desc = State()
    waiting_for_tone = State()

class GenText(StatesGroup):
    choosing_mode = State()
    waiting_for_free_input = State()
    # Структурированный ввод
    struct_event = State()
    struct_date = State()
    struct_details = State()

class GenImage(StatesGroup):
    waiting_for_prompt = State()

class Editor(StatesGroup):
    waiting_for_text = State()

class ContentPlan(StatesGroup):
    waiting_for_params = State()

# ==========================================
# КЛАВИАТУРЫ
# ==========================================

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📝 Генерация текста"), KeyboardButton(text="🖼 Генерация картинки")],
        [KeyboardButton(text="✏️ Редактор текста"), KeyboardButton(text="📅 Контент-план")],
        [KeyboardButton(text="⚙️ Моя НКО")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_skip_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Пропустить шаг", callback_data="skip_step")]])

def get_tone_keyboard():
    kb = [
        [KeyboardButton(text="Официально-деловой")],
        [KeyboardButton(text="Дружелюбный и теплый")],
        [KeyboardButton(text="Эмоциональный и призывающий")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_text_modes_keyboard():
    kb = [
        [KeyboardButton(text="🎯 Свободная идея")],
        [KeyboardButton(text="📋 По шаблону (структура)")],
        [KeyboardButton(text="🔙 В меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ==========================================
# ЭМУЛЯЦИЯ НЕЙРОСЕТИ (MOCK AI SERVICE)
# ==========================================
# В реальности здесь будут запросы к API GigaChat / YandexGPT / Kandinsky
async def ai_generate_text_real(prompt: str, context: dict) -> str:
    # Используйте ваш токен, полученный от GigaChat
    credentials = "ВАШ_GIGACHAT_ТОКЕН" 
    nko_name = context.get('name', 'НКО')
    nko_tone = context.get('tone', 'Дружелюбный')
    
    # Составление промпта для GigaChat
    full_prompt = (f"Ты контент-менеджер для НКО '{nko_name}'. "
                   f"Напиши пост в стиле '{nko_tone}', основываясь на идее: {prompt}. "
                   f"Добавь релевантный хештег.")
    
    try:
        # GigaChat обычно не поддерживает асинхронный контекст, используйте ThreadPoolExecutor
        # Или, если вы используете sync GigaChat, оберните его в asyncio.to_thread
        
        def sync_call():
            with GigaChat(credentials=credentials, verify_ssl_certs=False) as giga:
                response = giga.chat(full_prompt)
                return response.choices[0].message.content
        
        result = await asyncio.to_thread(sync_call)
        return result
        
    except Exception as e:
        return f"❌ Ошибка GigaChat: {e}. Попробуйте позже."
    
    FUSIONBRAIN_API_KEY = "ВАШ_КЛЮЧ" 
    
    async def ai_generate_image_real(prompt: str) -> str:
        
        # 1. Запрос на создание задачи
        response = requests.post(
            "https://api.fusionbrain.ai/api/v1/text2image/run",
            headers={"X-API-Key": FUSIONBRAIN_API_KEY},
            data={"prompt": prompt, "modelId": 1, "width": 1024, "height": 1024}
        )
        uuid = response.json().get('uuid')
    
        # 2. Ожидание готовности (цикл опроса)
        max_attempts = 10
        for _ in range(max_attempts):
            await asyncio.sleep(2) # Ждем 2 секунды
            status_resp = requests.get(
                f"https://api.fusionbrain.ai/api/v1/text2image/status/{uuid}",
                headers={"X-API-Key": FUSIONBRAIN_API_KEY}
            )
            data = status_resp.json()
            
            if data.get('status') == 'done':
                # 3. Возвращаем Base64 строку картинки (для отправки через message.answer_photo)
                # В этом случае функция вернет Base64, а хендлер должен его декодировать и отправить.
                return data.get('images')[0] 
            
        return "❌ Ошибка: Изображение не сгенерировано за отведенное время."
async def ai_edit_text(text):
    await asyncio.sleep(1.5)
    return f"✏️ [AI Редактор]:\nТекст проверен.\n\nИсправленный вариант:\n{text} (отредактировано)\n\nСовет: Добавьте призыв к действию в конце!"

async def ai_create_plan(days):
    await asyncio.sleep(2)
    return (f"📅 [AI План] Контент-план на {days}:\n\n"
            "🔹 Пн: Анонс мероприятия\n"
            "🔹 Ср: История подопечного\n"
            "🔹 Пт: Отчет о сборах\n"
            "🔹 Вс: Полезная инфографика")

# ==========================================
# ХЭНДЛЕРЫ: СТАРТ И РЕГИСТРАЦИЯ
# ==========================================

@router.message(CommandStart())
async def command_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    welcome_text = (
        "👋 Привет! Я — КонтентПомощник для НКО.\n"
        "Я помогу писать посты, создавать картинки и планы.\n\n"
        "Давай настроим профиль твоей организации, чтобы контент был качественнее."
    )
    
    # Кнопки выбора
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Настроить профиль НКО", callback_data="setup_nko")],
        [InlineKeyboardButton(text="🚀 Перейти к работе (без настроек)", callback_data="skip_setup")]
    ])
    
    await message.answer(welcome_text, reply_markup=kb)

@router.callback_query(F.data == "skip_setup")
async def skip_setup(callback: types.CallbackQuery):
    await callback.message.answer("Хорошо, будем работать в общем режиме!", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "setup_nko")
async def start_setup(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("1. Введите название вашей НКО:")
    await state.set_state(Registration.waiting_for_name)
    await callback.answer()

@router.message(Registration.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("2. Кратко опишите, чем занимается НКО (1-2 предложения):")
    await state.set_state(Registration.waiting_for_desc)

@router.message(Registration.waiting_for_desc)
async def process_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("3. Выберите стиль общения в постах:", reply_markup=get_tone_keyboard())
    await state.set_state(Registration.waiting_for_tone)

@router.message(Registration.waiting_for_tone)
async def process_tone(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    user_data['tone'] = message.text
    
    # Сохраняем в "БД"
    users_db[message.from_user.id] = user_data
    
    await message.answer("✅ Профиль настроен! Теперь я буду учитывать это при генерации.", reply_markup=get_main_keyboard())
    await state.clear()

# ==========================================
# ХЭНДЛЕРЫ: ГЕНЕРАЦИЯ ТЕКСТА
# ==========================================

@router.message(F.text == "📝 Генерация текста")
async def start_gen_text(message: types.Message, state: FSMContext):
    await message.answer("Выберите режим генерации:", reply_markup=get_text_modes_keyboard())
    await state.set_state(GenText.choosing_mode)

@router.message(GenText.choosing_mode, F.text == "🎯 Свободная идея")
async def text_mode_free(message: types.Message, state: FSMContext):
    await message.answer("Напишите тему поста или черновую идею:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(GenText.waiting_for_free_input)

@router.message(GenText.waiting_for_free_input)
async def generate_free_text(message: types.Message, state: FSMContext):
    user_profile = users_db.get(message.from_user.id)
    msg = await message.answer("⏳ Генерирую пост...")
    
    # Вызов AI
    result = await ai_generate_text(message.text, user_profile)
    
    await msg.edit_text(result)
    await message.answer("Что делаем дальше?", reply_markup=get_main_keyboard())
    await state.clear()

@router.message(GenText.choosing_mode, F.text == "📋 По шаблону (структура)")
async def text_mode_struct(message: types.Message, state: FSMContext):
    await message.answer("Шаг 1/3. О каком событии пишем? (Например: Субботник в парке)")
    await state.set_state(GenText.struct_event)

@router.message(GenText.struct_event)
async def struct_step_2(message: types.Message, state: FSMContext):
    await state.update_data(event=message.text)
    await message.answer("Шаг 2/3. Когда и где это будет? (Дата, время, место)")
    await state.set_state(GenText.struct_date)

@router.message(GenText.struct_date)
async def struct_step_3(message: types.Message, state: FSMContext):
    await state.update_data(datetime=message.text)
    await message.answer("Шаг 3/3. Кто приглашен и есть ли особые условия?")
    await state.set_state(GenText.struct_details)

@router.message(GenText.struct_details)
async def struct_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prompt = f"Событие: {data['event']}. Время/Место: {data['datetime']}. Детали: {message.text}"
    
    user_profile = users_db.get(message.from_user.id)
    msg = await message.answer("⏳ Собираю пост по структуре...")
    
    result = await ai_generate_text(prompt, user_profile)
    
    await msg.edit_text(result)
    await message.answer("Готово!", reply_markup=get_main_keyboard())
    await state.clear()

@router.message(GenText.choosing_mode, F.text == "🔙 В меню")
async def back_to_menu(message: types.Message, state: FSMContext):
    await message.answer("Главное меню", reply_markup=get_main_keyboard())
    await state.clear()

# ==========================================
# ХЭНДЛЕРЫ: ГЕНЕРАЦИЯ КАРТИНКИ
# ==========================================

@router.message(F.text == "🖼 Генерация картинки")
async def start_gen_image(message: types.Message, state: FSMContext):
    await message.answer("Опишите, что должно быть на изображении:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(GenImage.waiting_for_prompt)

@router.message(GenImage.waiting_for_prompt)
async def process_image_prompt(message: types.Message, state: FSMContext):
    msg = await message.answer("🎨 Рисую... Это может занять пару секунд.")
    
    image_url = await ai_generate_image(message.text)
    
    # В реальном боте здесь отправка фото через URL или файл
    # await message.answer_photo(image_url, caption="Ваше изображение готово!") 
    
    # Для демо отправляем ссылкой:
    await msg.edit_text(f"Картинка готова! (В реальном боте здесь будет фото)\n🔗 Ссылка: {image_url}")
    await message.answer("Меню:", reply_markup=get_main_keyboard())
    await state.clear()

# ==========================================
# ХЭНДЛЕРЫ: РЕДАКТОР
# ==========================================

@router.message(F.text == "✏️ Редактор текста")
async def start_editor(message: types.Message, state: FSMContext):
    await message.answer("Пришлите текст, который нужно проверить и улучшить:")
    await state.set_state(Editor.waiting_for_text)

@router.message(Editor.waiting_for_text)
async def process_editor(message: types.Message, state: FSMContext):
    msg = await message.answer("🧐 Читаю и правлю...")
    result = await ai_edit_text(message.text)
    await msg.edit_text(result)
    await message.answer("Меню:", reply_markup=get_main_keyboard())
    await state.clear()

# ==========================================
# ХЭНДЛЕРЫ: КОНТЕНТ-ПЛАН
# ==========================================

@router.message(F.text == "📅 Контент-план")
async def start_plan(message: types.Message, state: FSMContext):
    await message.answer("На какой период составить план? (например: неделя, месяц):")
    await state.set_state(ContentPlan.waiting_for_params)

@router.message(ContentPlan.waiting_for_params)
async def process_plan(message: types.Message, state: FSMContext):
    msg = await message.answer("📅 Планирую публикации...")
    result = await ai_create_plan(message.text)
    await msg.edit_text(result)
    await message.answer("Меню:", reply_markup=get_main_keyboard())
    await state.clear()

# ==========================================
# СЛУЖЕБНОЕ (НАСТРОЙКИ НКО ИЗ МЕНЮ)
# ==========================================
@router.message(F.text == "⚙️ Моя НКО")
async def my_nko_info(message: types.Message):
    data = users_db.get(message.from_user.id)
    if not data:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📝 Заполнить", callback_data="setup_nko")]])
        await message.answer("Информация об НКО не заполнена.", reply_markup=kb)
    else:
        text = (f"🏢 **Организация:** {data.get('name')}\n"
                f"ℹ️ **Описание:** {data.get('description')}\n"
                f"📣 **Стиль:** {data.get('tone')}")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Изменить", callback_data="setup_nko")]])
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)

# ==========================================
# ЗАПУСК
# ==========================================

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
        from gigachat import GigaChat