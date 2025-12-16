import os
import asyncio
import random
import string
import sqlite3
from datetime import datetime, timedelta
from contextlib import closing
from typing import Dict, Tuple, Optional
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# Конфигурация
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [8259635146, 7993168159]  # админы
SUPPORT_USERNAME = "@LEOLST"

# Способы оплаты
PAYMENT_METHODS = {
    "sber": "🏦 Сбербанк"
}

# Реквизиты для каждого способа оплаты
PAYMENT_DETAILS = {
    "sber": {
        "bank": "Сбербанк",
        "number": "+79002962952",
        "holder": "Эвелина О..",
        "instruction": "Переведите сумму на указанный номер карты"
    }
}

# Список банков для вывода
BANKS = {
    "sber": "🏦 Сбербанк",
    "tinkoff": "💳 Тинькофф",
    "yoomoney": "💰 ЮMoney",
    "alpha": "🔷 Альфа-Банк",
    "vtb": "🏛️ ВТБ",
    "gazprom": "⛽ Газпромбанк",
    "raiff": "🎯 Райффайзен",
    "other": "📱 Другой банк"
}

# Состояния для ConversationHandler
(SELECT_PAYMENT_METHOD, ENTER_DEPOSIT_AMOUNT, CONFIRM_DEPOSIT,
 ENTER_WITHDRAW_AMOUNT, SELECT_BANK, ENTER_DETAILS, CONFIRM_WITHDRAW,
 ENTER_BET_AMOUNT) = range(8)

# Инициализация базы данных
def init_db():
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance REAL DEFAULT 0,
                withdrawn REAL DEFAULT 0,
                deposit_invoice TEXT,
                deposit_amount REAL,
                deposit_method TEXT,
                deposit_time TIMESTAMP,
                withdraw_invoice TEXT,
                withdraw_amount REAL,
                withdraw_bank TEXT,
                withdraw_details TEXT,
                withdraw_time TIMESTAMP,
                last_bet_amount REAL DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                status TEXT,
                invoice TEXT,
                details TEXT,
                method TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                game_type TEXT,
                bet_amount REAL,
                win_amount REAL,
                result TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

# Функции для работы с пользователями
def get_user(user_id: int):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if user:
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, user))
    return None

