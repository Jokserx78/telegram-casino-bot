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
    Updater,  # ← ВАЖНО: используем Updater для версии 13.15
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    Filters,
    CallbackContext
)

# Конфигурация
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [8259635146, 7993168159]
SUPPORT_USERNAME = "@LEOLST"

# Способы оплаты
PAYMENT_METHODS = {
    "sber": "🏦 Сбербанк"
}

PAYMENT_DETAILS = {
    "sber": {
        "bank": "Сбербанк",
        "number": "+79002962952",
        "holder": "Эвелина О..",
        "instruction": "Переведите сумму на указанный номер карты"
    }
}

# Банки для вывода
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

# Состояния
(SELECT_PAYMENT_METHOD, ENTER_DEPOSIT_AMOUNT, CONFIRM_DEPOSIT,
 ENTER_WITHDRAW_AMOUNT, SELECT_BANK, ENTER_DETAILS, CONFIRM_WITHDRAW,
 ENTER_BET_AMOUNT) = range(8)

# === БАЗА ДАННЫХ (оставить как было) ===
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

def generate_invoice():
    return f"#{''.join(random.choices(string.ascii_uppercase, k=5))}"

# === КЛАВИАТУРЫ (оставить как было) ===
def get_main_reply_keyboard():
    keyboard = [
        ["👤 Профиль", "🎮 Игры"],
        ["💰 Финансы", "📜 Правила"],
        ["🎰 SONNET CASINO"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

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

# === ОБРАБОТЧИКИ КОМАНД ===
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = user.id
    
    create_user(user_id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""
✨ *Добро пожаловать в SONNET CASINO* ✨

🎰 *{user.first_name}*, приветствуем вас в нашем казино!

Используйте кнопки меню для навигации.

💰 *Минимальный депозит:* 10 ₽
💸 *Минимальный вывод:* 100 ₽
"""
    
    keyboard = [
        ["👤 Профиль", "🎮 Игры"],
        ["💰 Финансы", "📜 Правила"]
    ]
    
    update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

def profile_command(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user = get_user(user_id)
    
    if user:
        profile_text = f"""
📊 *Ваш профиль*

👤 *Имя:* {user['first_name']} {user.get('last_name', '')}
💰 *Баланс:* {user['balance']:.2f} ₽
🎮 *Последняя ставка:* {user['last_bet_amount']:.2f} ₽
"""
        update.message.reply_text(profile_text, parse_mode='Markdown')

def handle_text(update: Update, context: CallbackContext):
    text = update.message.text
    
    if text == "👤 Профиль":
        profile_command(update, context)
    elif text == "🎮 Игры":
        update.message.reply_text("🎮 Выберите игру:", reply_markup=get_games_keyboard())
    elif text == "💰 Финансы":
        update.message.reply_text("💰 Финансы:", reply_markup=get_finances_keyboard())
    elif text == "📜 Правила":
        update.message.reply_text("📜 Правила в разработке...")
    elif text == "🎰 SONNET CASINO":
        update.message.reply_text("🎰 Казино в разработке...")

# === CALLBACK ОБРАБОТЧИКИ ===
def deposit_start(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if user and user['deposit_invoice']:
        keyboard = [
            [InlineKeyboardButton("➡️ Перейти к счету", callback_data="active_deposit")],
            [InlineKeyboardButton("❌ Отменить счет", callback_data="cancel_active_deposit")]
        ]
        query.edit_message_text(
            f"⚠️ *У вас уже есть активный счет*\n\nСчет: `{user['deposit_invoice']}`\nСумма: {user['deposit_amount']} ₽",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_PAYMENT_METHOD
    
    query.edit_message_text(
        "💳 *Выбор способа оплаты*",
        parse_mode='Markdown',
        reply_markup=get_payment_methods_keyboard()
    )
    
    return SELECT_PAYMENT_METHOD

def select_payment_method(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    if query.data == "deposit_cancel":
        query.edit_message_text("❌ *Пополнение отменено*", parse_mode='Markdown')
        return ConversationHandler.END
    
    context.user_data['payment_method'] = 'sber'
    
    query.edit_message_text("💳 *Введите сумму (мин. 10 ₽):*", parse_mode='Markdown')
    
    return ENTER_DEPOSIT_AMOUNT

def handle_deposit_amount_text(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    
    try:
        amount = float(update.message.text)
        
        if amount < 10:
            update.message.reply_text("❌ *Минимум 10 рублей*", parse_mode='Markdown')
            return ENTER_DEPOSIT_AMOUNT
        
        context.user_data['deposit_amount'] = amount
        
        update.message.reply_text(
            f"💳 *Подтверждение*\n\nСумма: *{amount:.2f} ₽*\nВерно?",
            parse_mode='Markdown',
            reply_markup=get_confirmation_keyboard()
        )
        
        return CONFIRM_DEPOSIT
        
    except ValueError:
        update.message.reply_text("❌ *Введите число*", parse_mode='Markdown')
        return ENTER_DEPOSIT_AMOUNT

def confirm_deposit(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    if query.data == 'cancel':
        query.edit_message_text("❌ *Отменено*", parse_mode='Markdown')
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
├ Сумма: *{amount:.2f} ₽*
├ Реквизиты: `{details['number']}`
└ Получатель: *{details['holder']}*
"""
    
    query.edit_message_text(payment_text, parse_mode='Markdown')
    
    # Уведомление админам
    user = query.from_user
    for admin_id in ADMIN_IDS:
        try:
            context.bot.send_message(
                admin_id,
                f"📋 *Новая заявка*\n\nСчет: `{invoice}`\nЮзер: {user.first_name}\nСумма: *{amount:.2f} ₽*",
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
def game_dice(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    last_bet = user['last_bet_amount'] if user else 0
    
    bet_text = "Введите сумму ставки:"
    if last_bet > 0:
        bet_text = f"Введите сумму ставки:\n*Последняя ставка:* {last_bet:.2f} ₽"
    
    query.edit_message_text(f"🎲 *Кубики*\n\n{bet_text}", parse_mode='Markdown')
    
    context.user_data['game_type'] = 'dice'
    return ENTER_BET_AMOUNT

def enter_bet_amount(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user = get_user(user_id)
    
    try:
        bet_amount = float(update.message.text)
        
        if bet_amount < 1:
            update.message.reply_text("❌ *Минимум 1 рубль*", parse_mode='Markdown')
            return ENTER_BET_AMOUNT
        
        if bet_amount > user['balance']:
            update.message.reply_text(f"❌ *Недостаточно!*\nБаланс: {user['balance']:.2f} ₽", parse_mode='Markdown')
            return ENTER_BET_AMOUNT
        
        context.user_data['bet_amount'] = bet_amount
        game_type = context.user_data.get('game_type', 'dice')
        
        update.message.reply_text(
            f"🎯 *Подтверждение*\n\nИгра: *{'🎲 Кубики' if game_type == 'dice' else '🎰 Автоматы'}*\nСтавка: *{bet_amount:.2f} ₽*\n\nПодтверждаете?",
            parse_mode='Markdown',
            reply_markup=get_game_bet_keyboard(game_type)
        )
        
        return ConversationHandler.END
        
    except ValueError:
        update.message.reply_text("❌ *Введите число*", parse_mode='Markdown')
        return ENTER_BET_AMOUNT

def place_bet(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    if query.data == 'cancel_bet':
        query.edit_message_text("❌ *Ставка отменена*", parse_mode='Markdown')
        return
    
    game_type = query.data.replace('place_bet_', '')
    bet_amount = context.user_data.get('bet_amount', 0)
    
    start_game(update, context, game_type, bet_amount)

# Упрощенная игра
def start_game(update: Update, context: CallbackContext, game_type: str, bet_amount: float):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Списываем средства
    update_balance(user_id, -bet_amount)
    set_last_bet(user_id, bet_amount)
    
    # Простой результат (без анимации)
    import random
    
    if game_type == 'dice':
        dice_value = random.randint(2, 12)
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
        slots_value = random.randint(1, 100)
        if slots_value == 1:
            win_multiplier = 10.0
            result_text = "🎰 ДЖЕКПОТ!"
        elif slots_value <= 10:
            win_multiplier = 5.0
            result_text = "Большой выигрыш x5!"
        elif slots_value <= 30:
            win_multiplier = 2.0
            result_text = "Выигрыш x2!"
        else:
            win_multiplier = 0.0
            result_text = "Проигрыш"
    
    win_amount = bet_amount * win_multiplier
    if win_amount > 0:
        update_balance(user_id, win_amount)
    
    # Сохраняем историю
    result_status = "win" if win_amount > bet_amount else "lose" if win_amount < bet_amount else "draw"
    add_transaction(user_id, 'game', bet_amount, result_status, f"game_{game_type}")
    
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
    
    query.message.reply_text(
        result_message,
        parse_mode='Markdown',
        reply_markup=get_play_again_keyboard(game_type, win_amount > 0)
    )

# === ОСНОВНАЯ ФУНКЦИЯ ===
def main():
    if not BOT_TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не найден!")
        return
    
    init_db()
    
    try:
        # ИСПОЛЬЗУЕМ Updater для версии 13.15
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # ConversationHandler для пополнения
        deposit_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
            states={
                SELECT_PAYMENT_METHOD: [CallbackQueryHandler(select_payment_method, pattern="^(method_|deposit_cancel)")],
                ENTER_DEPOSIT_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, handle_deposit_amount_text)],
                CONFIRM_DEPOSIT: [CallbackQueryHandler(confirm_deposit, pattern="^(confirm|cancel)$")]
            },
            fallbacks=[CommandHandler("start", start)],
            name="deposit_conversation"
        )
        
        # ConversationHandler для ставок
        bet_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(game_dice, pattern="^game_dice$")
            ],
            states={
                ENTER_BET_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, enter_bet_amount)]
            },
            fallbacks=[CommandHandler("start", start)],
            name="bet_conversation"
        )
        
        # Регистрируем обработчики
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(deposit_conv)
        dp.add_handler(bet_conv)
        
        # Обработчики игр
        dp.add_handler(CallbackQueryHandler(place_bet, pattern="^place_bet_"))
        
        # Общий обработчик callback
        dp.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer()))
        
        # Обработчик текста
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
        
        print("🤖 Бот запускается (версия 13.15)...")
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()