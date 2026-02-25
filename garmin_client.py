"""
Garmin Client – Wrapper um garminconnect 0.2.x (garth-basiert)
Behandelt Session-Caching und den MFA-Email-Flow via Threading-Bridge.

Aus dem garminconnect Source:
  self.garth.login(username, password, prompt_mfa=self.prompt_mfa)
→ prompt_mfa muss auf dem Garmin-Objekt selbst gesetzt werden.
"""

import logging
import shutil
import threading
from pathlib import Path
from datetime import date

try:
    from garminconnect import Garmin
except ImportError:
    raise ImportError("Bitte installieren: pip install garminconnect")

log = logging.getLogger(__name__)

SESSION_DIR = Path("garmin_tokens")


class GarminClient:
    def __init__(self, email: str, password: str):
        self.email    = email
        self.password = password
        self._api: Garmin | None = None

        # Threading-Bridge für den MFA-Flow
        self._mfa_event  = threading.Event()
        self._mfa_code: str | None  = None
        self._login_result: str | None = None
        self._login_thread: threading.Thread | None = None

    # ── Login ─────────────────────────────────────────────────────────────────
    def login(self) -> str:
        """
        Rückgabewerte:
          "ok"           – eingeloggt (Session oder frisch)
          "mfa_required" – Thread wartet auf Code via submit_mfa()
          "error: ..."   – Fehler
        """
        # 1) Gespeicherte Session laden
        if SESSION_DIR.exists():
            log.info("Versuche gespeicherte Garmin-Session...")
            try:
                api = Garmin(self.email, self.password)
                api.login(tokenstore=str(SESSION_DIR))
                self._api = api
                log.info("Gespeicherte Session OK ✅")
                return "ok"
            except Exception as e:
                log.warning(f"Session ungültig ({e}) – lösche und logge neu ein.")
                shutil.rmtree(SESSION_DIR, ignore_errors=True)

        # 2) Frischer Login in Thread (blockierend wegen MFA)
        self._mfa_event.clear()
        self._mfa_code   = None
        self._login_result = None

        self._login_thread = threading.Thread(target=self._login_worker, daemon=True)
        self._login_thread.start()

        # 8 Sekunden warten – wenn fertig ohne MFA direkt zurück
        self._login_thread.join(timeout=8)

        if self._login_result == "ok":
            return "ok"
        elif self._login_result and self._login_result.startswith("error"):
            return self._login_result
        else:
            # Thread wartet noch auf MFA-Code
            return "mfa_required"

    def _login_worker(self):
        """Läuft im Hintergrund-Thread."""
        try:
            api = Garmin(self.email, self.password)
            # Laut garminconnect-Source wird self.prompt_mfa direkt
            # an garth.login() weitergegeben – hier setzen:
            api.prompt_mfa = self._mfa_callback
            api.login()

            # Tokens für nächsten Start speichern
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            api.garth.dump(str(SESSION_DIR))

            self._api = api
            self._login_result = "ok"
            log.info("Garmin Login erfolgreich ✅")
        except Exception as e:
            self._login_result = f"error: {e}"
            log.error(f"Garmin Login fehlgeschlagen: {e}")

    def _mfa_callback(self) -> str:
        """Wird von garth aufgerufen – blockiert bis submit_mfa() den Code liefert."""
        log.info("MFA-Callback: warte auf Telegram-Code (max 5 Min.)...")
        self._mfa_event.wait(timeout=300)
        code = self._mfa_code or ""
        log.info(f"MFA-Code erhalten: {code}")
        return code

    def submit_mfa(self, code: str) -> str:
        """Telegram-Handler übergibt hier den Code."""
        self._mfa_code = code
        self._mfa_event.set()

        if self._login_thread:
            self._login_thread.join(timeout=20)

        return self._login_result or "error: Timeout beim Login"

    def is_logged_in(self) -> bool:
        return self._api is not None

    # ── Daten abrufen ─────────────────────────────────────────────────────────
    def fetch_all(self, target_date: date) -> dict:
        if not self._api:
            raise RuntimeError("Nicht eingeloggt!")

        d = target_date.isoformat()
        data = {"date": d}

        def safe(key, fn, *args, **kwargs):
            try:
                data[key] = fn(*args, **kwargs)
            except Exception as e:
                log.warning(f"Konnte {key} nicht abrufen: {e}")
                data[key] = None

        safe("steps",        self._api.get_steps_data,         d)
        safe("sleep",        self._api.get_sleep_data,         d)
        safe("hrv",          self._api.get_hrv_data,           d)
        safe("heart_rate",   self._api.get_heart_rates,        d)
        safe("stress",       self._api.get_stress_data,        d)
        safe("body_battery", self._api.get_body_battery,       d)
        safe("activities",   self._api.get_activities_by_date, d, d)
        safe("stats",        self._api.get_stats,              d)
        safe("respiration",  self._api.get_respiration_data,   d)
        safe("spo2",         self._api.get_spo2_data,          d)

        return data