def create_user(user_id: int, username: str, first_name: str, last_name: str = ""):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, balance) 
            VALUES (?, ?, ?, ?, 0)
        ''', (user_id, username, first_name, last_name))
        conn.commit()

def update_balance(user_id: int, amount: float):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", 
                      (amount, user_id))
        conn.commit()

def update_withdrawn(user_id: int, amount: float):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET withdrawn = withdrawn + ? WHERE user_id = ?", 
                      (amount, user_id))
        conn.commit()

def set_deposit_invoice(user_id: int, invoice: str, amount: float, method: str):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET 
            deposit_invoice = ?, 
            deposit_amount = ?,
            deposit_method = ?,
            deposit_time = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (invoice, amount, method, user_id))
        conn.commit()

def set_withdraw_invoice(user_id: int, invoice: str, amount: float, bank: str, details: str):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET 
            withdraw_invoice = ?, 
            withdraw_amount = ?,
            withdraw_bank = ?,
            withdraw_details = ?,
            withdraw_time = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (invoice, amount, bank, details, user_id))
        conn.commit()

def clear_deposit_invoice(user_id: int):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET 
            deposit_invoice = NULL, 
            deposit_amount = NULL,
            deposit_method = NULL,
            deposit_time = NULL
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()

def clear_withdraw_invoice(user_id: int):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET 
            withdraw_invoice = NULL, 
            withdraw_amount = NULL,
            withdraw_bank = NULL,
            withdraw_details = NULL,
            withdraw_time = NULL
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()

def set_last_bet(user_id: int, amount: float):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_bet_amount = ? WHERE user_id = ?", 
                      (amount, user_id))
        conn.commit()

def add_transaction(user_id: int, type_: str, amount: float, status: str, invoice: str, details: str = "", method: str = ""):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, type, amount, status, invoice, details, method)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, type_, amount, status, invoice, details, method))
        conn.commit()

def add_game_history(user_id: int, game_type: str, bet_amount: float, win_amount: float, result: str):
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO games (user_id, game_type, bet_amount, win_amount, result)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, game_type, bet_amount, win_amount, result))
        conn.commit()

def generate_invoice():
    return f"#{''.join(random.choices(string.ascii_uppercase, k=5))}"

# Основная клавиатура бота
def get_main_reply_keyboard():
    keyboard = [
        ["👤 Профиль", "🎮 Игры"],
        ["💰 Финансы", "📜 Правила"],
        ["🎰 SONNET CASINO"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# Inline клавиатуры
def get_main_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📜 Пользовательское соглашение", callback_data="agreement")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_profile_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="profile_refresh")],
        [InlineKeyboardButton("📊 Статистика", callback_data="game_stats")],
        [InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_finances_keyboard():
    keyboard = [
        [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton("💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton("📋 Мои транзакции", callback_data="transactions")],
        [InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎲 Кубики", callback_data="game_dice")],
        [InlineKeyboardButton("🎰 Автоматы", callback_data="game_slots")],
        [InlineKeyboardButton("📊 Статистика", callback_data="game_stats")],
        [InlineKeyboardButton("🎯 Быстрая игра", callback_data="quick_game")],
        [InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_payment_methods_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏦 Сбербанк", callback_data="method_sber")],
        [InlineKeyboardButton("❌ Отмена", callback_data="deposit_cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_banks_keyboard():
    keyboard = []
    banks_list = list(BANKS.items())
    for i in range(0, len(banks_list), 2):
        row = []
        for bank_id, bank_name in banks_list[i:i+2]:
            row.append(InlineKeyboardButton(bank_name, callback_data=f"bank_{bank_id}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="withdraw_cancel")])
    return InlineKeyboardMarkup(keyboard)

def get_confirmation_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_game_bet_keyboard(game_type: str):
    keyboard = [
        [InlineKeyboardButton("✅ Сделать ставку", callback_data=f"place_bet_{game_type}")],
        [InlineKeyboardButton("✏️ Изменить ставку", callback_data=f"change_bet_{game_type}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_bet")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_play_again_keyboard(game_type: str, same_bet: bool = True):
    keyboard = [
        [InlineKeyboardButton("🔄 Играть еще", callback_data=f"play_again_{game_type}")],
        [
            InlineKeyboardButton("✏️ Изменить ставку", callback_data=f"change_bet_{game_type}"),
            InlineKeyboardButton("🎮 Другая игра", callback_data="games")
        ],
        [InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]
    ]
    if same_bet:
        keyboard[0].append(InlineKeyboardButton("💰 Та же ставка", callback_data=f"same_bet_{game_type}"))
    return InlineKeyboardMarkup(keyboard)

def get_transactions_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Все транзакции", callback_data="all_transactions")],
        [InlineKeyboardButton("💳 Пополнения", callback_data="deposit_transactions")],
        [InlineKeyboardButton("💸 Выводы", callback_data="withdraw_transactions")],
        [InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    create_user(user_id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""
✨ *Добро пожаловать в SONNET CASINO* ✨

🎰 *{user.first_name}*, приветствуем вас в нашем казино!

Здесь вы можете насладиться простыми и честными играми.
Используйте кнопки меню для навигации.

🎲 *Доступные игры:*
• 🎲 Кубики - классическая игра на удачу
• 🎰 Автоматы - испытайте удачу на слотах

💰 *Минимальный депозит:* 10 ₽
💸 *Минимальный вывод:* 100 ₽
⚡ *Быстрые выплаты*
🔒 *Полная безопасность*

*Удачной игры!* 🍀
"""
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_inline_keyboard()
    )
    
    await update.message.reply_text(
        "🎰 *Выберите действие:*",
        parse_mode='Markdown',
        reply_markup=get_main_reply_keyboard()
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "👤 Профиль":
        await profile_command(update, context)
    elif text == "🎮 Игры":
        await games_command(update, context)
    elif text == "💰 Финансы":
        await finances_command(update, context)
    elif text == "📜 Правила":
        await rules_command(update, context)
    elif text == "🎰 SONNET CASINO":
        await casino_info(update, context)

async def casino_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_text = """
🎰 *SONNET CASINO*

⚡ *Основные функции:*
• 🎲 Две азартные игры
• 💳 Удобное пополнение
• 💸 Быстрый вывод
• 📊 Подробная статистика

🎯 *Особенности:*
• Минималистичный дизайн
• Простой интерфейс
• Мгновенные выплаты
• Поддержка 24/7

📞 *Техподдержка:* @LEOLST
"""
    
    await update.message.reply_text(
        info_text,
        parse_mode='Markdown'
    )

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = get_user(user_id)
    
    if user:
        profile_text = f"""
📊 *Ваш профиль*

👤 *Имя:* {user['first_name']} {user.get('last_name', '')}
🆔 *ID:* {user_id}
🔖 *Юзернейм:* @{user['username'] if user['username'] else 'Нет'}
💰 *Баланс:* {user['balance']:.2f} ₽
💸 *Выведено:* {user['withdrawn']:.2f} ₽
🎮 *Последняя ставка:* {user['last_bet_amount']:.2f} ₽
"""
        
        await update.message.reply_text(
            profile_text,
            parse_mode='Markdown',
            reply_markup=get_profile_keyboard()
        )

async def finances_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 *Финансовые операции*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=get_finances_keyboard()
    )

async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 *Игровой зал*\n\nВыберите игру:",
        parse_mode='Markdown',
        reply_markup=get_games_keyboard()
    )

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules_text = """
📜 *Правила SONNET CASINO*

🎰 *Общие правила:*
• Минимальный возраст: 18 лет
• Все игры используют ГСЧ для честности
• Вывод средств осуществляется на банковские карты

💰 *Финансы:*
├ Минимальный депозит: 10 ₽
├ Минимальный вывод: 100 ₽
├ Комиссия при выводе: 0%
└ Время обработки вывода: 1-12 часов

🎮 *Игры:*
• 🎲 Кубики: Ставки от 1 ₽, коэффициенты до x2
• 🎰 Автоматы: Ставки от 1 ₽, коэффициенты до x10

📞 *Поддержка:* @LEOLST
"""
    
    await update.message.reply_text(
        rules_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]])
    )

# Callback обработчики
async def agreement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "❌ *Упс, тут пока ничего нет*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="main_menu_inline")]])
    )

async def profile_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if user:
        profile_text = f"""
📊 *Ваш профиль*

👤 *Имя:* {user['first_name']} {user.get('last_name', '')}
🆔 *ID:* {user_id}
🔖 *Юзернейм:* @{user['username'] if user['username'] else 'Нет'}
💰 *Баланс:* {user['balance']:.2f} ₽
💸 *Выведено:* {user['withdrawn']:.2f} ₽
🎮 *Последняя ставка:* {user['last_bet_amount']:.2f} ₽
"""
        
        await query.edit_message_text(
            profile_text,
            parse_mode='Markdown',
            reply_markup=get_profile_keyboard()
        )

async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if user and user['deposit_invoice']:
        keyboard = [
            [InlineKeyboardButton("➡️ Перейти к счету", callback_data="active_deposit")],
            [InlineKeyboardButton("❌ Отменить счет", callback_data="cancel_active_deposit")]
        ]
        await query.edit_message_text(
            f"⚠️ *У вас уже есть активный счет*\n\nСчет: `{user['deposit_invoice']}`\nСумма: {user['deposit_amount']} ₽",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    await query.edit_message_text(
        "💳 *Выбор способа оплаты*\n\nВыберите способ:",
        parse_mode='Markdown',
        reply_markup=get_payment_methods_keyboard()
    )
    
    return SELECT_PAYMENT_METHOD

async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "deposit_cancel":
        await query.edit_message_text(
            "❌ *Пополнение отменено*",
            parse_mode='Markdown'
        )
        await finances_command_callback(update, context)
        return ConversationHandler.END
    
    context.user_data['payment_method'] = 'sber'
    
    await query.edit_message_text(
        f"💳 *Пополнение через Сбербанк*\n\nВведите сумму (мин. 10 ₽):",
        parse_mode='Markdown'
    )
    
    return ENTER_DEPOSIT_AMOUNT

async def handle_deposit_amount_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    try:
        amount = float(update.message.text)
        
        if amount < 10:
            await update.message.reply_text("❌ *Минимум 10 рублей*", parse_mode='Markdown')
            return ENTER_DEPOSIT_AMOUNT
        
        context.user_data['deposit_amount'] = amount
        
        await update.message.reply_text(
            f"💳 *Подтверждение*\n\nСумма: *{amount:.2f} ₽*\nВерно?",
            parse_mode='Markdown',
            reply_markup=get_confirmation_keyboard()
        )
        
        return CONFIRM_DEPOSIT
        
    except ValueError:
        await update.message.reply_text("❌ *Введите число*", parse_mode='Markdown')
        return ENTER_DEPOSIT_AMOUNT

async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel':
        await query.edit_message_text("❌ *Отменено*", parse_mode='Markdown')
        return ConversationHandler.END
    
    user_id = query.from_user.id
    amount = context.user_data.get('deposit_amount', 0)
    details = PAYMENT_DETAILS.get('sber')
    
    invoice = generate_invoice()
    set_deposit_invoice(user_id, invoice, amount, "Сбербанк")
    add_transaction(user_id, 'deposit', amount, 'pending', invoice, details['number'], "Сбербанк")
    
    payment_text = f"""
💳 *Счет создан*

📋 *Детали:*
├ Счет: `{invoice}`
├ Способ: Сбербанк
├ Сумма: *{amount:.2f} ₽*
├ Реквизиты: `{details['number']}`
└ Получатель: *{details['holder']}*

📝 *Инструкция:*
1. {details['instruction']}
2. В комментарии укажите: `{invoice}`
"""
    
    await query.edit_message_text(
        payment_text,
        parse_mode='Markdown'
    )
    
    # Уведомление админам
    user = query.from_user
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"📋 *Новая заявка на пополнение*\n\nСчет: `{invoice}`\nЮзер: {user.first_name}\nСумма: *{amount:.2f} ₽*",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Одобрить", callback_data=f"admin_approve_{invoice}"),
                     InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_{invoice}")]
                ])
            )
        except:
            pass
    
    return ConversationHandler.END

# Игры
async def game_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    last_bet = user['last_bet_amount'] if user else 0
    
    bet_text = "Введите сумму ставки:"
    if last_bet > 0:
        bet_text = f"Введите сумму ставки:\n*Последняя ставка:* {last_bet:.2f} ₽"
    
    await query.edit_message_text(
        f"🎲 *Игра в кубики*\n\n{bet_text}",
        parse_mode='Markdown'
    )
    
    context.user_data['game_type'] = 'dice'
    return ENTER_BET_AMOUNT

async def game_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data['game_type'] = 'slots'
    
    await query.edit_message_text(
        "🎰 *Автоматы*\n\nВведите сумму ставки:",
        parse_mode='Markdown'
    )
    
    return ENTER_BET_AMOUNT

async def enter_bet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = get_user(user_id)
    
    try:
        bet_amount = float(update.message.text)
        
        if bet_amount < 1:
            await update.message.reply_text("❌ *Минимальная ставка: 1 ₽*", parse_mode='Markdown')
            return ENTER_BET_AMOUNT
        
        if bet_amount > user['balance']:
            await update.message.reply_text(f"❌ *Недостаточно средств!*\nБаланс: {user['balance']:.2f} ₽", parse_mode='Markdown')
            return ENTER_BET_AMOUNT
        
        context.user_data['bet_amount'] = bet_amount
        game_type = context.user_data.get('game_type', 'dice')
        
        await update.message.reply_text(
            f"🎯 *Подтверждение*\n\nИгра: *{'🎲 Кубики' if game_type == 'dice' else '🎰 Автоматы'}*\nСтавка: *{bet_amount:.2f} ₽*\n\nПодтверждаете?",
            parse_mode='Markdown',
            reply_markup=get_game_bet_keyboard(game_type)
        )
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ *Введите число*", parse_mode='Markdown')
        return ENTER_BET_AMOUNT

async def place_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel_bet':
        await query.edit_message_text("❌ *Ставка отменена*", parse_mode='Markdown')
        return
    
    game_type = query.data.replace('place_bet_', '')
    bet_amount = context.user_data.get('bet_amount', 0)
    
    await start_game(update, context, game_type, bet_amount)

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str, bet_amount: float):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Списываем средства
    update_balance(user_id, -bet_amount)
    set_last_bet(user_id, bet_amount)
    
    # Отправляем анимацию
    emoji = '🎲' if game_type == 'dice' else '🎰'
    dice_message = await query.message.reply_dice(emoji=emoji)
    
    await asyncio.sleep(5.5)
    
    # Результат
    dice_value = dice_message.dice.value
    
    if game_type == 'dice':
        if 2 <= dice_value <= 6:
            win_multiplier = 0.0
            result_text = f"Выпало: {dice_value} - Проигрыш"
        elif dice_value == 7:
            win_multiplier = 1.0
            result_text = f"Выпало: 7 - Ничья"
        else:
            win_multiplier = 2.0
            result_text = f"Выпало: {dice_value} - Выигрыш x2!"
    else:
        if dice_value == 1:
            win_multiplier = 10.0
            result_text = "🎰 ДЖЕКПОТ! 777 🎰"
        elif dice_value <= 5:
            win_multiplier = 5.0
            result_text = "3 одинаковых - Выигрыш x5!"
        elif dice_value <= 15:
            win_multiplier = 2.0
            result_text = "2 одинаковых - Выигрыш x2!"
        else:
            win_multiplier = 0.0
            result_text = "Проигрыш"
    
    win_amount = bet_amount * win_multiplier
    if win_amount > 0:
        update_balance(user_id, win_amount)
    
    # Сохраняем историю
    result_status = "win" if win_amount > bet_amount else "lose" if win_amount < bet_amount else "draw"
    add_game_history(user_id, game_type, bet_amount, win_amount, result_status)
    
    # Отправляем результат
    balance = get_user(user_id)['balance']
    
    result_message = f"""
🎮 *Результат*

{result_text}

💰 *Детали:*
├ Ставка: {bet_amount:.2f} ₽
├ Выигрыш: {win_amount:.2f} ₽
└ Баланс: *{balance:.2f} ₽*
"""
    
    await query.message.reply_text(
        result_message,
        parse_mode='Markdown',
        reply_markup=get_play_again_keyboard(game_type, win_amount > 0)
    )

async def play_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace('play_again_', '')
    if data.startswith('same_bet_'):
        game_type = data.replace('same_bet_', '')
        user_id = query.from_user.id
        user = get_user(user_id)
        bet_amount = user['last_bet_amount'] if user and user['last_bet_amount'] > 0 else 10
        
        if bet_amount > user['balance']:
            await query.answer(f"❌ Недостаточно средств! Баланс: {user['balance']:.2f} ₽", show_alert=True)
            return
    else:
        game_type = data
        bet_amount = context.user_data.get('bet_amount', 10)
    
    await start_game(update, context, game_type, bet_amount)

async def game_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                COUNT(*) as total_games,
                SUM(bet_amount) as total_bet,
                SUM(win_amount) as total_win,
                SUM(CASE WHEN win_amount > bet_amount THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN win_amount < bet_amount THEN 1 ELSE 0 END) as losses
            FROM games 
            WHERE user_id = ?
        ''', (user_id,))
        stats = cursor.fetchone()
    
    if stats and stats[0] > 0:
        total_games, total_bet, total_win, wins, losses = stats
        profit = total_win - total_bet
        
        stats_text = f"""
📊 *Статистика*

🎮 *Общая:*
├ Всего игр: {total_games}
├ Побед: {wins}
└ Поражений: {losses}

💰 *Финансовая:*
├ Всего поставлено: {total_bet:.2f} ₽
├ Всего выиграно: {total_win:.2f} ₽
└ Прибыль: {profit:.2f} ₽
"""
    else:
        stats_text = "📊 *У вас пока нет игровой статистики*"
    
    await query.edit_message_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Игры", callback_data="games")]])
    )

