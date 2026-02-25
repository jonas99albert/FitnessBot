"""
Garmin Client – Wrapper um garminconnect
Behandelt Session-Caching und den MFA-Email-Flow.
"""

import json
import logging
import pickle
from pathlib import Path
from datetime import date

try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectTooManyRequestsError,
    )
except ImportError:
    raise ImportError("Bitte installieren: pip install garminconnect")

log = logging.getLogger(__name__)

SESSION_FILE = Path("garmin_session.pkl")


class GarminClient:
    def __init__(self, email: str, password: str):
        self.email    = email
        self.password = password
        self._api: Garmin | None = None

    # ── Login ─────────────────────────────────────────────────────────────────
    def login(self) -> str:
        """
        Versucht Login. Gibt zurück:
          "ok"           – erfolgreich
          "mfa_required" – Garmin hat Code per E-Mail geschickt
          "error: ..."   – Fehler
        """
        # 1) Gespeicherte Session versuchen
        if SESSION_FILE.exists():
            log.info("Versuche gespeicherte Garmin-Session...")
            try:
                with open(SESSION_FILE, "rb") as f:
                    api = pickle.load(f)
                api.login()
                self._api = api
                log.info("Gespeicherte Session erfolgreich ✅")
                return "ok"
            except Exception as e:
                log.warning(f"Session ungültig, neu einloggen: {e}")
                SESSION_FILE.unlink(missing_ok=True)

        # 2) Frischer Login
        try:
            api = Garmin(self.email, self.password)
            api.login()
            self._api = api
            self._save_session()
            return "ok"

        except GarminConnectAuthenticationError as e:
            msg = str(e)
            # Garmin verlangt MFA-Code (Email-OTP)
            if "MFA" in msg or "needs_mfa" in msg.lower() or "NEEDS_MFA" in msg:
                log.info("MFA erforderlich")
                # api-Objekt für späteren MFA-Submit zwischenspeichern
                self._api = api
                return "mfa_required"
            return f"error: {msg}"

        except GarminConnectTooManyRequestsError:
            return "error: Zu viele Anfragen – bitte kurz warten."

        except Exception as e:
            # Garminconnect wirft manchmal Exception mit 'needs_mfa' im Text
            msg = str(e)
            if "mfa" in msg.lower() or "needs_mfa" in msg.lower():
                self._api = Garmin(self.email, self.password)
                return "mfa_required"
            return f"error: {msg}"

    def submit_mfa(self, code: str) -> str:
        """Sendet den MFA-Code an Garmin."""
        if not self._api:
            return "error: Kein Login-Objekt vorhanden"
        try:
            self._api.login(code)
            self._save_session()
            return "ok"
        except Exception as e:
            return f"error: {e}"

    def is_logged_in(self) -> bool:
        return self._api is not None

    def _save_session(self):
        try:
            with open(SESSION_FILE, "wb") as f:
                pickle.dump(self._api, f)
            log.info("Session gespeichert 💾")
        except Exception as e:
            log.warning(f"Session konnte nicht gespeichert werden: {e}")

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

        safe("steps",          self._api.get_steps_data,           d)
        safe("sleep",          self._api.get_sleep_data,           d)
        safe("hrv",            self._api.get_hrv_data,             d)
        safe("heart_rate",     self._api.get_heart_rates,          d)
        safe("stress",         self._api.get_stress_data,          d)
        safe("body_battery",   self._api.get_body_battery,         d)
        safe("activities",     self._api.get_activities_by_date,   d, d)
        safe("stats",          self._api.get_stats,                d)
        safe("respiration",    self._api.get_respiration_data,     d)
        safe("spo2",           self._api.get_spo2_data,            d)

        return data
