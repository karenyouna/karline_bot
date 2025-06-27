import os
import pandas as pd
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import configparser
from datetime import datetime
import re

# ======= config read ========
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')
TOKEN = config['bot']['token']
ADMIN_ID = int(config['bot']['admin_id'])
PASSWORD = config['bot']['password']
LOGO_FILE = config['bot']['welcome_logo']

DATA_DIR = './months_data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

LOGS_DIR = './logs'
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

STATE_PASSWORD, STATE_MONTH_SELECT, STATE_MENU = range(3)

# ============================
user_sessions = {}    # user_id: {'authed':bool, 'current_month':str}

def persian_months(files):
    months = []
    for f in files:
        if f.endswith('.xlsx'):
            # rnd to فارسی
            basename = os.path.splitext(f)[0]
            parts = basename.split('_')
            if len(parts)>1:
                months.append(parts[1])
            else:
                months.append(basename)
    return months

def get_month_files():
    files = os.listdir(DATA_DIR)
    months = persian_months(files)
    zipped = zip(months, files)
    return list(zipped)

def persian_weekday_score(date_str):
    # date in 1404/03/31 (jalaali), convert to weekday (fake, for demo)
    try:
        # Assume jalali date & convert to weekday index (simulate)
        parts = date_str.split('/')
        # really should use jdatetime but here, just fake for simplicity
        y, m, d = map(int, parts)
        # Simple mapping: (not accurate, but just for demonstration!)
        weekday_index = (y + m + d) % 7
        # Map: 0=Sat ... 6=Fri
        if 0 <= weekday_index <= 4:
            return 10 # Sat-Wed
        elif weekday_index == 5:
            return 15 # Thu
        else:
            return 20 # Fri
    except:
        return 0

def check_user(user_id):
    return user_sessions.get(user_id, {}).get('authed', False)

