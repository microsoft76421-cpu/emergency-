import math
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel

# ---------------------------------------------------------
# TELEGRAM CONFIGURATION
# Replace these with your actual credentials from BotFather
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8976557269:AAHBCvaPiqrMIgfu8Dk13W0b700Mdy8k5fc"
TELEGRAM_CHAT_ID = "8145643961"

app = FastAPI(title="Emergency API with Telegram Notifications")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

alerts_db = []


class EmergencyPayload(BaseModel):
    user_name: str
    contact_phone: str
    emergency_type: str
    latitude: float
    longitude: float
    accuracy: Optional[float] = 0.0
    medical_info: Optional[str] = None
    timestamp: Optional[str] = None


# --- Telegram Notification Dispatcher ---


async def send_telegram_alert(alert: dict, is_cluster: bool = False):
    """Sends a formatted Markdown alert directly to a Telegram Chat or Group."""
    if (
        TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE"
        or not TELEGRAM_BOT_TOKEN
    ):
        print(
            "⚠️ Telegram Token not configured. Skipping Telegram notification."
        )
        return

    maps_link = f"https://www.google.com/maps?q={alert['latitude']},{alert['longitude']}"

    if is_cluster:
        message = (
            f"🚨 **MAJOR INCIDENT CLUSTER DETECTED** 🚨\n\n"
            f"Multiple emergency alerts registered near location!\n"
            f"📍 **Coordinates:** {alert['latitude']}, {alert['longitude']}\n"
            f"🗺️ [Open Location on Google Maps]({maps_link})"
        )
    else:
        message = (
            f"🚨 **EMERGENCY ALERT RECEIVED** 🚨\n\n"
            f"👤 **Name:** {alert['user_name']}\n"
            f"⚠️ **Type:** {alert['emergency_type']}\n"
            f"📞 **Phone:** {alert['contact_phone']}\n"
            f"🏥 **Medical Notes:** {alert.get('medical_info', 'N/A')}\n"
            f"🎯 **GPS Accuracy:** ~{round(alert.get('accuracy', 0))}m\n"
            f"🕒 **Time:** {alert['received_at']}\n\n"
            f"🗺️ [View Live Map Location]({maps_link})"
        )

    telegram_url = (
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                telegram_url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
            )
            if response.status_code != 200:
                print(f"Failed to send Telegram message: {response.text}")
        except Exception as e:
            print(f"Error sending Telegram notification: {e}")


# --- Cluster Detection Logic ---


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def process_cluster_and_notifications(alert_data: dict):
    # 1. Dispatch individual Telegram alert
    await send_telegram_alert(alert_data, is_cluster=False)

    # 2. Check if a major incident cluster exists (>= 3 alerts within 1km)
    nearby_count = 0
    for alert in alerts_db:
        dist = haversine_distance(
            alert_data["latitude"],
            alert_data["longitude"],
            alert["latitude"],
            alert["longitude"],
        )
        if dist <= 1.0:
            nearby_count += 1

    if nearby_count >= 3:
        await send_telegram_alert(alert_data, is_cluster=True)


# --- Endpoints ---


@app.post("/api/v1/alert", status_code=201)
async def create_alert(
    payload: EmergencyPayload, background_tasks: BackgroundTasks
):
    alert_record = payload.dict()
    alert_record["id"] = len(alerts_db) + 1
    alert_record["received_at"] = datetime.utcnow().strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    alerts_db.append(alert_record)

    # Trigger Telegram notifications in the background
    background_tasks.add_task(
        process_cluster_and_notifications, alert_record
    )

    return {
        "status": "SUCCESS",
        "message": "Alert received and sent to Telegram.",
        "alert_id": alert_record["id"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
