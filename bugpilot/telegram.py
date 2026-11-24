import os, logging, requests

def notify(message):
    token=os.getenv('TELEGRAM_BOT_TOKEN')
    chat=os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat: return False
    try:
        response=requests.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat,'text':message},timeout=5)
        return response.ok and response.json().get('ok',False)
    except (requests.RequestException, ValueError):
        logging.warning('Telegram delivery failed')
        return False
