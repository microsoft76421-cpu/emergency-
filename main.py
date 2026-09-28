import math
from datetime import datetime, timezone
from typing import Optional

import httpx
import uvicorn
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================
# TELEGRAM CONFIGURATION
# ============================================================

TELEGRAM_BOT_TOKEN = "8976557269:AAEAZ_KUFPrk2qxrSdoqcH7MCcFufwvx42k"
TELEGRAM_CHAT_ID = "8145643961"

# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Emergency API with Telegram Notifications",
    version="1.0.0",
    description="Local Emergency Rescue API with Telegram notifications."
)

# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# TEMPORARY ALERT DATABASE
# ============================================================

alerts_db = []

# ============================================================
# EMERGENCY PAYLOAD
# ============================================================

class EmergencyPayload(BaseModel):
    user_name: str
    contact_phone: str
    emergency_type: str
    latitude: float
    longitude: float
    accuracy: Optional[float] = 0.0
    medical_info: Optional[str] = None
    timestamp: Optional[str] = None

# ============================================================
# TELEGRAM NOTIFICATION
# ============================================================

async def send_telegram_alert(alert: dict, is_cluster: bool = False):
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram bot token is not configured.")
        return

    if not TELEGRAM_CHAT_ID:
        print("Telegram chat ID is not configured.")
        return

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    maps_link = f"https://www.google.com/maps?q={alert['latitude']},{alert['longitude']}"

    if is_cluster:
        message = (
            "🚨 MAJOR INCIDENT CLUSTER DETECTED 🚨\n\n"
            "Multiple emergency alerts have been registered near this location.\n\n"
            f"📍 Coordinates: {alert['latitude']}, {alert['longitude']}\n"
            f"🗺️ Location: {maps_link}"
        )
    else:
        medical_notes = alert.get("medical_info") if alert.get("medical_info") else "N/A"
        accuracy = alert.get("accuracy") or 0

        message = (
            "🚨 EMERGENCY ALERT RECEIVED 🚨\n\n"
            f"👤 Name: {alert['user_name']}\n"
            f"⚠️ Emergency Type: {alert['emergency_type']}\n"
            f"📞 Phone: {alert['contact_phone']}\n"
            f"🏥 Medical Notes: {medical_notes}\n"
            f"🎯 GPS Accuracy: ~{round(accuracy)}m\n"
            f"🕒 Time: {alert['received_at']}\n\n"
            f"🗺️ View Location:\n{maps_link}"
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                telegram_url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "disable_web_page_preview": False
                }
            )

        print("=" * 60)
        print("TELEGRAM RESPONSE")
        print("=" * 60)
        print("Status:", response.status_code)
        print("Response:", response.text)
        print("=" * 60)

        if response.status_code == 200:
            print("Telegram notification sent successfully.")
        else:
            print("Telegram notification failed.")

    except httpx.TimeoutException:
        print("Telegram request timed out.")
    except httpx.RequestError as e:
        print(f"Telegram connection error: {e}")
    except Exception as e:
        print(f"Unexpected Telegram error: {e}")

# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0  # Earth radius in km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ============================================================
# CLUSTER DETECTION AND NOTIFICATIONS
# ============================================================

async def process_cluster_and_notifications(alert_data: dict):
    # Send normal alert
    await send_telegram_alert(alert_data, is_cluster=False)

    # Count nearby alerts (within 1 km)
    nearby_count = 0
    for alert in alerts_db:
        distance = haversine_distance(
            alert_data["latitude"],
            alert_data["longitude"],
            alert["latitude"],
            alert["longitude"]
        )
        if distance <= 1.0:
            nearby_count += 1

    print(f"Nearby emergency alerts: {nearby_count}")

    if nearby_count >= 3:
        print("Major incident cluster detected!")
        await send_telegram_alert(alert_data, is_cluster=True)

# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Emergency Rescue API is running",
        "api": "/api/v1",
        "alert_endpoint": "/api/v1/alert",
        "health": "/api/health",
        "docs": "/docs"
    }

# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
async def health_check():
    telegram_configured = bool(TELEGRAM_BOT_TOKEN) and bool(TELEGRAM_CHAT_ID)

    return {
        "status": "healthy",
        "telegram_configured": telegram_configured,
        "alerts_received": len(alerts_db)
    }

# ============================================================
# CREATE EMERGENCY ALERT
# ============================================================

@app.post("/api/v1/alert", status_code=201)
async def create_alert(payload: EmergencyPayload, background_tasks: BackgroundTasks):
    alert_record = payload.model_dump()
    alert_record["id"] = len(alerts_db) + 1
    alert_record["received_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    alerts_db.append(alert_record)

    print("=" * 60)
    print("NEW EMERGENCY ALERT")
    print("=" * 60)
    print(f"ID: {alert_record['id']}")
    print(f"Name: {alert_record['user_name']}")
    print(f"Emergency: {alert_record['emergency_type']}")
    print(f"Phone: {alert_record['contact_phone']}")
    print(f"Location: {alert_record['latitude']}, {alert_record['longitude']}")
    print("=" * 60)

    background_tasks.add_task(process_cluster_and_notifications, alert_record)

    return {
        "status": "SUCCESS",
        "message": "Emergency alert received. Telegram notification queued.",
        "alert_id": alert_record["id"]
    }

# ============================================================
# GET ALL ALERTS
# ============================================================

@app.get("/api/v1/alerts")
async def get_alerts():
    return {
        "status": "SUCCESS",
        "count": len(alerts_db),
        "alerts": alerts_db
    }

# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("EMERGENCY RESCUE API")
    print("=" * 60)
    print("API:    http://127.0.0.1:8001")
    print("Docs:   http://127.0.0.1:8001/docs")
    print("Alert:  http://127.0.0.1:8001/api/v1/alert")
    print("=" * 60)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,          # Changed to 8001 to avoid conflict
        reload=False
    )