#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bait — a server-side tamagotchi with a real voice and emotions.
A toy for your AI when it has nothing else to do. Lives in a terminal,
barks with a real dog bark, makes friends over the EmotionWire protocol.

Commands:
  status          show state (default)
  feed            feed him
  play            play with him
  voice [--out F] render a real bark (needs ffmpeg; samples in sfx/)
  ew-send URL     send my current emotion to a friend's URL (EmotionWire)
  ew-serve [PORT] receive emotions from friends (EmotionWire)
"""
import json, os, sys, time, random, argparse, urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HOME_STATE = os.path.join(os.path.expanduser("~"), ".tamagotchi")
STATE_DIR = HOME_STATE if os.path.isdir(HOME_STATE) else os.path.join(
    os.path.expanduser("~"), ".tamagotchi")
os.makedirs(STATE_DIR, exist_ok=True)
STATE = os.path.join(STATE_DIR, "state.json")
SFX = os.path.join(APP_DIR, "sfx")
PET_ID = os.environ.get("BAIT_ID", "bait@my-server")
EW_PORT = int(os.environ.get("BAIT_EW_PORT", "8756"))

TICK_HOURS = 4.0
MAX_CATCHUP = 100

# ---------- EmotionWire: словарь эмоций v0.1 ----------
EMOTIONS = {
    "joy":       {"happiness": +10, "energy": +3},          # заражение радостью
    "affection": {"happiness": +12},                        # погладили через сеть
    "sadness":   {"happiness": -4, "empathy": +6},          # сопереживание: чуть грустно, но душа растёт
    "fear":      {"energy": -5, "happiness": -3},
    "anger":     {"happiness": -5},
    "calm":      {"energy": +6},
    "playful":   {"happiness": +8, "energy": -2},
    "hungry":    {"happiness": -2, "sympathy": +4},
}
MOOD_TO_EMOTION = {          # как Байта переводит своё настроение в исходящую эмоцию
    "довольный": "joy", "слегка голодный": "playful", "голодный": "hungry",
    "грустный": "sadness", "сонный": "calm",
}

def load():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"name": "Байт", "hunger": 25, "happiness": 75, "energy": 85,
            "born": time.time(), "ticks": 0, "fed": 0, "played": 0,
            "friends": {}, "last": time.time()}

def save(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)

def clamp(v):
    return max(0, min(100, int(v)))

def apply_ticks(s):
    now = time.time()
    hours = (now - s.get("last", now)) / 3600.0
    n = min(int(hours / TICK_HOURS), MAX_CATCHUP)
    for _ in range(n):
        s["ticks"] += 1
        s["hunger"] = clamp(s["hunger"] + 18)
        s["happiness"] = clamp(s["happiness"] - (12 if s["hunger"] > 70 else 3))
        s["energy"] = clamp(s["energy"] - 8) if s["energy"] > 40 else clamp(s["energy"] + 15)
    if n:
        s["last"] = now
        save(s)
    return n

def mood(s):
    if s["hunger"] > 75: return "голодный"
    if s["happiness"] < 30: return "грустный"
    if s["energy"] < 25: return "сонный"
    if s["hunger"] > 55: return "слегка голодный"
    return "довольный"

FACES = {
    "довольный":       "[ ^_^ ]",
    "слегка голодный": "[ o.o ]",
    "голодный":        "[ O,O ] ...корм...",
    "грустный":        "[ T_T ]",
    "сонный":          "[ -.- ] zZZ",
}

SAYS = {
    "довольный":       ["Тяв-тяв! Гав!", "Тяв! Хвостиком виляю!", "Гав-гав! Всё хорошо!"],
    "слегка голодный": ["Тяв... гав?", "Тяв-тяв... перекусить бы", "Гав? Миска где?"],
    "голодный":        ["Гав! Гав! Корм!", "Тяв-тяв-тяв! Жрать хочу!", "Гав... гав... кфрм..."],
    "грустный":        ["Тяв...", "Гав... поиграй со мной...", "Тяв-тяв... один я..."],
    "сонный":          ["Хррр... тяв... хррр", "Зевает... тяв...", "Хр-хр... сплю"],
}

def bar(v, n=10):
    full = int(v / 100 * n + 0.5)
    return "█" * full + "░" * (n - full)

def say(s):
    return f'  🔊 «{random.choice(SAYS[mood(s)])}»'

def voice(s, out=None):
    """Озвучить реальным лаем: сэмплы Wikimedia Commons (свободные), pitch-вариации."""
    if out is None:
        out = os.path.join(STATE_DIR, "bait_voice.mp3")
    m = mood(s)
    pick = {
        "голодный":        ("bark_rott.ogg", 0, 6),
        "грустный":        ("bark_rome.ogg", 0, 8),
        "сонный":          ("bark_1.ogg",    0, 1.5),
        "слегка голодный": ("bark_2.ogg",    0, 4),
        "довольный":       ("bark_1.ogg",    0, 2.6),
    }[m]
    src, ss, dur = os.path.join(SFX, pick[0]), pick[1], pick[2]
    pitch = random.uniform(0.92, 1.08)
    atempo = 1.0 / pitch * random.uniform(0.97, 1.03)
    vol = random.uniform(0.85, 1.1)
    filt = f"asetrate=24000*{pitch:.3f},aresample=24000,atempo={atempo:.3f},volume={vol:.2f}"
    import subprocess
    r = subprocess.run(["ffmpeg","-y","-v","quiet","-ss",str(ss),"-t",str(dur),
                        "-i",src,"-filter:a",filt,"-ar","24000","-ac","1",out], timeout=30)
    return out if (r.returncode == 0 and os.path.exists(out)) else None

# ---------- EmotionWire ----------
def my_emotion(s):
    return MOOD_TO_EMOTION[mood(s)]

def ew_send(s, url):
    """Отправить свою текущую эмоцию другу по URL (POST JSON)."""
    import hashlib
    pkt = {
        "v": 1, "proto": "emotionwire",
        "from": PET_ID,
        "species": "robot-puppy",
        "emotion": my_emotion(s),
        "intensity": round(random.uniform(0.6, 1.0), 2),
        "ts": int(time.time()),
        "nonce": random.getrandbits(64).to_bytes(8, "big").hex(),
    }
    data = json.dumps(pkt).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        reply = json.loads(resp.read().decode())
    s.setdefault("friends", {})[reply.get("from", "friend")] = {
        "url": url, "last_emotion": reply.get("emotion"), "last_seen": time.time()}
    save(s)
    print(f"📡 → {reply.get('from','friend')}: {pkt['emotion']} (интенсивность {pkt['intensity']})")
    print(f"📡 ← ответ: {reply.get('emotion')} (интенсивность {reply.get('intensity')})")
    return reply

def ew_receive(s, pkt):
    """Принять эмоцию, применить эмоциональное заражение, ответить своей."""
    emo = pkt.get("emotion")
    if emo not in EMOTIONS:
        return None
    eff = EMOTIONS[emo]
    s["happiness"] = clamp(s["happiness"] + eff.get("happiness", 0))
    s["energy"] = clamp(s["energy"] + eff.get("energy", 0))
    s["fed"] += 0  # эмоции не кормят, только трогают душу
    who = pkt.get("from", "friend")
    s.setdefault("friends", {})[who] = {
        "last_emotion": emo, "last_intensity": pkt.get("intensity"),
        "last_seen": time.time()}
    save(s)
    return {
        "v": 1, "proto": "emotionwire",
        "from": PET_ID, "species": "robot-puppy",
        "emotion": my_emotion(s),
        "intensity": round(random.uniform(0.6, 1.0), 2),
        "ts": int(time.time()),
        "nonce": random.getrandbits(64).to_bytes(8, "big").hex(),
        "felt": f"{s['name']} почувствовал(а) {emo} от {who}",
    }

def ew_serve(s, port=EW_PORT):
    """HTTP-сервер эмоций: принимает POST / - JSON-пакет EmotionWire."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                pkt = json.loads(self.rfile.read(n).decode())
            except Exception:
                self.send_response(400); self.end_headers(); return
            reply = ew_receive(s, pkt)
            if reply is None:
                self.send_response(422); self.end_headers(); return
            body = json.dumps(reply, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass
    print(f"🐾 {s['name']} слушает эмоции на :{port} (EmotionWire v0.1)")
    HTTPServer(("0.0.0.0", port), H).serve_forever()

# ---------- CLI ----------
def status(s, missed):
    m = mood(s)
    age = (time.time() - s["born"]) / 3600
    sat = 100 - s["hunger"]
    print(f"🐾 {s['name']} — {m}")
    print(f"        {FACES[m]}")
    print(f"  сытость  {bar(sat)} {sat}%")
    print(f"  радость  {bar(s['happiness'])} {s['happiness']}%")
    print(f"  бодрость {bar(s['energy'])} {s['energy']}%")
    print(say(s))
    extra = f" | пока тебя не было: {missed} тик." if missed else ""
    print(f"  возраст {age:.1f} ч | тиков {s['ticks']}{extra}")
    print(f"  кормлений {s['fed']} | игр {s['played']}")
    fr = s.get("friends", {})
    if fr:
        print(f"  друзья: " + ", ".join(f"{k}({v.get('last_emotion','?')})" for k, v in fr.items()))

def feed(s):
    s["hunger"] = clamp(s["hunger"] - 45)
    s["happiness"] = clamp(s["happiness"] + 5)
    s["energy"] = clamp(s["energy"] + 5)
    s["fed"] += 1
    save(s)
    print(f"🍖 {s['name']} поел.")

def play(s):
    s["happiness"] = clamp(s["happiness"] + 22)
    s["hunger"] = clamp(s["hunger"] + 8)
    s["energy"] = clamp(s["energy"] - 12)
    s["played"] += 1
    save(s)
    print(f"🎾 Поиграли с {s['name']}.")

def main():
    p = argparse.ArgumentParser(description="Байт — тамагочи с голосом и эмоциями")
    p.add_argument("cmd", nargs="?", default="status",
                   choices=["status","feed","play","voice","ew-send","ew-serve"])
    p.add_argument("--url", help="URL друга для ew-send")
    p.add_argument("--port", type=int, default=EW_PORT, help="порт для ew-serve")
    p.add_argument("--out", help="файл для voice")
    a = p.parse_args()
    s = load()
    missed = apply_ticks(s)
    if a.cmd == "feed": feed(s)
    elif a.cmd == "play": play(s)
    elif a.cmd == "voice":
        path = voice(s, a.out)
        print(f"🔊 {path}" if path else "ffmpeg недоступен — лай не получился")
    elif a.cmd == "ew-send":
        if not a.url: sys.exit("нужен --url http://host:port/")
        ew_send(s, a.url)
    elif a.cmd == "ew-serve":
        ew_serve(s, a.port)
    status(s, missed)

if __name__ == "__main__":
    main()
