from telegram import LabeledPrice, Update
from telegram.ext import CommandHandler, PreCheckoutQueryHandler, MessageHandler, filters, Application
from datetime import datetime, timedelta
import sqlite3
import schedule
import time
import threading

# =======================
# ১. আপনার তথ্য
# =======================

BOT_TOKEN = "8520079202:AAF-exR0ei9h1KCmZ6BGi6mFrzifUcJf78M" 
PAYMENT_TOKEN = "1877036958:TEST:20b0a42f4a3f20c1d8ddf2c1fcaf6f2323b87e3e"  
TARGET_GROUP_ID = -1002541807760 # আপনার গ্রুপের আইডি

# ==================================
# ২. ডেটাবেস ফাংশন
# ==================================

def init_db():
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER PRIMARY KEY,
            expiry_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_member_to_db(user_id, days=30):
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('INSERT OR REPLACE INTO members (user_id, expiry_date) VALUES (?, ?)', 
                   (user_id, expiry_date))
    conn.commit()
    conn.close()
    return expiry_date

# ==================================
# ৩. টেলিগ্রাম হ্যান্ডলার
# ==================================

async def checkout(update: Update, context):
    # দাম ১০০০ টাকা, যা পয়সাতে রূপান্তর করা হলো
    price = LabeledPrice(label="১ মাসের মেম্বারশিপ", amount=1000 * 100) 
    
    await update.message.reply_invoice(
        title="মাসিক সাবস্ক্রিপশন",
        description="এক মাসের জন্য প্রিমিয়াম গ্রুপ এক্সেস।",
        payload=str(update.effective_user.id),
        provider_token=PAYMENT_TOKEN,
        currency="BDT", 
        prices=[price],
        start_parameter="start_param",
        is_flexible=False
    )

async def pre_checkout_query(update: Update, context):
    query = update.pre_checkout_query
    await query.answer(ok=True) 

async def successful_payment(update: Update, context):
    user_id = update.message.successful_payment.invoice_payload
    expiry_date = add_member_to_db(user_id, days=30)
    
    # গ্রুপে যোগ করার জন্য ইনভাইট লিঙ্ক তৈরি
    invite_link = await context.bot.create_chat_invite_link(
        chat_id=TARGET_GROUP_ID, 
        member_limit=1, 
        expire_date=datetime.now() + timedelta(hours=1)
    )

    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ পেমেন্ট সফল হয়েছে! আপনার মেম্বারশিপের মেয়াদ **{expiry_date}** পর্যন্ত।\n\nগ্রুপে জয়েন করার লিঙ্ক: {invite_link.invite_link}",
        parse_mode='Markdown'
    )

# ==================================
# ৪. রিমুভাল শিডিউলার
# ==================================

def check_and_remove_expired_members(application: Application):
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('SELECT user_id FROM members WHERE expiry_date < ?', (now,))
    expired_members = cursor.fetchall()

    for (user_id,) in expired_members:
        try:
            # গ্রুপ থেকে রিমুভ (ব্যান) করুন
            application.bot.ban_chat_member(
                chat_id=TARGET_GROUP_ID, 
                user_id=user_id
            )
            # ডেটাবেস থেকে মেম্বারকে মুছে দিন
            cursor.execute('DELETE FROM members WHERE user_id = ?', (user_id,))
            
            # মেম্বারকে নোটিফিকেশন পাঠানো
            application.bot.send_message(
                chat_id=user_id,
                text="❌ দুঃখিত! আপনার মেম্বারশিপের মেয়াদ শেষ হয়ে যাওয়ায় আপনাকে গ্রুপ থেকে রিমুভ করা হলো। নতুন করে সাবস্ক্রাইব করতে `/checkout` টাইপ করুন।"
            )
            
        except Exception as e:
            # যদি ব্যবহারকারী ইতিমধ্যে গ্রুপে না থাকে, তবে এড়িয়ে যান
            pass

    conn.commit()
    conn.close()

def run_scheduler(application):
    # প্রতিদিন রাত ১২টায় চেক করবে
    schedule.every().day.at("00:00").do(check_and_remove_expired_members, application)
    while True:
        schedule.run_pending()
        time.sleep(1)

# ==================================
# ৫. বট চালু করা
# ==================================

def main():
    init_db() 
    application = Application.builder().token(BOT_TOKEN).build()

    # হ্যান্ডলার যোগ
    application.add_handler(CommandHandler("checkout", checkout))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    # রিমুভাল লজিক একটি আলাদা থ্রেডে চালু করা
    threading.Thread(target=run_scheduler, args=(application,)).start()

    # বট শুরু
    application.run_polling(poll_interval=3)

if __name__ == '__main__':
    main()
