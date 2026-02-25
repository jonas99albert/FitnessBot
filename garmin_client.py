"""
Garmin Client – Wrapper um garminconnect (>= 0.2.x / garth-basiert)
Behandelt Session-Caching und den MFA-Email-Flow via Threading-Bridge.

Neuere garminconnect-Versionen nutzen garth und erwarten einen
prompt_mfa-Callback. Wir lösen das mit einem threading.Event,
das vom Telegram-Handler entsperrt wird.
"""

import logging
import threading
from pathlib import Path
from datetime import date

try:
    import garth
    from garminconnect import Garmin
except ImportError:
    raise ImportError("Bitte installieren: pip install garminconnect garth")

log = logging.getLogger(__name__)

SESSION_DIR = Path("garmin_tokens")   # garth speichert OAuth-Tokens als Dateien


class GarminClient:
    def __init__(self, email: str, password: str):
        self.email    = email
        self.password = password
        self._api: Garmin | None = None

        # Threading-Bridge für den MFA-Flow
        self._mfa_event = threading.Event()
        self._mfa_code: str | None = None
        self._login_result: str | None = None   # "ok" | "error: ..."
        self._login_thread: threading.Thread | None = None

    # ── Login ─────────────────────────────────────────────────────────────────
    def login(self) -> str:
        """
        Versucht Login. Rückgabewerte:
          "ok"           – sofort eingeloggt (gespeicherte Session)
          "mfa_required" – Login-Thread wartet auf MFA-Code
          "error: ..."   – Fehler
        """
        # 1) Gespeicherte garth-Session
        if SESSION_DIR.exists():
            log.info("Versuche gespeicherte Garmin-Session (garth)...")
            try:
                api = Garmin()
                api.login(tokenstore=str(SESSION_DIR))
                self._api = api
                log.info("Gespeicherte Session erfolgreich ✅")
                return "ok"
            except Exception as e:
                log.warning(f"Session abgelaufen oder ungültig: {e}")
                # Token-Ordner löschen damit frischer Login erfolgt
                import shutil
                shutil.rmtree(SESSION_DIR, ignore_errors=True)

        # 2) Frischer Login in separatem Thread
        #    (garminconnect.login() ist synchron-blockierend)
        self._mfa_event.clear()
        self._mfa_code = None
        self._login_result = None

        self._login_thread = threading.Thread(
            target=self._login_worker, daemon=True
        )
        self._login_thread.start()

        # Kurz warten: endet der Thread sofort ohne MFA → direkt fertig
        self._login_thread.join(timeout=8)

        if self._login_result == "ok":
            return "ok"
        elif self._login_result and self._login_result.startswith("error"):
            return self._login_result
        else:
            # Thread wartet noch → MFA benötigt
            return "mfa_required"

    def _login_worker(self):
        """Läuft im Hintergrund-Thread; wartet ggf. auf MFA-Code."""
        try:
            api = Garmin(self.email, self.password)
            # Direkt das Attribut auf dem internen garth-Client setzen
            # (funktioniert mit garth 0.4.x bis 0.5.x)
            api.garth.prompt_mfa = self._mfa_callback
            api.login()
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            api.garth.dump(str(SESSION_DIR))
            self._api = api
            self._login_result = "ok"
            log.info("Garmin Login erfolgreich ✅")
        except Exception as e:
            self._login_result = f"error: {e}"
            log.error(f"Garmin Login fehlgeschlagen: {e}")

    def _mfa_callback(self) -> str:
        """
        Wird von garminconnect aufgerufen wenn MFA nötig ist.
        Blockiert den Login-Thread bis submit_mfa() den Code liefert.
        """
        log.info("MFA-Callback aufgerufen – warte auf Code via Telegram...")
        self._mfa_event.wait(timeout=300)   # max 5 Minuten warten
        code = self._mfa_code or ""
        log.info(f"MFA-Code empfangen: {code}")
        return code

    def submit_mfa(self, code: str) -> str:
        """
        Übergibt den MFA-Code an den wartenden Login-Thread
        und wartet auf dessen Ergebnis.
        """
        self._mfa_code = code
        self._mfa_event.set()   # Login-Thread entsperren

        # Auf Ergebnis warten (max 15 Sek.)
        if self._login_thread:
            self._login_thread.join(timeout=15)

        return self._login_result or "error: Timeout beim Login"

    def is_logged_in(self) -> bool:
        return self._api is not None

    # ── Daten abrufen ─────────────────────────────────────────────────────────
    def fetch_all(self, target_date: date) -> dict:
        """Ruft alle relevanten Daten für ein Datum ab."""
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
