# WaSenderAPI integration for WhatsApp messaging
import os
import requests
from datetime import datetime

WASENDER_API_KEY = os.environ.get("WASENDER_API_KEY")

def send_whatsapp_alert(to_phone_number: str, title: str, category: str, summary: str, news_url: str, published_time: datetime) -> bool:
    """
    Send formatted WhatsApp alert message to user via WaSenderAPI
    
    Format:
    🚨 GEOECO NEWS
    📈 [CATEGORIA] | [NIVEL_IMPACTO]
    [TÍTULO]
    💬 [Resumo]
    🔗 [Link]
    ⏰ [Horário]
    """
    
    if not WASENDER_API_KEY:
        print("WaSenderAPI credentials not configured")
        return False
    
    try:
        # Format the message according to specifications
        category_icons = {
            "economy": "📈",
            "geopolitics": "🌍", 
            "markets": "💰"
        }
        
        icon = category_icons.get(category.lower(), "📈")
        
        # Validate and format phone number using our validation function
        try:
            formatted_number = validate_brazilian_phone(to_phone_number)
        except ValueError as e:
            print(f"Invalid phone number format: {to_phone_number} - {e}")
            return False
        
        dashboard_url = os.environ.get('REPLIT_DEV_DOMAIN', 'localhost:5000')
        
        message_body = f"""🚨 GEOECO NEWS

{icon} {category.upper()} | ALTO IMPACTO
{title.upper()}

💬 {summary}

🔗 {news_url}
⏰ {published_time.strftime('%d/%m/%Y %H:%M')}

---
⚙️ Configurar alertas: https://{dashboard_url}/settings"""

        # Send via WaSenderAPI
        response = requests.post(
            'https://wasenderapi.com/api/send-message',
            headers={'Authorization': f'Bearer {WASENDER_API_KEY}'},
            json={'to': formatted_number, 'text': message_body},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"WhatsApp message sent via WaSenderAPI to {formatted_number}")
            return True
        else:
            print(f"Error sending WhatsApp: {response.status_code} - {response.text}")
            return False
        
    except Exception as e:
        print(f"Error sending WhatsApp message: {str(e)}")
        return False

def validate_brazilian_phone(phone_number: str) -> str:
    """
    Validate and format Brazilian mobile phone number for WhatsApp
    Expected format: 5551999999999 (55 + DDD + 9 + 8 digits)
    """
    import re
    
    # Remove all non-numeric characters
    clean_phone = re.sub(r'\D', '', phone_number)
    
    # Add country code if missing and number looks like Brazilian mobile
    if len(clean_phone) == 11 and clean_phone[2] == '9':
        # 11 digits starting with DDD + 9 (mobile format)
        clean_phone = f"55{clean_phone}"
    elif len(clean_phone) == 10:
        # 10 digits - add country code and mobile digit 9
        area_code = clean_phone[:2]
        number = clean_phone[2:]
        clean_phone = f"55{area_code}9{number}"
    
    # Validate exact mobile format: 55 + DDD (11-99) + 9 + 8 digits = 13 digits total
    if not re.match(r'^55[1-9][0-9]9[0-9]{8}$', clean_phone):
        raise ValueError("Formato inválido. Use: 5551999999999 (55 + DDD + 9 + 8 dígitos)")
    
    return clean_phone