async def show_main_menu_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎰 *Главное меню*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("🎮 Игры", callback_data="games")],
            [InlineKeyboardButton("💰 Финансы", callback_data="finances")]
        ])
    )

async def finances_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💰 *Финансы*",
        parse_mode='Markdown',
        reply_markup=get_finances_keyboard()
    )

async def games_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎮 *Игры*",
        parse_mode='Markdown',
        reply_markup=get_games_keyboard()
    )

# Админ функции
async def admin_approve_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Нет прав", show_alert=True)
        return
    
    invoice = query.data.replace("admin_approve_", "")
    
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, deposit_amount FROM users WHERE deposit_invoice = ?", (invoice,))
        result = cursor.fetchone()
    
    if result:
        user_id, amount = result
        update_balance(user_id, amount)
        clear_deposit_invoice(user_id)
        add_transaction(user_id, 'deposit', amount, 'approved', invoice)
        
        try:
            await context.bot.send_message(
                user_id,
                f"✅ *Баланс пополнен!*\n\nСумма: *{amount:.2f} ₽*\nСчет: `{invoice}`",
                parse_mode='Markdown'
            )
        except:
            pass
        
        await query.edit_message_text(
            f"✅ *Пополнение одобрено*\n\nСчет: `{invoice}`",
            parse_mode='Markdown'
        )

