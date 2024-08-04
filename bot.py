import telebot
import requests
import hashlib
import hmac
import base64
import time
from urllib.parse import quote_plus
from apscheduler.schedulers.background import BackgroundScheduler
from config import API_KEY, AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_ASSOCIATE_TAG, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID, CHAT_ID

# Inicialização do bot do Telegram
bot = telebot.TeleBot(API_KEY)

# Estado do bot (modo autônomo ou manual)
autonomous_mode_enabled = False

# Funções auxiliares
def sign_request(secret_key, string_to_sign):
    """Cria uma assinatura usando HMAC-SHA256."""
    signature = hmac.new(secret_key.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha256).digest()
    return base64.b64encode(signature).decode()

def get_affiliate_products(search_index='All', keywords='bestsellers'):
    """Obtém produtos afiliados da Amazon com análise simples de desempenho."""
    url = 'https://webservices.amazon.com/onca/xml'
    params = {
        'Service': 'AWSECommerceService',
        'Operation': 'ItemSearch',
        'AWSAccessKeyId': AMAZON_ACCESS_KEY,
        'AssociateTag': AMAZON_ASSOCIATE_TAG,
        'SearchIndex': search_index,
        'Keywords': keywords,
        'ResponseGroup': 'Images,ItemAttributes,Offers',
        'Timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }

    # Cria uma string a ser assinada
    sorted_params = sorted(params.items())
    canonical_query_string = '&'.join([f"{quote_plus(k)}={quote_plus(v)}" for k, v in sorted_params])
    string_to_sign = f"GET\nwebservices.amazon.com\n/onca/xml\n{canonical_query_string}"
    
    # Cria a assinatura
    signature = sign_request(AMAZON_SECRET_KEY, string_to_sign)
    params['Signature'] = signature

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        products = []
        from xml.etree import ElementTree
        root = ElementTree.fromstring(response.content)
        items = root.find('.//Items')
        for item in items.findall('.//Item'):
            products.append({
                'name': item.find('.//Title').text,
                'affiliate_link': item.find('.//DetailPageURL').text,
                'image_url': item.find('.//LargeImage/URL').text,
                'rating': float(item.find('.//Rating').text) if item.find('.//Rating') is not None else 0,
                'price': float(item.find('.//OfferSummary/LowestNewPrice/Amount').text) / 100 if item.find('.//OfferSummary/LowestNewPrice/Amount') is not None else 0
            })
        # Ordena produtos por rating e preço
        products.sort(key=lambda x: (x['rating'], -x['price']), reverse=True)
        return products
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar produtos: {e}")
        return []

def create_ad_content(product):
    """Cria conteúdo para o anúncio baseado no produto."""
    return (
        f"Confira o incrível {product['name']}!\n"
        f"Preço: ${product['price']:.2f}\n"
        f"Avaliação: {product['rating']} estrelas\n\n"
        f"Compre agora: {product['affiliate_link']}\n"
        f"Imagem: {product['image_url']}"
    )

def post_to_instagram(product):
    """Posta um produto no Instagram."""
    url = f'https://graph.facebook.com/v12.0/{INSTAGRAM_USER_ID}/media'
    headers = {
        'Authorization': f'Bearer {INSTAGRAM_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        'image_url': product['image_url'],
        'caption': create_ad_content(product),
        'access_token': INSTAGRAM_ACCESS_TOKEN
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        creation_id = response.json()['id']
        publish_url = f'https://graph.facebook.com/v12.0/{INSTAGRAM_USER_ID}/media_publish'
        publish_data = {
            'creation_id': creation_id,
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        publish_response = requests.post(publish_url, headers=headers, json=publish_data)
        return publish_response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Erro ao postar no Instagram: {e}")
        return False

def get_latest_products():
    """Obtém os produtos mais recentes."""
    return get_affiliate_products(keywords='new arrivals')

def get_top_rated_products():
    """Obtém os produtos mais bem avaliados."""
    return get_affiliate_products(keywords='top rated')

def search_products(keyword):
    """Pesquisa produtos por palavra-chave."""
    return get_affiliate_products(keywords=keyword)

def get_product_details(product_id):
    """Obtém detalhes de um produto específico (utiliza o ItemLookup da API da Amazon)."""
    url = 'https://webservices.amazon.com/onca/xml'
    params = {
        'Service': 'AWSECommerceService',
        'Operation': 'ItemLookup',
        'AWSAccessKeyId': AMAZON_ACCESS_KEY,
        'AssociateTag': AMAZON_ASSOCIATE_TAG,
        'ItemId': product_id,
        'ResponseGroup': 'Images,ItemAttributes,Offers',
        'Timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }

    # Cria uma string a ser assinada
    sorted_params = sorted(params.items())
    canonical_query_string = '&'.join([f"{quote_plus(k)}={quote_plus(v)}" for k, v in sorted_params])
    string_to_sign = f"GET\nwebservices.amazon.com\n/onca/xml\n{canonical_query_string}"
    
    # Cria a assinatura
    signature = sign_request(AMAZON_SECRET_KEY, string_to_sign)
    params['Signature'] = signature

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        from xml.etree import ElementTree
        root = ElementTree.fromstring(response.content)
        item = root.find('.//Item')
        details = {
            'name': item.find('.//Title').text,
            'affiliate_link': item.find('.//DetailPageURL').text,
            'image_url': item.find('.//LargeImage/URL').text,
            'rating': float(item.find('.//Rating').text) if item.find('.//Rating') is not None else 0,
            'price': float(item.find('.//OfferSummary/LowestNewPrice/Amount').text) / 100 if item.find('.//OfferSummary/LowestNewPrice/Amount') is not None else 0
        }
        return details
    except requests.exceptions.RequestException as e:
        print(f"Erro ao obter detalhes do produto: {e}")
        return {}

# Funções de comando do Telegram
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Bem-vindo ao AffiliateBot! Use /help para ver a lista de comandos disponíveis.")

@bot.message_handler(commands=['products'])
def handle_products(message):
    products = get_affiliate_products()
    response = "Produtos recomendados:\n"
    for product in products:
        response += f"{product['name']}\nLink: {product['affiliate_link']}\n\n"
    bot.reply_to(message, response)

@bot.message_handler(commands=['latest_products'])
def handle_latest_products(message):
    products = get_latest_products()
    response = "Produtos mais recentes:\n"
    for product in products:
        response += f"{product['name']}\nLink: {product['affiliate_link']}\n\n"
    bot.reply_to(message, response)

@bot.message_handler(commands=['top_rated_products'])
def handle_top_rated_products(message):
    products = get_top_rated_products()
    response = "Produtos mais bem avaliados:\n"
    for product in products:
        response += f"{product['name']}\nLink: {product['affiliate_link']}\n\n"
    bot.reply_to(message, response)

@bot.message_handler(commands=['search_product'])
def handle_search_product(message):
    keyword = message.text.split(' ', 1)[1] if len(message.text.split(' ', 1)) > 1 else ''
    if keyword:
        products = search_products(keyword)
        response = f"Resultados para '{keyword}':\n"
        for product in products:
            response += f"{product['name']}\nLink: {product['affiliate_link']}\n\n"
        bot.reply_to(message, response)
    else:
        bot.reply_to(message, "Por favor, forneça uma palavra-chave para a pesquisa.")

@bot.message_handler(commands=['product_details'])
def handle_product_details(message):
    product_id = message.text.split(' ', 1)[1] if len(message.text.split(' ', 1)) > 1 else ''
    if product_id:
        details = get_product_details(product_id)
        if details:
            response = (
                f"Detalhes do produto:\n"
                f"Nome: {details['name']}\n"
                f"Preço: ${details['price']:.2f}\n"
                f"Avaliação: {details['rating']} estrelas\n"
                f"Link: {details['affiliate_link']}\n"
                f"Imagem: {details['image_url']}"
            )
            bot.reply_to(message, response)
        else:
            bot.reply_to(message, "Não foi possível obter detalhes do produto.")
    else:
        bot.reply_to(message, "Por favor, forneça o ID do produto.")

@bot.message_handler(commands=['unsubscribe'])
def handle_unsubscribe(message):
    # Implementar lógica para desinscrição, se necessário
    bot.reply_to(message, "Você foi desinscrito com sucesso.")

@bot.message_handler(commands=['subscribe'])
def handle_subscribe(message):
    # Implementar lógica para inscrição, se necessário
    bot.reply_to(message, "Você foi inscrito com sucesso.")

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = (
        "/start - Inicia o bot\n"
        "/products - Mostra produtos recomendados\n"
        "/latest_products - Mostra produtos mais recentes\n"
        "/top_rated_products - Mostra produtos mais bem avaliados\n"
        "/search_product <keyword> - Pesquisa produtos por palavra-chave\n"
        "/product_details <product_id> - Mostra detalhes do produto\n"
        "/unsubscribe - Desinscreve-se de atualizações\n"
        "/subscribe - Inscreve-se para atualizações\n"
        "/status - Mostra o status do bot\n"
        "/update - Informa sobre atualizações futuras\n"
        "/autonomous_mode - Ativa o modo autônomo\n"
        "/manual_mode - Ativa o modo manual"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['status'])
def handle_status(message):
    mode = "autônomo" if autonomous_mode_enabled else "manual"
    bot.reply_to(message, f"O bot está no modo {mode}.")

@bot.message_handler(commands=['update'])
def handle_update(message):
    update_bot(message)

@bot.message_handler(commands=['autonomous_mode'])
def handle_autonomous_mode(message):
    switch_to_autonomous_mode(message)

@bot.message_handler(commands=['manual_mode'])
def handle_manual_mode(message):
    switch_to_manual_mode(message)

# Agendador para o modo autônomo
scheduler = BackgroundScheduler()
scheduler.add_job(autonomous_mode, 'interval', hours=1)
scheduler.start()

if __name__ == "__main__":
    bot.polling()
