"""
Fitness Bahia Expo 2026 — WhatsApp Bot (Evolution API)
Stateless command-driven bot with follow-up scheduling.
"""

import os
import time
import json
import logging
from datetime import datetime

import requests
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

# ──────────────────────────────────────────────
# Configuration (Environment Variables)
# ──────────────────────────────────────────────
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "")       # e.g. https://evo.yourdomain.com
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")       # Global or instance API key
INSTANCE = os.getenv("INSTANCE", "")                         # Instance name on Evolution API

PORT = int(os.getenv("PORT", 5000))
FOLLOWUP_DELAY = int(os.getenv("FOLLOWUP_DELAY", 600))      # seconds (default 10 min)

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("fitness-bot")

# ──────────────────────────────────────────────
# Flask + Scheduler
# ──────────────────────────────────────────────
app = Flask(__name__)

scheduler = BackgroundScheduler(daemon=True)
_scheduler_started = False

# Track greeted users (in-memory)
greeted_users: set = set()


def _ensure_scheduler():
    """Start the scheduler lazily (safe for Gunicorn fork)."""
    global _scheduler_started
    if not _scheduler_started:
        scheduler.start()
        _scheduler_started = True
        log.info("⏱ Scheduler started")


# ══════════════════════════════════════════════
#  MESSAGE CONTENT
# ══════════════════════════════════════════════

GREETING = (
    "Olá! 👋 Seja bem-vindo(a) à Fitness Bahia Expo 2026! 🏋️\n\n"
    "Para te atender mais rápido e direcionar para o setor certo, me conta: qual é o seu interesse?\n\n"
    "Digite o número da opção 👇\n\n"
    "1️⃣ Quero ser um expositor (stands)\n"
    "2️⃣ Quero garantir minha vaga no workshops\n"
    "3️⃣ Quero participar do concurso Garota & Garoto Fitness Bahia Expo 👑\n"
    "4️⃣ Tenho dúvidas gerais sobre o evento\n"
    "5️⃣ Quero ser um apoiador / parceiro do evento 🤝\n\n"
    "Assim que você responder, já te encaminho com o time responsável 😉"
)

FALLBACK = (
    "Desculpe, não entendi 😅\n"
    "Por favor, digite um número de 1 a 5 para que eu possa te ajudar:\n\n"
    "1️⃣ Expositor (stands)\n"
    "2️⃣ Workshops\n"
    "3️⃣ Concurso Garota & Garoto 👑\n"
    "4️⃣ Dúvidas gerais\n"
    "5️⃣ Apoiador / Parceiro 🤝"
)

# ── Option 1 — Expositor ──
OPTION_1 = [
    (
        "Que massa ter você por aqui! 🔥\n\n"
        "Se você tá pensando em expor, já te adianto: a Fitness Bahia Expo é uma oportunidade "
        "muito forte pra quem quer mostrar a marca, fazer conexão e gerar negócios de verdade na região.\n\n"
        "Os espaços são limitados, e os melhores pontos já estão sendo garantidos.\n\n"
        "Me chama aqui, que eu te explico direitinho como funciona, e vejo contigo o que faz mais "
        "sentido para sua marca:\n\n"
        "👉 Bruna: https://wa.link/suyjny\n\n"
        "Sem pressão, tá? Se fizer sentido pra você, já conseguimos ver a melhor posição para sua "
        "marca dentro do evento."
    ),
]

OPTION_1_FOLLOWUP = "Garantiu seu Stand na Fitness Bahia Expo 2026? Ficou com alguma dúvida?"

# ── Option 2 — Workshops ──
OPTION_2 = [
    (
        "Ótima escolha!\n\n"
        "Os workshops da Fitness Bahia Expo 2026 são pensados para quem quer crescer profissionalmente, "
        "se atualizar e se conectar com grandes nomes do mercado.\n\n"
        "Eles acontecem no dia 18/04, durante todo o dia e a noite também.\n\n"
        "As VAGAS SÃO LIMITADAS. E vale lembrar que profissionais cadastrados no CREF têm 20% de "
        "desconto na inscrição.\n\n"
        "Compre pelo site:\n"
        "https://www.sympla.com.br/evento/fitness-bahia-expo/3278103?referrer=www.google.com"
        "&referrer=www.google.com&referrer=www.google.com&referrer=www.google.com&share_id=copiarlink\n\n"
        "Ou fale com um de nossos vendedores, vamos te ajudar a garantir a sua vaga:\n"
        "👉 Oséas Augusto: 73 9975-2416 | André Quebranca: 73 9953-0217"
    ),
]