async def admin_reject_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Нет прав", show_alert=True)
        return
    
    invoice = query.data.replace("admin_reject_", "")
    
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, deposit_amount FROM users WHERE deposit_invoice = ?", (invoice,))
        result = cursor.fetchone()
    
    if result:
        user_id, amount = result
        clear_deposit_invoice(user_id)
        add_transaction(user_id, 'deposit', amount, 'rejected', invoice)
        
        await query.edit_message_text(
            f"❌ *Пополнение отклонено*\n\nСчет: `{invoice}`",
            parse_mode='Markdown'
        )

# Общий обработчик callback
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "main_menu_inline":
        await show_main_menu_inline(update, context)
    elif query.data == "profile":
        await profile_command_callback(update, context)
    elif query.data == "profile_refresh":
        await profile_refresh(update, context)
    elif query.data == "finances":
        await finances_command_callback(update, context)
    elif query.data == "games":
        await games_command_callback(update, context)
    elif query.data == "deposit":
        await deposit_start(update, context)
    elif query.data == "withdraw":
        await query.answer("⚠️ В разработке", show_alert=True)
    elif query.data == "transactions":
        await query.answer("⚠️ В разработке", show_alert=True)
    elif query.data == "game_dice":
        await game_dice(update, context)
    elif query.data == "game_slots":
        await game_slots(update, context)
    elif query.data == "game_stats":
        await game_stats(update, context)
    elif query.data.startswith("place_bet_"):
        await place_bet(update, context)
    elif query.data.startswith("play_again_"):
        await play_again(update, context)
    elif query.data.startswith("same_bet_"):
        await play_again(update, context)
    elif query.data.startswith("admin_approve_"):
        await admin_approve_deposit(update, context)
    elif query.data.startswith("admin_reject_"):
        await admin_reject_deposit(update, context)

