import os
import json
import requests
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# WhatsApp API configuration
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
WHATSAPP_API_URL = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

# LLM API configuration
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.together.xyz/v1/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

# Admin user for web login
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", generate_password_hash("changeme"))


# Simple user class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    if user_id == '1':
        return User(1, ADMIN_USERNAME)
    return None


# Web interface routes
@app.route('/')
@login_required
def index():
    """Dashboard page (requires login)"""
    return render_template('index.html',
                           phone_id=WHATSAPP_PHONE_NUMBER_ID,
                           webhook_token=WHATSAPP_WEBHOOK_VERIFY_TOKEN)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            user = User(1, username)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Logout route"""
    logout_user()
    return redirect(url_for('login'))


# API routes
@app.route("/api/status")
@login_required
def api_status():
    """API status endpoint"""
    return jsonify({
        "status": "online",
        "version": "1.0.0"
    })


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    """Handle WhatsApp webhook requests"""
    # Handle GET request (webhook verification)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode and token:
            if mode == "subscribe" and token == WHATSAPP_WEBHOOK_VERIFY_TOKEN:
                print("Webhook verified")
                return challenge, 200

        return "Verification failed", 403

    # Handle POST request (incoming messages)
    elif request.method == "POST":
        data = request.get_json()

        # Verify this is a WhatsApp message
        if not data.get('object') or not data.get('entry'):
            return jsonify({"error": "Invalid request"}), 400

        try:
            for entry in data["entry"]:
                for change in entry.get("changes", []):
                    if change.get("value") and change["value"].get("messages"):
                        for message in change["value"]["messages"]:
                            if message.get("type") == "text":
                                # Extract message information
                                sender_id = message["from"]
                                message_body = message["text"]["body"]

                                # Check if the message is from a group
                                is_group = False
                                if "context" in message and message["context"].get("from") is not None:
                                    is_group = True

                                # Check if bot is mentioned or the message is direct
                                bot_mentioned = "@bot" in message_body.lower() or not is_group

                                if bot_mentioned:
                                    # Clean up the message (remove bot mention if present)
                                    clean_message = message_body.lower().replace("@bot", "").strip()

                                    # Process with LLM
                                    llm_response = generate_llm_response(clean_message)

                                    # Send response back to WhatsApp
                                    send_whatsapp_message(sender_id, llm_response)

            return jsonify({"status": "success"}), 200
        except Exception as e:
            print(f"Error processing message: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500


def generate_llm_response(prompt):
    """Generate a response using an external LLM API"""
    try:
        # Using Together.ai API (could be replaced with any LLM API)
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "meta-llama/Llama-3-8b-chat-hf",
            "prompt": f"<s>[INST] {prompt} [/INST]",
            "max_tokens": 500,
            "temperature": 0.7,
            "top_p": 0.9
        }

        response = requests.post(
            LLM_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            return result.get("choices", [{}])[0].get("text", "I couldn't generate a response.")
        else:
            print(f"API error: {response.status_code} - {response.text}")
            return "I'm having trouble connecting to my brain. Please try again later."
    except Exception as e:
        print(f"Error generating LLM response: {e}")
        return "Sorry, I'm having trouble thinking right now. Please try again later."


def send_whatsapp_message(recipient_id, message):
    """Send a message via WhatsApp API"""
    headers = {
        "Authorization": f"Bearer {WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_id,
        "type": "text",
        "text": {
            "body": message
        }
    }

    try:
        response = requests.post(
            WHATSAPP_API_URL,
            headers=headers,
            data=json.dumps(payload)
        )

        return response.json()
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        return None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))