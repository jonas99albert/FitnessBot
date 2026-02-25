# 🏋️ Garmin Fitness Coach – Telegram Bot

Jeden Morgen analysiert der Bot deine Garmin-Daten der letzten Nacht und schickt dir einen personalisierten Coaching-Bericht.

---

## 📊 Was der Bot analysiert

| Metrik | Was wird geprüft |
|--------|-----------------|
| 😴 Schlaf | Dauer, Tiefschlaf, REM, Schlaf-Score |
| ❤️ HRV | Letzten Nacht vs. 7-Tage-Schnitt |
| ⚡ Body Battery | Aktueller Stand, Min/Max |
| 🧘 Stress | Ø Stresslevel des Vortages |
| 🚶 Schritte | Tagesziel-Fortschritt |
| 🚴 Training | Alle Aktivitäten mit Dauer, Distanz, Kalorien |
| 💓 Herzfrequenz | Ruhepuls, Max/Min |
| 🫁 SpO2 | Sauerstoffsättigung |

Am Ende gibt's eine **Coach-Empfehlung**: Regeneration, lockeres Training oder volles Programm – je nach Erholungsstatus.

---

## 🚀 Setup

### 1. Bot installieren
```bash
git clone / Dateien kopieren
pip install -r requirements.txt
```

### 2. config.json ausfüllen
```json
{
  "telegram_token": "DEIN_TELEGRAM_BOT_TOKEN",
  "telegram_user_id": "DEINE_TELEGRAM_USER_ID",
  "garmin_email": "deine@email.com",
  "garmin_password": "dein_garmin_passwort",
  "morning_hour": 7,
  "morning_minute": 0,
  "timezone": "Europe/Vienna"
}
```

**Telegram Bot Token:** @BotFather → `/newbot`  
**Telegram User-ID:** @userinfobot anschreiben

### 3. Bot starten
```bash
python bot.py
```

---

## 🔐 Garmin MFA – Email-Bestätigung

Garmin schickt manchmal einen Bestätigungscode per E-Mail wenn ein neues Gerät/IP sich anmeldet.

**Der Bot behandelt das automatisch:**

1. Bot erkennt die MFA-Anforderung
2. Telegram-Nachricht: *"Bitte antworte mit /mfa DEIN_CODE"*
3. Du öffnest deine E-Mail, kopierst den Code
4. Sendest `/mfa 123456` im Telegram-Chat
5. Bot loggt sich ein und holt sofort deinen Report

**Die Session wird lokal gespeichert** (`garmin_session.pkl`) – du musst das nur einmal machen. Danach läuft alles automatisch.

---

## 📱 Telegram-Befehle

| Befehl | Funktion |
|--------|----------|
| `/report` | Sofortiger Report für gestern |
| `/today` | Heutige Daten (live) |
| `/status` | Bot & Garmin-Status anzeigen |
| `/mfa CODE` | Garmin MFA-Code eingeben |
| `/time 06:30` | Morgen-Report-Zeit ändern |
| `/setup` | Konfiguration anzeigen |

---

## 🖥️ Als Hintergrundprozess (Linux/Raspberry Pi)

```bash
# Mit nohup
nohup python bot.py > bot.log 2>&1 &

# Oder als systemd Service (empfohlen):
# /etc/systemd/system/garmin-coach.service
[Unit]
Description=Garmin Fitness Coach Bot
After=network.target

[Service]
WorkingDirectory=/home/pi/garmin_coach_bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable garmin-coach
sudo systemctl start garmin-coach
```

---

## 📁 Dateistruktur

```
garmin_coach_bot/
├── bot.py              ← Telegram Bot + Scheduler
├── garmin_client.py    ← Garmin API + MFA-Handling
├── analyzer.py         ← Daten-Analyse + Report-Erstellung
├── config.json         ← Konfiguration
├── requirements.txt    ← Python-Dependencies
├── garmin_session.pkl  ← Gespeicherte Garmin-Session (auto)
└── bot.log             ← Logfile (auto)
```