async def profile_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if user:
        profile_text = f"""
📊 *Ваш профиль*

👤 *Имя:* {user['first_name']} {user.get('last_name', '')}
💰 *Баланс:* {user['balance']:.2f} ₽
🎮 *Последняя ставка:* {user['last_bet_amount']:.2f} ₽
"""
        
        await query.edit_message_text(
            profile_text,
            parse_mode='Markdown',
            reply_markup=get_profile_keyboard()
        )

# Основная функция
def main():
    if not BOT_TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не найден!")
        return
    
    init_db()
    
    try:
        # Создаем Application (НЕ Updater!)
        application = Application.builder().token(BOT_TOKEN).build()
        
        # ConversationHandler для пополнения
        deposit_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
            states={
                SELECT_PAYMENT_METHOD: [CallbackQueryHandler(select_payment_method, pattern="^(method_|deposit_cancel)")],
                ENTER_DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deposit_amount_text)],
                CONFIRM_DEPOSIT: [CallbackQueryHandler(confirm_deposit, pattern="^(confirm|cancel)$")]
            },
            fallbacks=[CommandHandler("start", start)],
            name="deposit_conversation",
            persistent=False
        )
        
        # ConversationHandler для ставок
        bet_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(game_dice, pattern="^game_dice$"),
                CallbackQueryHandler(game_slots, pattern="^game_slots$")
            ],
            states={
                ENTER_BET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_bet_amount)]
            },
            fallbacks=[CommandHandler("start", start)],
            name="bet_conversation",
            persistent=False
        )
        
        # Регистрируем обработчики (ВАЖНЫЙ ПОРЯДОК!)
        application.add_handler(CommandHandler("start", start))
        application.add_handler(deposit_conv)
        application.add_handler(bet_conv)
        
        # Обработчики игр
        application.add_handler(CallbackQueryHandler(place_bet, pattern="^place_bet_"))
        application.add_handler(CallbackQueryHandler(play_again, pattern="^(play_again_|same_bet_)"))
        
        # Админ обработчики
        application.add_handler(CallbackQueryHandler(admin_approve_deposit, pattern="^admin_approve_"))
        application.add_handler(CallbackQueryHandler(admin_reject_deposit, pattern="^admin_reject_"))
        
        # Общие обработчики callback
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Обработчик текстовых сообщений (последний!)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        
        print("🤖 Бот запускается...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()