def send_welcome(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    user_sessions[user_id] = {'authed': False, 'current_month': None}
    try:
        context.bot.send_photo(chat_id=update.effective_chat.id, photo=open(LOGO_FILE, 'rb'))
    except Exception as e:
        pass  # عکس نبود، رد شو
    msg = "کارشناس کارلاینی عزیز خیلی خوش آمدی😍🦇\n\nلطفاً رمز ورود را وارد کنید:"
    update.message.reply_text(msg)
    return STATE_PASSWORD

def password_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    if update.message.text == PASSWORD:
        user_sessions[user_id]['authed'] = True
        return month_select(update, context)
    else:
        update.message.reply_text('رمز اشتباه است! دوباره تلاش کنید:')
        return STATE_PASSWORD

def month_select(update: Update, context: CallbackContext) -> int:
    month_files = get_month_files()
    if not month_files:
        update.message.reply_text('فعلاً هیچ ماه فعالی وجود ندارد (ادمین هنوز فایل اکسل بارگزاری نکرده است).')
    else:
        month_names = [m for m, f in month_files]
        kb = [[m] for m in month_names]
        update.message.reply_text('ماه مورد نظر را انتخاب کنید:', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return STATE_MONTH_SELECT
    # اگر ماه نبود، مستقیم منو فقط نشون بده:
    return main_menu(update, context)

def select_month_handler(update: Update, context: CallbackContext) -> int:
    selected = update.message.text
    # پیدا کردن فایل اکسل ماه
    found = None
    for m, fname in get_month_files():
        if m == selected:
            found = fname
            break
    user_id = update.effective_user.id
    if not found:
        update.message.reply_text('ماه انتخاب شده معتبر نیست! لطفاً بین گزینه‌ها انتخاب کنید.')
        return STATE_MONTH_SELECT
    user_sessions[user_id]['current_month'] = found
    return main_menu(update, context)

def main_menu(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    menu = [['جستجوی نیرو 🔍', 'خروج ⬅️']]
    # اگر ادمین هست:
    if user_id == ADMIN_ID:
        menu = [['جستجوی نیرو 🔍'], ['آپلود فایل اکسل 🗂️', 'گزارش کلی 📊'], ['خروج ⬅️']]
    update.message.reply_text('لطفاً یکی از گزینه‌‌ها را انتخاب کنید:', reply_markup=ReplyKeyboardMarkup(menu, resize_keyboard=True))
    return STATE_MENU

def handle_menu(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    if text == 'جستجوی نیرو 🔍':
        update.message.reply_text('نام یا موبایل نیرو را وارد کنید (بخشی کافیست):')
        context.user_data['waiting_for_query'] = True
        return STATE_MENU
    elif text == 'آپلود فایل اکسل 🗂️' and user_id == ADMIN_ID:
        update.message.reply_text('فایل اکسل ماه جدید را ارسال کنید:')
        context.user_data['waiting_for_excel'] = True
        return STATE_MENU
    elif text == 'گزارش کلی 📊' and user_id == ADMIN_ID:
        user_month = user_sessions.get(user_id, {}).get('current_month')
        if not user_month:
            update.message.reply_text('ابتدا ماه مورد نظر را انتخاب کنید.')
            return month_select(update, context)
        report_msg = generate_report(user_month)
        update.message.reply_text(report_msg)
        return STATE_MENU
    elif text == 'خروج ⬅️':
        user_sessions[user_id] = {'authed': False, 'current_month': None}
        return send_welcome(update, context)
    else:
        if context.user_data.get('waiting_for_query'):
            query = text.strip()
            user_month = user_sessions.get(user_id, {}).get('current_month')
            if not user_month:
                update.message.reply_text('ابتدا ماه مورد نظر را انتخاب کنید.')
                return month_select(update, context)
            file_path = os.path.join(DATA_DIR, user_month)
            msg = search_worker(query, file_path)
            update.message.reply_text(msg)
            context.user_data['waiting_for_query'] = False
            return STATE_MENU
        elif context.user_data.get('waiting_for_excel') and user_id == ADMIN_ID:
            update.message.reply_text('فقط به صورت فایل اکسل ارسال نمایید')
            context.user_data['waiting_for_excel'] = False
            return STATE_MENU
        else:
            update.message.reply_text('گزینه نامعتبر است. دوباره انتخاب کنید.')
            return STATE_MENU

def is_valid_excel(filename):
    return filename.endswith('.xlsx')

def handle_document(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID or not context.user_data.get('waiting_for_excel'):
        update.message.reply_text('دسترسی آپلود فقط برای ادمین است.')
        return
    doc = update.message.document
    if not is_valid_excel(doc.file_name):
        update.message.reply_text('لطفاً فقط فایل اکسل با پسوند xlsx ارسال کنید.')
        return
    month_name = input("اسم ماه چی باشه؟ (مثل تیرماه): ")
    save_path = os.path.join(DATA_DIR, f"ماه_{month_name}.xlsx")
    doc.get_file().download(custom_path=save_path)
    update.message.reply_text('فایل اکسل ماه جدید ذخیره شد.')
    context.user_data['waiting_for_excel'] = False

def search_worker(query, xlsx_path):
    try:
        df = pd.read_excel(xlsx_path)
    except Exception as e:
        return 'خطا در باز کردن فایل اکسل.'
    # جستجو در نام (Partial) یا موبایل (با یا بدون صفر)
    res = df[
        df['نام نیرو'].str.contains(query, na=False) |
        df['موبایل نیرو'].astype(str).str.contains(query.replace('۰','0').replace('۰','0')) |
        df['موبایل نیرو'].astype(str).str.contains(query.lstrip('0'))
    ]
    if res.empty:
        return 'نیرویی با این مشخصات پیدا نشد.'
    # محاسبه جمع امتیاز
    total_score = 0
    orders = []
    for i, row in res.iterrows():
        score = persian_weekday_score(str(row['تاریخ انجام']))
        total_score += score
        orders.append(row['تاریخ انجام'])
    msg = f"تعداد سفارش پایان کار شده: {len(orders)}\nجمع امتیازات: {total_score}"
    return msg

def generate_report(xlsx_name):
    try:
        df = pd.read_excel(os.path.join(DATA_DIR, xlsx_name))
    except Exception:
        return 'خطا در خواندن اکسل.'
    score_sum = 0
    for i, row in df.iterrows():
        s = persian_weekday_score(str(row['تاریخ انجام']))
        score_sum += s
    return f"تعداد کل سفارشات: {len(df)}\nجمع کل امتیازات: {score_sum}"

# ========== main ===============
def main():
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', send_welcome)],
        states={
            STATE_PASSWORD: [MessageHandler(Filters.text & ~Filters.command, password_handler)],
            STATE_MONTH_SELECT: [MessageHandler(Filters.text & ~Filters.command, select_month_handler)],
            STATE_MENU: [
                MessageHandler(Filters.text & ~Filters.command, handle_menu),
                MessageHandler(Filters.document, handle_document)
            ],
        },
        fallbacks=[CommandHandler('start', send_welcome)]
    )

    dp.add_handler(conv)

    updater.start_polling()
    print('ربات فعال است...')
    updater.idle()

if __name__ == '__main__':
    main()