OPTION_2_FOLLOWUP = "Conseguiu finalizar sua inscrição nos Workshops da Fitness Bahia Expo 2026? Ficou com alguma dúvida?"

# ── Option 3 — Concurso ──
OPTION_3 = [
    (
        "Que decisão!\n\n"
        "O concurso Garota & Garoto Fitness Bahia Expo 2026 é uma oportunidade de visibilidade, "
        "posicionamento e reconhecimento dentro do cenário fitness da região.\n\n"
        "Importante deixar claro:\n"
        "❌ Não é um campeonato de fisiculturismo.\n"
        "❌ Não será avaliada muscularidade extrema.\n\n"
        "Nosso objetivo é valorizar o lifestyle fitness, a estética saudável e a presença de palco.\n\n"
        "Muita gente entra sem noção do quanto isso pode abrir portas depois."
    ),
    (
        "CRITÉRIOS DE AVALIAÇÃO:\n\n"
        "✅ Beleza geral: cabelo, maquiagem (no caso das mulheres), harmonia física e apresentação.\n"
        "✅ Desfile: comunicação corporal, postura, elegância, desenvoltura na passarela.\n"
        "✅ Presença de palco: representatividade, confiança, atitude e energia.\n"
        "✅ Simpatia: conexão com o público e carisma.\n\n"
        "Queremos pessoas que representem o universo fitness com autenticidade, confiança e leveza.\n\n"
        "Se você vive um estilo de vida saudável, gosta de se cuidar e tem presença… este palco pode ser seu. "
        "E sabe qual a melhor parte?"
    ),
    (
        "AS PREMIAÇÕES:\n\n"
        "🥇 1º lugar: 1.000 REAIS + KIT SUPLEMENTO\n"
        "🥈 2º lugar: CONSULTORIA + KIT SUPLEMENTO\n"
        "🥉 3º lugar: KIT SUPLEMENTOS"
    ),
    (
        "🚨 VAGAS ABERTAS 🚨\n\n"
        "👉 Garanta sua participação agora:\n"
        "https://docs.google.com/forms/d/e/1FAIpQLSdHEgXhI5C1yzirKwHc8upZrE_RMMvF58LyWDjye7HiHwRu5g/"
        "viewform?usp=header\n\n"
        "Esse é o seu momento!"
    ),
]

OPTION_3_FOLLOWUP = (
    "Conseguiu finalizar sua inscrição no Concurso Garota & Garoto Fitness Bahia Expo 2026? "
    "Ficou com alguma dúvida?"
)

# ── Option 4 — Dúvidas Gerais ──
OPTION_4 = [
    (
        "Claro! 😊\n\n"
        "A Fitness Bahia Expo 2026 acontece nos dias 17, 18 e 19 de abril, em Teixeira de Freitas, "
        "reunindo empresas, profissionais e grandes nomes do mercado fitness, saúde e beleza.\n\n"
        "Pode me falar a sua dúvida sobre o evento por aqui. Olha o exemplo:\n\n"
        "📌 PROGRAMAÇÃO: O que vai acontecer em cada dia? Quais dias são gratuitos?\n"
        "📌 WORKSHOPS: Eles vão acontecer somente dia 18/04?\n"
        "📌 PALESTRAS E PALESTRANTES: As palestras serão gratuitas? Quais são os palestrantes que irão "
        "marcar presença e em quais os dias?\n\n"
        "Me conta: o que você quer saber exatamente?"
    ),
]

# ── Option 5 — Parceiro / Apoiador ──
OPTION_5 = [
    (
        "Excelente escolha! 🤝\n\n"
        "Se conectar como parceiro da Fitness Bahia Expo 2026 vai abrir os horizontes da sua marca, "
        "gerar autoridade e se associar a um dos maiores movimentos do setor na região.\n\n"
        "Me diz aqui, como você quer apoiar o evento e vemos juntos o melhor encaixe para sua marca:\n\n"
        "👉 Bruna: https://wa.link/suyjny\n\n"
        "Esse tipo de conexão, quando bem feita, gera resultado de verdade 😉"
    ),
]

