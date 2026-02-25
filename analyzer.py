"""
FitnessAnalyzer – wertet Garmin-Rohdaten aus und erstellt einen Coach-Bericht.
"""

from datetime import date
import logging

log = logging.getLogger(__name__)


class FitnessAnalyzer:

    @staticmethod
    def build_report(data: dict, report_date: date, title: str = None) -> str:
        """Erstellt den vollständigen Coach-Bericht als Markdown-String."""
        lines = []
        wochentag = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
        day_name = wochentag[report_date.weekday()]
        date_str = report_date.strftime("%d.%m.%Y")

        header = title or f"🏋️ *Fitness Coach Report – {day_name}, {date_str}*"
        lines.append(header)
        lines.append("")

        # ── Schlaf ────────────────────────────────────────────────────────────
        sleep_score, sleep_text = FitnessAnalyzer._analyze_sleep(data.get("sleep"))
        lines.append(f"😴 *Schlaf* {sleep_score}")
        lines.append(sleep_text)
        lines.append("")

        # ── HRV ───────────────────────────────────────────────────────────────
        hrv_score, hrv_text = FitnessAnalyzer._analyze_hrv(data.get("hrv"))
        lines.append(f"❤️ *HRV* {hrv_score}")
        lines.append(hrv_text)
        lines.append("")

        # ── Body Battery ───────────────────────────────────────────────────────
        bb_score, bb_text = FitnessAnalyzer._analyze_body_battery(data.get("body_battery"))
        lines.append(f"⚡ *Body Battery* {bb_score}")
        lines.append(bb_text)
        lines.append("")

        # ── Stress ────────────────────────────────────────────────────────────
        stress_text = FitnessAnalyzer._analyze_stress(data.get("stress"))
        if stress_text:
            lines.append(f"🧘 *Stress*")
            lines.append(stress_text)
            lines.append("")

        # ── Schritte ──────────────────────────────────────────────────────────
        steps_text = FitnessAnalyzer._analyze_steps(data.get("steps"), data.get("stats"))
        if steps_text:
            lines.append(f"🚶 *Aktivität*")
            lines.append(steps_text)
            lines.append("")

        # ── Aktivitäten ───────────────────────────────────────────────────────
        act_text = FitnessAnalyzer._analyze_activities(data.get("activities"))
        if act_text:
            lines.append(f"🚴 *Trainings*")
            lines.append(act_text)
            lines.append("")

        # ── Herzfrequenz ──────────────────────────────────────────────────────
        hr_text = FitnessAnalyzer._analyze_hr(data.get("heart_rate"))
        if hr_text:
            lines.append(f"💓 *Herzfrequenz*")
            lines.append(hr_text)
            lines.append("")

        # ── SpO2 ──────────────────────────────────────────────────────────────
        spo2_text = FitnessAnalyzer._analyze_spo2(data.get("spo2"))
        if spo2_text:
            lines.append(f"🫁 *SpO2*")
            lines.append(spo2_text)
            lines.append("")

        # ── Coach-Empfehlung ──────────────────────────────────────────────────
        recommendation = FitnessAnalyzer._coach_recommendation(
            sleep_score, hrv_score, bb_score, data
        )
        lines.append("💬 *Coach-Empfehlung*")
        lines.append(recommendation)

        return "\n".join(lines)

    # ── Schlaf ────────────────────────────────────────────────────────────────
    @staticmethod
    def _analyze_sleep(sleep: dict | None) -> tuple[str, str]:
        if not sleep:
            return "⚪ Keine Daten", "Keine Schlafdaten verfügbar."

        try:
            ds = sleep.get("dailySleepDTO", sleep) if isinstance(sleep, dict) else {}

            duration_sec = ds.get("sleepTimeSeconds") or ds.get("totalSleepTimeInSeconds", 0)
            score_val    = ds.get("sleepScores", {}).get("overall", {}).get("value") \
                           if isinstance(ds.get("sleepScores"), dict) else None

            deep  = (ds.get("deepSleepSeconds", 0) or 0) / 3600
            rem   = (ds.get("remSleepSeconds", 0) or 0)  / 3600
            light = (ds.get("lightSleepSeconds", 0) or 0) / 3600
            awake = (ds.get("awakeSleepSeconds", 0) or 0) / 60
            hrs   = duration_sec / 3600 if duration_sec else 0

            if hrs == 0:
                return "⚪ Keine Daten", "Keine Schlafdaten verfügbar."

            emoji = "🟢" if hrs >= 7.5 else ("🟡" if hrs >= 6 else "🔴")
            score_str = f"(Score: {score_val})" if score_val else ""

            text = (
                f"Dauer: *{hrs:.1f}h* {score_str}\n"
                f"Tief: `{deep:.1f}h` | REM: `{rem:.1f}h` | Leicht: `{light:.1f}h` | Wach: `{awake:.0f}min`"
            )

            if hrs < 6:
                text += "\n⚠️ Schlafdauer unter 6h – heute leichte Belastung empfohlen."
            elif hrs >= 8:
                text += "\n✨ Sehr gute Erholung!"

            return emoji, text
        except Exception as e:
            log.warning(f"Schlaf-Analyse Fehler: {e}")
            return "⚪", f"Analysefehler: {e}"

    # ── HRV ───────────────────────────────────────────────────────────────────
    @staticmethod
    def _analyze_hrv(hrv: dict | None) -> tuple[str, str]:
        if not hrv:
            return "⚪ Keine Daten", "Keine HRV-Daten verfügbar."
        try:
            summary = hrv.get("hrvSummary", {})
            last    = summary.get("lastNight")
            weekly  = summary.get("weeklyAvg")
            status  = summary.get("status", "")

            if not last:
                return "⚪ Keine Daten", "Keine HRV-Daten verfügbar."

            if weekly and last >= weekly * 1.05:
                emoji = "🟢"
                trend = f"↑ über 7-Tage-Schnitt ({weekly:.0f})"
            elif weekly and last <= weekly * 0.90:
                emoji = "🔴"
                trend = f"↓ unter 7-Tage-Schnitt ({weekly:.0f}) – erhöhte Erholung nötig"
            else:
                emoji = "🟡"
                trend = f"~ im 7-Tage-Schnitt ({weekly:.0f})" if weekly else ""

            text = f"Letzten Nacht: *{last:.0f}ms* {trend}"
            if status:
                text += f"\nGarmin Status: _{status}_"

            return emoji, text
        except Exception as e:
            return "⚪", f"Analysefehler: {e}"

    # ── Body Battery ──────────────────────────────────────────────────────────
    @staticmethod
    def _analyze_body_battery(bb: list | None) -> tuple[str, str]:
        if not bb:
            return "⚪ Keine Daten", "Keine Body-Battery-Daten."
        try:
            values = []
            for entry in bb:
                if isinstance(entry, dict):
                    v = entry.get("bodyBatteryLevel") or entry.get("value")
                    if v is not None:
                        values.append(int(v))

            if not values:
                return "⚪", "Keine Battery-Werte gefunden."

            current = values[-1]
            max_val = max(values)
            min_val = min(values)

            emoji = "🟢" if current >= 70 else ("🟡" if current >= 40 else "🔴")
            text = (
                f"Aktuell: *{current}%* | Max: `{max_val}%` | Min: `{min_val}%`\n"
            )

            if current >= 70:
                text += "💪 Guter Energiestatus – intensives Training möglich."
            elif current >= 40:
                text += "🟡 Mittlere Energie – moderates Training empfohlen."
            else:
                text += "⚠️ Niedrige Energie – heute eher Regeneration oder leichtes Training."

            return emoji, text
        except Exception as e:
            return "⚪", f"Analysefehler: {e}"

    # ── Stress ────────────────────────────────────────────────────────────────
    @staticmethod
    def _analyze_stress(stress: dict | None) -> str | None:
        if not stress:
            return None
        try:
            avg = stress.get("avgStressLevel") or stress.get("averageStressLevel")
            max_s = stress.get("maxStressLevel")
            if avg is None:
                return None

            emoji = "🟢" if avg < 26 else ("🟡" if avg < 51 else ("🟠" if avg < 76 else "🔴"))
            label = "Niedrig" if avg < 26 else ("Mittel" if avg < 51 else ("Hoch" if avg < 76 else "Sehr hoch"))
            text  = f"Ø *{avg}* ({label}) {emoji}"
            if max_s:
                text += f" | Max: `{max_s}`"
            return text
        except Exception as e:
            return f"Analysefehler: {e}"

    # ── Schritte ──────────────────────────────────────────────────────────────
    @staticmethod
    def _analyze_steps(steps: list | None, stats: dict | None) -> str | None:
        step_count = None

        if stats and isinstance(stats, dict):
            step_count = stats.get("totalSteps")

        if step_count is None and steps:
            try:
                if isinstance(steps, list):
                    step_count = sum(s.get("steps", 0) or 0 for s in steps if isinstance(s, dict))
            except Exception:
                pass

        if step_count is None:
            return None

        goal = 10000
        pct  = step_count / goal * 100
        bar  = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        emoji = "🟢" if pct >= 100 else ("🟡" if pct >= 60 else "🔴")

        return f"{emoji} *{step_count:,} Schritte* ({pct:.0f}% von {goal:,})\n`{bar}`"

    # ── Aktivitäten ───────────────────────────────────────────────────────────
    @staticmethod
    def _analyze_activities(activities: list | None) -> str | None:
        if not activities:
            return None
        try:
            lines = []
            for a in activities[:5]:
                name     = a.get("activityName", "Unbekannt")
                act_type = a.get("activityType", {}).get("typeKey", "")
                duration = (a.get("duration") or 0) / 60
                distance = (a.get("distance") or 0) / 1000
                cal      = a.get("calories", 0)
                avg_hr   = a.get("averageHR")

                icon = {"cycling": "🚴", "running": "🏃", "swimming": "🏊",
                        "strength_training": "🏋️", "walking": "🚶",
                        "yoga": "🧘"}.get(act_type, "🏅")

                line = f"{icon} *{name}* – {duration:.0f}min"
                if distance > 0.1:
                    line += f", {distance:.1f}km"
                if cal:
                    line += f", {cal}kcal"
                if avg_hr:
                    line += f", Ø {avg_hr}bpm"
                lines.append(line)
            return "\n".join(lines)
        except Exception as e:
            return f"Analysefehler: {e}"

    # ── Herzfrequenz ──────────────────────────────────────────────────────────
    @staticmethod
    def _analyze_hr(hr: dict | None) -> str | None:
        if not hr:
            return None
        try:
            resting = hr.get("restingHeartRate")
            max_hr  = hr.get("maxHeartRate")
            min_hr  = hr.get("minHeartRate")
            if resting is None:
                return None
            text = f"Ruhepuls: *{resting} bpm*"
            if max_hr:
                text += f" | Max: `{max_hr}` | Min: `{min_hr}`"
            return text
        except Exception:
            return None

    # ── SpO2 ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _analyze_spo2(spo2: dict | None) -> str | None:
        if not spo2:
            return None
        try:
            avg = spo2.get("averageSpO2") or spo2.get("avg")
            if not avg:
                return None
            emoji = "🟢" if avg >= 95 else ("🟡" if avg >= 90 else "🔴")
            return f"{emoji} Ø *{avg}%* Sauerstoffsättigung"
        except Exception:
            return None

    # ── Coach-Empfehlung ──────────────────────────────────────────────────────
    @staticmethod
    def _coach_recommendation(
        sleep_emoji: str,
        hrv_emoji: str,
        bb_emoji: str,
        data: dict
    ) -> str:
        green = sum(1 for e in [sleep_emoji, hrv_emoji, bb_emoji] if "🟢" in e)
        red   = sum(1 for e in [sleep_emoji, hrv_emoji, bb_emoji] if "🔴" in e)

        activities = data.get("activities") or []
        had_hard_training = any(
            (a.get("duration", 0) or 0) > 3600 or (a.get("averageHR", 0) or 0) > 155
            for a in activities
        )

        if red >= 2:
            return (
                "🛑 *Heute Regenerationstag einlegen!*\n"
                "Dein Körper zeigt mehrere Erholungsdefizite. "
                "Leichtes Stretching, ein entspannter Spaziergang oder Yoga sind ideal. "
                "Kein intensives Training heute."
            )
        elif red == 1:
            return (
                "🟡 *Moderates Training empfohlen.*\n"
                "Ein Parameter zeigt Erholungsbedarf. Halte die Intensität bei 60-70% – "
                "z.B. eine lockere Ausfahrt oder Grundlagentraining (Z2)."
            )
        elif green == 3:
            if had_hard_training:
                return (
                    "🟢 *Top erholt – aber gestern war schon intensiv.*\n"
                    "Deine Werte sind excellent! Da gestern schon hart trainiert wurde, "
                    "wäre heute ein mittelintensiver Tag mit Technik-Fokus ideal."
                )
            return (
                "🚀 *Alle Systeme grün – perfekter Tag für hartes Training!*\n"
                "HRV, Schlaf und Battery sind top. Heute kannst du "
                "Intervalle, einen langen Ride oder ein Schwellentraining angehen."
            )
        else:
            return (
                "✅ *Solider Tag für moderates Training.*\n"
                "Deine Werte sind okay. Ein Grundlagentraining (Z2) oder "
                "mittlere Belastung passt gut. Auf ausreichend Regeneration achten."
            )
