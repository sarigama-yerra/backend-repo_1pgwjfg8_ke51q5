import os
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Ping - Mock Router API", version="0.1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# In-memory mock storage
# ----------------------

class User(BaseModel):
    handle: str
    name: str
    bio: str
    email: Optional[str] = None
    phone: Optional[str] = None

# Seed mock users
USERS: Dict[str, User] = {
    "davit": User(handle="davit", name="Davit A.", bio="Building delightful products. Lover of crisp UIs and fast APIs.", email="davit@example.com", phone="+1234567890"),
    "alex": User(handle="alex", name="Alex M.", bio="Design, code, sound. Trying new mediums every week.", email="alex@example.com", phone="+1987654321"),
    "kai": User(handle="kai", name="Kai Z.", bio="Research → Prototypes → Systems. ping to collaborate.", email="kai@example.com", phone="+14155550123"),
}

class MessageIn(BaseModel):
    handle: str = Field(..., description="Recipient user handle, e.g., 'davit'")
    subject: str
    message: str
    contact: str = Field(..., description="Sender contact: email or phone")
    priority: Literal['normal', 'urgent'] = 'normal'

class DeliveryResult(BaseModel):
    channel: Literal['email', 'sms', 'inbox']
    delivered: bool
    debug: str
    auto_reply: Optional[str] = None

class Message(BaseModel):
    id: str
    created_at: str
    handle: str
    subject: str
    message: str
    contact: str
    priority: Literal['normal', 'urgent']
    decided_channel: Literal['email', 'sms', 'inbox']
    deliveries: List[DeliveryResult]

MESSAGES: List[Message] = []

# Routing rules (editable on dashboard). Keep simple JSON-like structure.
DEFAULT_RULES: Dict[str, Any] = {
    "priority": {
        "urgent": "sms"
    },
    "subject_keywords": {
        "keywords": ["quote", "collab"],
        "channel": "email"
    },
    "outside_working_hours": {
        "channel": "email",
        "auto_reply": "Thanks for your message. I'm currently away and will reply during working hours."
    },
    "fallback": "inbox",
    "working_hours": {
        "start": 9,
        "end": 17,
        "weekdays_only": True
    }
}

ROUTING_RULES: Dict[str, Any] = DEFAULT_RULES.copy()

# ----------------------
# Helpers
# ----------------------

def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def is_working_hours(dt: Optional[datetime] = None) -> bool:
    dt = dt or datetime.utcnow()
    wh = ROUTING_RULES.get("working_hours", {"start": 9, "end": 17, "weekdays_only": True})
    start = int(wh.get("start", 9))
    end = int(wh.get("end", 17))
    weekdays_only = bool(wh.get("weekdays_only", True))

    if weekdays_only and dt.weekday() >= 5:  # 5=Sat,6=Sun
        return False
    return start <= dt.hour < end


def route_message(msg: MessageIn) -> (str, Optional[str]):
    # priority rule
    prio_map = ROUTING_RULES.get("priority", {})
    if msg.priority in prio_map:
        return prio_map[msg.priority], None

    # subject keywords
    sub_rule = ROUTING_RULES.get("subject_keywords", {})
    keywords = [str(k).lower() for k in sub_rule.get("keywords", [])]
    if any(k in msg.subject.lower() for k in keywords):
        return str(sub_rule.get("channel", "email")), None

    # outside working hours
    if not is_working_hours():
        owh = ROUTING_RULES.get("outside_working_hours", {})
        ch = str(owh.get("channel", "email"))
        auto = owh.get("auto_reply")
        return ch, auto

    # fallback
    return str(ROUTING_RULES.get("fallback", "inbox")), None


def simulate_delivery(channel: str, msg: MessageIn, auto_reply: Optional[str]) -> List[DeliveryResult]:
    deliveries: List[DeliveryResult] = []

    if channel == "email":
        debug = f"[EMAIL] To: {USERS.get(msg.handle).email if msg.handle in USERS else 'unknown'} | From: {msg.contact} | Subj: {msg.subject}"
        print(debug)
        deliveries.append(DeliveryResult(channel="email", delivered=True, debug=debug, auto_reply=auto_reply))
    elif channel == "sms":
        debug = f"[SMS] To: {USERS.get(msg.handle).phone if msg.handle in USERS else 'unknown'} | From: {msg.contact} | Msg: {msg.message[:60]}..."
        print(debug)
        deliveries.append(DeliveryResult(channel="sms", delivered=True, debug=debug, auto_reply=auto_reply))
    elif channel == "inbox":
        debug = f"[INBOX] Stored for {msg.handle} | From: {msg.contact} | Subj: {msg.subject}"
        print(debug)
        deliveries.append(DeliveryResult(channel="inbox", delivered=True, debug=debug, auto_reply=auto_reply))
    else:
        debug = f"[UNKNOWN] Channel {channel} not implemented"
        print(debug)
        deliveries.append(DeliveryResult(channel=channel, delivered=False, debug=debug, auto_reply=auto_reply))

    return deliveries

# ----------------------
# API Routes
# ----------------------

@app.get("/")
async def root():
    return {"service": "Ping", "version": "0.1.1"}

@app.get("/api/users/{handle}", response_model=User)
async def get_user(handle: str):
    user = USERS.get(handle)
    if not user:
        raise HTTPException(404, detail="User not found")
    return user

@app.get("/api/messages", response_model=List[Message])
async def list_messages():
    return list(reversed(MESSAGES))

@app.post("/api/messages", response_model=Message)
async def create_message(payload: MessageIn):
    if payload.handle not in USERS:
        raise HTTPException(404, detail="User not found")

    channel, auto_reply = route_message(payload)
    deliveries = simulate_delivery(channel, payload, auto_reply)

    msg = Message(
        id=str(len(MESSAGES) + 1),
        created_at=now_iso(),
        handle=payload.handle,
        subject=payload.subject,
        message=payload.message,
        contact=payload.contact,
        priority=payload.priority,
        decided_channel=channel,  # type: ignore
        deliveries=deliveries,
    )
    MESSAGES.append(msg)
    return msg

@app.get("/api/rules")
async def get_rules():
    return ROUTING_RULES

@app.put("/api/rules")
async def update_rules(new_rules: Dict[str, Any]):
    global ROUTING_RULES
    if not isinstance(new_rules, dict):
        raise HTTPException(400, detail="Rules must be a JSON object")
    ROUTING_RULES = new_rules
    return {"ok": True, "updated": ROUTING_RULES}

@app.delete("/api/messages")
async def reset_messages():
    MESSAGES.clear()
    return {"ok": True, "count": 0}

@app.get("/test")
async def test():
    return {"backend": "✅ Running", "users": list(USERS.keys()), "messages_stored": len(MESSAGES)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
