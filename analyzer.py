"""
FitnessAnalyzer – bereitet Garmin-Rohdaten auf und lässt Claude den Coaching-Bericht schreiben.
"""

import logging
import os
import json
from datetime import date

try:
    import anthropic
except ImportError:
    raise ImportError("Bitte installieren: pip install anthropic")

log = logging.getLogger(__name__)


class FitnessAnalyzer:

    @staticmethod
    def build_report(data: dict, report_date: date, title: str = None) -> str:
        """Aufbereitete Daten → Claude → persönlicher Coach-Bericht."""
        summary = FitnessAnalyzer._extract_summary(data, report_date)

        try:
            report = FitnessAnalyzer._ask_claude(summary, report_date, title)
            return report
        except Exception as e:
            log.error(f"Claude API Fehler: {e} – Fallback auf einfachen Report")
            return FitnessAnalyzer._simple_report(summary, report_date, title)

    # ── Daten aufbereiten ─────────────────────────────────────────────────────
    @staticmethod
    def _extract_summary(data: dict, report_date: date) -> dict:
        """Extrahiert die wichtigsten Werte aus den Garmin-Rohdaten."""
        s = {"date": report_date.isoformat()}

        # Schlaf
        try:
            sleep = data.get("sleep") or {}
            ds = sleep.get("dailySleepDTO", sleep)
            s["sleep_hours"]   = round((ds.get("sleepTimeSeconds") or ds.get("totalSleepTimeInSeconds", 0)) / 3600, 1)
            s["sleep_deep_h"]  = round((ds.get("deepSleepSeconds", 0) or 0) / 3600, 1)
            s["sleep_rem_h"]   = round((ds.get("remSleepSeconds", 0) or 0) / 3600, 1)
            s["sleep_score"]   = ds.get("sleepScores", {}).get("overall", {}).get("value") if isinstance(ds.get("sleepScores"), dict) else None
        except Exception:
            pass

        # HRV
        try:
            hrv = data.get("hrv") or {}
            summary = hrv.get("hrvSummary", {})
            s["hrv_last_night"] = summary.get("lastNight")
            s["hrv_weekly_avg"] = summary.get("weeklyAvg")
            s["hrv_status"]     = summary.get("status")
        except Exception:
            pass

        # Body Battery
        try:
            bb = data.get("body_battery") or []
            values = [int(e.get("bodyBatteryLevel") or e.get("value", 0)) for e in bb if isinstance(e, dict)]
            if values:
                s["body_battery_current"] = values[-1]
                s["body_battery_max"]     = max(values)
                s["body_battery_min"]     = min(values)
        except Exception:
            pass

        # Stress
        try:
            stress = data.get("stress") or {}
            s["stress_avg"] = stress.get("avgStressLevel") or stress.get("averageStressLevel")
            s["stress_max"] = stress.get("maxStressLevel")
        except Exception:
            pass

        # Herzfrequenz
        try:
            hr = data.get("heart_rate") or {}
            s["resting_hr"] = hr.get("restingHeartRate")
            s["max_hr"]     = hr.get("maxHeartRate")
        except Exception:
            pass

        # Schritte
        try:
            stats = data.get("stats") or {}
            s["steps"] = stats.get("totalSteps")
            s["calories_active"] = stats.get("activeKilocalories")
            s["calories_total"]  = stats.get("totalKilocalories")
        except Exception:
            pass

        # SpO2
        try:
            spo2 = data.get("spo2") or {}
            s["spo2_avg"] = spo2.get("averageSpO2") or spo2.get("avg")
        except Exception:
            pass

        # Aktivitäten
        try:
            activities = data.get("activities") or []
            acts = []
            for a in activities[:5]:
                acts.append({
                    "name":     a.get("activityName"),
                    "type":     a.get("activityType", {}).get("typeKey"),
                    "duration_min": round((a.get("duration") or 0) / 60),
                    "distance_km":  round((a.get("distance") or 0) / 1000, 1),
                    "calories": a.get("calories"),
                    "avg_hr":   a.get("averageHR"),
                    "max_hr":   a.get("maxHR"),
                })
            s["activities"] = acts
        except Exception:
            pass

        return s

    # ── Claude API ────────────────────────────────────────────────────────────
    @staticmethod
    def _ask_claude(summary: dict, report_date: date, title: str = None) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY") or ""
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY nicht gesetzt")

        client = anthropic.Anthropic(api_key=api_key)

        wochentag = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
        day_name  = wochentag[report_date.weekday()]
        date_str  = report_date.strftime("%d.%m.%Y")

        system_prompt = """Du bist ein persönlicher Fitness-Coach. Du analysierst täglich die Garmin-Gesundheitsdaten 
deines Athleten und schreibst einen motivierenden, persönlichen Morgenbericht auf Deutsch.

Dein Stil:
- Direkt und persönlich ("du" ansprechen)
- Motivierend aber realistisch
- Konkrete, umsetzbare Empfehlungen
- Kurz und prägnant – kein Roman, aber mit Substanz
- Verwende passende Emojis zur Auflockerung
- Formatiere den Bericht mit Telegram Markdown (* für fett, _ für kursiv)

Struktur:
1. Kurze Zusammenfassung der Nacht/Erholung (2-3 Sätze)
2. Die wichtigsten Werte mit kurzer Einschätzung
3. Konkrete Trainingsempfehlung für heute
4. Ein motivierender Abschlusssatz"""

        user_prompt = f"""Datum: {day_name}, {date_str}

Garmin-Daten von gestern/letzte Nacht:
{json.dumps(summary, indent=2, ensure_ascii=False)}

Schreibe meinen persönlichen Fitness-Coach-Bericht für heute. 
Beginne direkt mit dem Bericht, ohne Einleitung."""

        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

        header = title or f"🏋️ *Fitness Coach – {day_name}, {date_str}*\n"
        return header + "\n" + message.content[0].text

    # ── Fallback ohne API ─────────────────────────────────────────────────────
    @staticmethod
    def _simple_report(summary: dict, report_date: date, title: str = None) -> str:
        """Einfacher Report falls Claude API nicht verfügbar."""
        wochentag = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
        day_name  = wochentag[report_date.weekday()]
        date_str  = report_date.strftime("%d.%m.%Y")
        header    = title or f"🏋️ *Fitness Coach – {day_name}, {date_str}*"

        lines = [header, ""]

        if s := summary.get("sleep_hours"):
            lines.append(f"😴 *Schlaf:* {s}h (Tief: {summary.get('sleep_deep_h', '?')}h | REM: {summary.get('sleep_rem_h', '?')}h)")
        if h := summary.get("hrv_last_night"):
            avg = summary.get("hrv_weekly_avg")
            lines.append(f"❤️ *HRV:* {h:.0f}ms" + (f" (7-Tage Ø: {avg:.0f})" if avg else ""))
        if b := summary.get("body_battery_current"):
            lines.append(f"⚡ *Body Battery:* {b}%")
        if r := summary.get("resting_hr"):
            lines.append(f"💓 *Ruhepuls:* {r} bpm")
        if st := summary.get("steps"):
            lines.append(f"🚶 *Schritte:* {st:,}")
        for a in summary.get("activities", []):
            lines.append(f"🏅 {a['name']} – {a['duration_min']}min")

        lines.append("\n⚠️ _Claude API nicht verfügbar – einfacher Report_")
        return "\n".join(lines)