# Global option map
OPTIONS = {
    "1": OPTION_1,
    "2": OPTION_2,
    "3": OPTION_3,
    "4": OPTION_4,
    "5": OPTION_5,
}


# ══════════════════════════════════════════════
#  EVOLUTION API — SEND FUNCTION
# ══════════════════════════════════════════════

def send_presence(remote_jid, presence="composing"):
    """
    Send typing presence via Evolution API to simulate human typing.
    """
    if not EVOLUTION_API_URL or not INSTANCE:
        return

    number = remote_jid.replace("@s.whatsapp.net", "").strip()
    url = f"{EVOLUTION_API_URL.rstrip('/')}/chat/sendPresence/{INSTANCE}"
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY,
    }
    payload = {
        "number": number,
        "delay": 3000,
        "presence": presence,
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=5)
    except Exception as exc:
        log.error(f"Failed to send presence: {exc}")

def send_text(remote_jid, text):
    """
    Send a text message via Evolution API.
    POST {EVOLUTION_API_URL}/message/sendText/{INSTANCE}

    Accepts either a raw phone number (5573999999999)
    or a full JID (5573999999999@s.whatsapp.net).
    """
    if not EVOLUTION_API_URL or not INSTANCE:
        log.warning("EVOLUTION_API_URL or INSTANCE not set — DRY RUN")
        log.info(f"  [DRY-RUN] → {remote_jid}: {text[:100]}…")
        return False

    # Normalise: always send the raw number (without @s.whatsapp.net)
    number = remote_jid.replace("@s.whatsapp.net", "").strip()

    url = f"{EVOLUTION_API_URL.rstrip('/')}/message/sendText/{INSTANCE}"
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY,
    }
    payload = {
        "number": number,
        "text": text,
        "options": {
            "linkPreview": False
        }
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        log.info(f"✓ Sent to {number} ({len(text)} chars)")
        return True
    except requests.RequestException as exc:
        log.error(f"✗ Failed → {number}: {exc}")
        return False


def send_sequence(remote_jid, messages, is_delayed=False, gap=1.5):
    """Send multiple messages in order with a small delay between each."""
    if is_delayed:
        # Simulate typing for 3 seconds before sending the message sequence
        send_presence(remote_jid, "composing")
        time.sleep(3)

    for i, msg in enumerate(messages):
        if i > 0:
            time.sleep(gap)
        send_text(remote_jid, msg)


# ══════════════════════════════════════════════
#  FOLLOW-UP SCHEDULER
# ══════════════════════════════════════════════

def cancel_followup(remote_jid):
    """Cancel a pending follow-up job for a user if they reply."""
    _ensure_scheduler()
    job_id = f"followup_{remote_jid}"
    existing = scheduler.get_job(job_id)
    if existing:
        existing.remove()
        log.info(f"🚫 Canceled pending follow-up for {remote_jid} due to user interaction")

def schedule_followup(remote_jid, text, delay=FOLLOWUP_DELAY):
    """Schedule a delayed follow-up. Replaces any pending one for the same user."""
    _ensure_scheduler()
    job_id = f"followup_{remote_jid}"

    existing = scheduler.get_job(job_id)
    if existing:
        existing.remove()
        log.info(f"↻ Replaced pending follow-up for {remote_jid}")

    from datetime import timedelta
    run_at = datetime.now() + timedelta(seconds=delay)

    scheduler.add_job(
        send_text,
        trigger="date",
        run_date=run_at,
        args=[remote_jid, text],
        id=job_id,
        replace_existing=True,
    )
    log.info(f"⏱ Follow-up scheduled for {remote_jid} in {delay}s")


# ══════════════════════════════════════════════
#  CORE MESSAGE HANDLER (STATELESS)
# ══════════════════════════════════════════════

def bg_process_message(remote_jid, cleaned):
    """
    Process message in background to avoid blocking the webhook worker.
    """
    # ── Global numeric command ──
    if cleaned in OPTIONS:
        # Options 1 and 5 invoke the typing delay
        is_delayed = (cleaned in ["1", "5"])
        
        # Append the support message to the chosen sequence
        sequence = list(OPTIONS[cleaned])
        sequence.append("Nosso time de suporte entrará em contato com você em breve para dar continuidade ao seu atendimento. Fique de olho no seu WhatsApp! 😉")
        
        send_sequence(remote_jid, sequence, is_delayed=is_delayed)

        if cleaned == "1":
            schedule_followup(remote_jid, OPTION_1_FOLLOWUP)
        elif cleaned == "2":
            schedule_followup(remote_jid, OPTION_2_FOLLOWUP)
        elif cleaned == "3":
            schedule_followup(remote_jid, OPTION_3_FOLLOWUP)

        greeted_users.add(remote_jid)
        log.info(f"Option [{cleaned}] served → state reset")
        return

    # ── Non-numeric: greeting or fallback ──
    if remote_jid not in greeted_users:
        send_text(remote_jid, GREETING)
        greeted_users.add(remote_jid)
        log.info(f"Greeting sent → {remote_jid}")
    else:
        send_text(remote_jid, FALLBACK)
        log.info(f"Fallback menu re-sent → {remote_jid}")


def handle_message(remote_jid, text):
    """
    Stateless handler:
      • Cancels any pending follow-up jobs immediately.
      • Schedules the background processing so webhook can return 200 OK instantly.
    """
    cleaned = text.strip()
    log.info(f"← {remote_jid}: {cleaned}")
    
    # Cancel any followups since the user replied
    cancel_followup(remote_jid)
    
    # Delegate to background thread
    scheduler.add_job(bg_process_message, args=[remote_jid, cleaned])


# ══════════════════════════════════════════════
#  WEBHOOK PAYLOAD PARSER (EVOLUTION API)
# ══════════════════════════════════════════════

def parse_evolution_payload(data):
    """
    Extract (remoteJid, text) from an Evolution API webhook event.

    Expected payload (messages.upsert):
    {
      "event": "messages.upsert",
      "instance": "...",
      "data": {
        "key": {
          "remoteJid": "5573999999999@s.whatsapp.net",
          "fromMe": false
        },
        "message": {
          "conversation": "user text here"
          // or "extendedTextMessage": { "text": "..." }
        },
        "messageType": "conversation"
      }
    }
    """
    try:
        # Skip messages sent by the bot itself
        key = data.get("data", {}).get("key", {})
        if key.get("fromMe", False):
            return None, None

        remote_jid = key.get("remoteJid", "")

        # Skip group messages — only handle personal chats
        if not remote_jid or "@g.us" in remote_jid:
            return None, None

        # Extract text from possible message structures
        message = data.get("data", {}).get("message", {})
        text = (
            message.get("conversation")
            or message.get("extendedTextMessage", {}).get("text")
            or ""
        )

        if not text:
            return None, None

        return remote_jid, text

    except Exception as exc:
        log.error(f"Payload parse error: {exc}")
        return None, None


# ══════════════════════════════════════════════
#  FLASK ROUTES
# ══════════════════════════════════════════════

@app.before_request
def _startup():
    """Ensure scheduler is running (safe for Gunicorn workers)."""
    _ensure_scheduler()


@app.route("/", methods=["GET"])
def health():
    """Health-check for Railway."""
    return jsonify({
        "status": "running",
        "service": "Fitness Bahia Expo 2026 — WhatsApp Bot",
        "instance": INSTANCE,
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Receive Evolution API webhook events.
    Only processes 'messages.upsert' events with text content.
    """
    data = request.get_json(silent=True) or {}

    event = data.get("event", "")
    log.debug(f"Event received: {event}")

    # Only care about incoming messages
    if event != "messages.upsert":
        return jsonify({"status": "ignored", "reason": f"event={event}"}), 200

    remote_jid, text = parse_evolution_payload(data)

    if remote_jid and text:
        handle_message(remote_jid, text)
        return jsonify({"status": "processed"}), 200

    return jsonify({"status": "skipped"}), 200


# ══════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════

if __name__ == "__main__":
    _ensure_scheduler()
    log.info(f"🚀 Bot starting | instance={INSTANCE} | port={PORT}")
    from waitress import serve
    serve(app, host="0.0.0.0", port=PORT)
