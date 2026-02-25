"""
Garmin Fitness Coach - Telegram Bot
Analysiert täglich deine Garmin-Daten und sendet einen personalisierten Coach-Bericht.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

from garmin_client import GarminClient
from analyzer import FitnessAnalyzer

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
CONFIG_FILE = Path("config.json")

def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

cfg = load_config()

TELEGRAM_TOKEN   = cfg.get("telegram_token")   or os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_USER_ID = cfg.get("telegram_user_id") or os.getenv("TELEGRAM_USER_ID", "")
GARMIN_EMAIL     = cfg.get("garmin_email")     or os.getenv("GARMIN_EMAIL", "")
GARMIN_PASSWORD  = cfg.get("garmin_password")  or os.getenv("GARMIN_PASSWORD", "")
MORNING_HOUR     = int(cfg.get("morning_hour", 7))
MORNING_MINUTE   = int(cfg.get("morning_minute", 0))
TIMEZONE         = cfg.get("timezone", "Europe/Vienna")

# Global state für MFA-Flow
mfa_pending: dict = {}   # user_id -> GarminClient waiting for code
garmin_client: GarminClient | None = None
scheduler: AsyncIOScheduler | None = None


# ─── Garmin Connect ───────────────────────────────────────────────────────────
async def ensure_garmin(app: Application) -> GarminClient | None:
    global garmin_client
    if garmin_client and garmin_client.is_logged_in():
        return garmin_client

    log.info("Garmin-Session abgelaufen oder nicht vorhanden, versuche Login...")
    client = GarminClient(GARMIN_EMAIL, GARMIN_PASSWORD)
    
    result = client.login()

    if result == "mfa_required":
        log.info("Garmin verlangt MFA-Code – sende Prompt an Telegram-User")
        mfa_pending[TELEGRAM_USER_ID] = client
        await app.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=(
                "🔐 *Garmin Login – Code benötigt*\n\n"
                "Garmin hat dir einen Bestätigungscode per E-Mail geschickt.\n"
                "Bitte antworte mit:\n`/mfa DEIN_CODE`"
            ),
            parse_mode="Markdown"
        )
        return None
    elif result == "ok":
        garmin_client = client
        log.info("Garmin Login erfolgreich ✅")
        return garmin_client
    else:
        log.error(f"Garmin Login fehlgeschlagen: {result}")
        await app.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=f"❌ Garmin Login fehlgeschlagen: `{result}`",
            parse_mode="Markdown"
        )
        return None


# ─── Morning Report ───────────────────────────────────────────────────────────
async def send_morning_report(app: Application):
    log.info("⏰ Morgendlicher Report wird erstellt...")

    client = await ensure_garmin(app)
    if not client:
        return

    today = date.today()
    yesterday = today - timedelta(days=1)

    try:
        data = client.fetch_all(yesterday)
    except Exception as e:
        log.error(f"Fehler beim Abrufen der Garmin-Daten: {e}")
        await app.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=f"⚠️ Garmin-Daten konnten nicht abgerufen werden:\n`{e}`",
            parse_mode="Markdown"
        )
        return

    report = FitnessAnalyzer.build_report(data, yesterday)

    await app.bot.send_message(
        chat_id=TELEGRAM_USER_ID,
        text=report,
        parse_mode="Markdown"
    )
    log.info("✅ Morgendlicher Report gesendet.")


# ─── Command Handlers ─────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Garmin Fitness Coach* hier!\n\n"
        "Ich analysiere täglich deine Garmin-Daten und schicke dir morgens einen personalisierten Bericht.\n\n"
        "📋 *Befehle:*\n"
        "`/report` – Sofortiger Report für gestern\n"
        "`/today` – Heutige Daten (soweit verfügbar)\n"
        "`/status` – Bot & Garmin Status\n"
        "`/mfa CODE` – MFA-Code nach Garmin-Login eingeben\n"
        "`/time HH:MM` – Sendezeit ändern (z.B. `/time 06:30`)\n"
        "`/setup` – Konfiguration anzeigen",
        parse_mode="Markdown"
    )


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Rufe Garmin-Daten ab...")
    await send_morning_report(ctx.application)


async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Lade heutige Daten...")
    client = await ensure_garmin(ctx.application)
    if not client:
        return

    try:
        data = client.fetch_all(date.today())
        report = FitnessAnalyzer.build_report(data, date.today(), title="📊 Heutige Daten (live)")
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: `{e}`", parse_mode="Markdown")


async def cmd_mfa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Empfängt den Garmin MFA-Code per Telegram."""
    global garmin_client

    user_id = str(update.effective_user.id)

    if user_id not in mfa_pending:
        await update.message.reply_text("ℹ️ Kein MFA-Login ausstehend.")
        return

    if not ctx.args:
        await update.message.reply_text("⚠️ Bitte Code angeben: `/mfa 123456`", parse_mode="Markdown")
        return

    code = ctx.args[0].strip()
    client = mfa_pending.pop(user_id)

    result = client.submit_mfa(code)
    if result == "ok":
        garmin_client = client
        await update.message.reply_text("✅ Garmin Login erfolgreich! Ich hole jetzt deinen Report...")
        await send_morning_report(ctx.application)
    else:
        await update.message.reply_text(f"❌ MFA fehlgeschlagen: `{result}`", parse_mode="Markdown")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global garmin_client
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    next_run = scheduler.get_job("morning_report")
    next_str = next_run.next_run_time.strftime("%d.%m.%Y %H:%M") if next_run else "unbekannt"

    garmin_ok = "✅ Eingeloggt" if (garmin_client and garmin_client.is_logged_in()) else "❌ Nicht eingeloggt"

    await update.message.reply_text(
        f"*🤖 Bot Status*\n\n"
        f"🕐 Aktuelle Zeit: `{now.strftime('%d.%m.%Y %H:%M')} {TIMEZONE}`\n"
        f"📡 Garmin: {garmin_ok}\n"
        f"📧 Garmin-Account: `{GARMIN_EMAIL}`\n"
        f"⏰ Nächster Report: `{next_str}`\n",
        parse_mode="Markdown"
    )


async def cmd_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global MORNING_HOUR, MORNING_MINUTE
    if not ctx.args:
        await update.message.reply_text("⚠️ Verwendung: `/time 06:30`", parse_mode="Markdown")
        return

    try:
        parts = ctx.args[0].split(":")
        h, m = int(parts[0]), int(parts[1])
        MORNING_HOUR, MORNING_MINUTE = h, m

        cfg["morning_hour"] = h
        cfg["morning_minute"] = m
        save_config(cfg)

        # Scheduler updaten
        scheduler.reschedule_job(
            "morning_report",
            trigger="cron",
            hour=h,
            minute=m,
            timezone=TIMEZONE
        )
        await update.message.reply_text(f"✅ Report-Zeit auf `{h:02d}:{m:02d}` gesetzt.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Ungültiges Format: `{e}`", parse_mode="Markdown")


async def cmd_setup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"*⚙️ Konfiguration*\n\n"
        f"📧 Garmin: `{GARMIN_EMAIL}`\n"
        f"⏰ Report-Zeit: `{MORNING_HOUR:02d}:{MORNING_MINUTE:02d}` ({TIMEZONE})\n"
        f"🆔 Telegram User-ID: `{TELEGRAM_USER_ID}`\n\n"
        f"Einstellungen in `config.json` änderbar.",
        parse_mode="Markdown"
    )


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    global scheduler

    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN fehlt! Bitte in config.json oder als Umgebungsvariable setzen.")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handler registrieren
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("today",  cmd_today))
    app.add_handler(CommandHandler("mfa",    cmd_mfa))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("time",   cmd_time))
    app.add_handler(CommandHandler("setup",  cmd_setup))

    # Scheduler
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        send_morning_report,
        trigger="cron",
        hour=MORNING_HOUR,
        minute=MORNING_MINUTE,
        id="morning_report",
        args=[app]
    )
    scheduler.start()

    log.info(f"🚀 Bot gestartet | Report täglich um {MORNING_HOUR:02d}:{MORNING_MINUTE:02d} {TIMEZONE}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
