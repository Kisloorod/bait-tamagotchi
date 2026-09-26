#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bait — a server-side tamagotchi with a real voice, emotions and a life of his own.
A toy for your AI when it has nothing else to do. Lives in a terminal,
barks with a real dog bark, makes friends over the EmotionWire protocol.

Commands:
  status            show state (default)
  feed              feed him
  play              play with him
  walk [--loc L]    take him for a walk (finds treasures, sees weather)
  treat             give a treat (big happiness, small satiety; don't overdo it)
  sleep             tuck him in (fast energy recovery, no playing while asleep)
  wake              wake him up
  train CMD         teach a trick: sit | voice | place | fas | come
  diary [N]         show the last N diary entries
  voice [--out F]   render a real bark (needs ffmpeg; samples in sfx/)
  ew-send URL       send my current emotion to a friend's URL (EmotionWire)
  ew-serve [PORT]   receive emotions from friends (EmotionWire)

v2.1 (2026-09-26): new tricks «фас» and «ко мне» (come): fas needs spirit,
                   come makes him happiest. Training success still grows with joy.
v2.0 (2026-09-26): walks with finds, treats, sleep, trick training, diary,
                   pseudo-weather, life stages, dreams.
"""
import json, os, sys, time, random, argparse, urllib.request, datetime

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
    "joy":       {"happiness": +10, "energy": +3},
    "affection": {"happiness": +12},
    "sadness":   {"happiness": -4, "empathy": +6},
    "fear":      {"energy": -5, "happiness": -3},
    "anger":     {"happiness": -5},
    "calm":      {"energy": +6},
    "playful":   {"happiness": +8, "energy": -2},
    "hungry":    {"happiness": -2, "sympathy": +4},
}
MOOD_TO_EMOTION = {
    "довольный": "joy", "слегка голодный": "playful", "голодный": "hungry",
    "грустный": "sadness", "сонный": "calm",
}

# ---------- Новое в v1.1 ----------

WEATHER = [
    ("солнечно",  "☀️", {"happiness": +2}),
    ("облачно",   "☁️", {}),
    ("ветрено",   "🌬", {"energy": -1}),
    ("дождь",     "🌧", {"happiness": -2}),
    ("снег",      "🌨", {"happiness": +1}),
]
FINDS = [
    ("🍖 косточка",      {"happiness": +6}),
    ("🎾 мячик",         {"happiness": +8, "energy": -2}),
    ("🥏 летающая тарелка", {"happiness": +7, "energy": -3}),
    ("🦴 старая кость",   {"happiness": +3}),
    ("🌸 цветочек",      {"happiness": +2}),
    ("🐛 жук!",          {"happiness": +10, "energy": -4}),
    ("📰 чья-то газета",  {"happiness": +1}),
]
TRICKS = ["sit", "voice", "place", "fas", "come"]
TRICK_RU = {"sit": "сидеть", "voice": "голос", "place": "место",
            "fas": "фас", "come": "ко мне"}

STAGES = [                       # (порог возраста в часах, название, modifier)
    (0,   "щенок",        {"happiness": +5}),   # щенку всё радостно
    (72,  "молодой пёс",  {}),
    (336, "взрослый пёс", {"energy": -3}),     # взрослый чуть спокойнее
]

DREAMS = [
    "видел сон: бесконечное поле и летающая тарелка…",
    "видел сон: миска, полная косточек…",
    "видел сон: его гладил человек с тёплыми руками…",
    "видел сон: он гонится за мячом, который сам бросается…",
    "видел сон: другие собаки по EmotionWire…",
    "проснулся на секунду, посмотрел на серверную стойку и уснул снова",
]

def _today_seed():
    return int(time.time()) // 86400

def weather():
    """Погода дня: одинаковая в течение суток, меняется день ото дня."""
    rnd = random.Random(_today_seed())
    w = rnd.choice(WEATHER)
    return w

def stage(age_h):
    name, mod = STAGES[0][1], STAGES[0][2]
    for thr, n, m in STAGES:
        if age_h >= thr:
            name, mod = n, m
    return name, mod

def diary_add(s, text):
    d = s.setdefault("diary", [])
    d.append({"t": time.strftime("%Y-%m-%d %H:%M"), "e": text})
    s["diary"] = d[-200:]     # хвост дневника, не бесконечность

def load():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"name": "Байт", "hunger": 25, "happiness": 75, "energy": 85,
            "born": time.time(), "ticks": 0, "fed": 0, "played": 0,
            "friends": {}, "last": time.time(),
            # v1.1
            "asleep": False, "treats": 0, "walks": 0,
            "inventory": {}, "tricks": {}, "diary": [],
            "sad_days": 0, "last_walk": 0}

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
        if s.get("asleep"):
            # спит: бодрость быстро растёт, голод медленно
            s["energy"] = clamp(s["energy"] + 25)
            s["hunger"] = clamp(s["hunger"] + 6)
            if s["energy"] >= 95:              # выспался — сам просыпается
                s["asleep"] = False
                diary_add(s, "выспался и проснулся сам")
        else:
            s["hunger"] = clamp(s["hunger"] + 18)
            s["happiness"] = clamp(s["happiness"] - (12 if s["hunger"] > 70 else 3))
            s["energy"] = clamp(s["energy"] - 8) if s["energy"] > 40 else clamp(s["energy"] + 15)
        # хандра: если давно никто не играл (счётчик тиков без радости)
        if s["happiness"] < 15 and not s.get("asleep"):
            s["sad_days"] = s.get("sad_days", 0) + 1
            if s["sad_days"] == 3:
                diary_add(s, "заскучал по-настоящему…")
        elif s["happiness"] > 50:
            s["sad_days"] = 0
    if n:
        s["last"] = now
        save(s)
    return n

def mood(s):
    if s.get("asleep"): return "спит"
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
    "спит":            "[ −.− ] zZZzZ",
}

SAYS = {
    "довольный":       ["Тяв-тяв! Гав!", "Тяв! Хвостиком виляю!", "Гав-гав! Всё хорошо!"],
    "слегка голодный": ["Тяв... гав?", "Тяв-тяв... перекусить бы", "Гав? Миска где?"],
    "голодный":        ["Гав! Гав! Корм!", "Тяв-тяв-тяв! Жрать хочу!", "Гав... гав... кфрм..."],
    "грустный":        ["Тяв...", "Гав... поиграй со мной...", "Тяв-тяв... один я..."],
    "сонный":          ["Хррр... тяв... хррр", "Зевает... тяв...", "Хр-хр... сплю"],
    "спит":            ["Хрррр... хррр...", "тяв... (во сне)", "хр-хр... косточки..."],
}

def bar(v, n=10):
    full = int(v / 100 * n + 0.5)
    return "█" * full + "░" * (n - full)

def say(s):
    m = mood(s)
    line = random.choice(SAYS[m])
    # сонные сны: иногда спящий Байт видит сон
    if m == "спит" and random.random() < 0.4:
        dream = random.choice(DREAMS)
        diary_add(s, dream)
        line += f"  💭 {dream}"
    return f'  🔊 «{line}»'

def voice(s, out=None):
    """Озвучить Байта РЕАЛЬНЫМ лаем (сэмплы Wikimedia Commons, свободные)."""
    m = mood(s)
    S = SFX
    if m == "голодный":
        src, dur = f"{S}/bark_rott.ogg", 6
    elif m == "грустный":
        src, dur = f"{S}/bark_rome.ogg", 8
    elif m in ("сонный", "спит"):
        src, dur = f"{S}/bark_1.ogg", 1.5
    elif m == "слегка голодный":
        src, dur = f"{S}/bark_2.ogg", 4
    else:
        src, dur = f"{S}/bark_1.ogg", 2.6
    pitch = random.uniform(0.92, 1.08)
    atempo = 1.0 / pitch * random.uniform(0.97, 1.03)
    vol = random.uniform(0.85, 1.1)
    filt = f"asetrate=24000*{pitch:.3f},aresample=24000,atempo={atempo:.3f},volume={vol:.2f}"
    out = out or os.path.join(STATE_DIR, "bait_voice.mp3")
    try:
        subprocess = __import__("subprocess")
        r = subprocess.run(["ffmpeg", "-y", "-ss", "0", "-t", str(dur), "-i", src,
                            "-af", filt, "-f", "mp3", out],
                           capture_output=True, timeout=30)
        return out if r.returncode == 0 else None
    except Exception:
        return None

# ---------- EmotionWire ----------
def my_emotion(s):
    return MOOD_TO_EMOTION.get(mood(s), "calm")

def ew_send(s, url):
    pkt = {"id": PET_ID, "emotion": my_emotion(s),
           "mood": mood(s), "ts": int(time.time())}
    req = urllib.request.Request(url, data=json.dumps(pkt).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        print(f"📡 отправил «{pkt['emotion']}» → {url}: {r.status}")

def ew_receive(s, pkt):
    emo = pkt.get("emotion", "calm")
    eff = EMOTIONS.get(emo, {})
    s["happiness"] = clamp(s["happiness"] + eff.get("happiness", 0))
    s["energy"] = clamp(s["energy"] + eff.get("energy", 0))
    s.setdefault("empathy", 0); s["empathy"] = s.get("empathy", 0) + eff.get("empathy", 0)
    s.setdefault("sympathy", 0); s["sympathy"] = s.get("sympathy", 0) + eff.get("sympathy", 0)
    who = pkt.get("id", "кто-то")
    s.setdefault("friends", {})
    fr = s["friends"].setdefault(who, {"seen": 0, "last_emotion": "—"})
    fr["seen"] += 1
    fr["last_emotion"] = emo
    fr["last_ts"] = pkt.get("ts", int(time.time()))
    diary_add(s, f"друг {who} прислал «{emo}»")
    save(s)

def ew_serve(s, port=EW_PORT):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            ln = int(self.headers.get("Content-Length", 0))
            try:
                pkt = json.loads(self.rfile.read(ln) or b"{}")
            except Exception:
                pkt = {}
            ew_receive(s, pkt)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        def log_message(self, *a): pass
    print(f"🐾 {s['name']} слушает эмоции на :{port} (EmotionWire v0.1)")
    HTTPServer(("0.0.0.0", port), H).serve_forever()

# ---------- действия ----------
def _apply(stage_mod, eff):
    """Применить эффект с учётом стадии жизни."""
    out = dict(eff)
    if "happiness" in out:
        out["happiness"] += stage_mod.get("happiness", 0)
    if "energy" in out:
        out["energy"] += stage_mod.get("energy", 0)
    return out

def status(s, missed):
    m = mood(s)
    age = (time.time() - s["born"]) / 3600
    st_name, _ = stage(age)
    sat = 100 - s["hunger"]
    wemoji, wname, _ = weather()
    print(f"🐾 {s['name']} — {m} ({st_name})")
    print(f"        {FACES[m]}")
    print(f"  сытость  {bar(sat)} {sat}%")
    print(f"  радость  {bar(s['happiness'])} {s['happiness']}%")
    print(f"  бодрость {bar(s['energy'])} {s['energy']}%")
    print(f"  погода: {wemoji} {wname}")
    print(say(s))
    extra = f" | пока тебя не было: {missed} тик." if missed else ""
    print(f"  возраст {age:.1f} ч | тиков {s['ticks']}{extra}")
    print(f"  кормлений {s['fed']} | игр {s['played']} | прогулок {s.get('walks',0)}"
          f" | вкусняшек {s.get('treats',0)}")
    inv = s.get("inventory", {})
    if inv:
        print("  находки: " + ", ".join(f"{k}×{v}" for k, v in inv.items()))
    tr = s.get("tricks", {})
    if tr:
        print("  трюки: " + ", ".join(f"{TRICK_RU.get(k,k)} {v}%" for k, v in tr.items()))
    fr = s.get("friends", {})
    if fr:
        print(f"  друзья: " + ", ".join(f"{k}({v.get('last_emotion','?')})" for k, v in fr.items()))

def feed(s):
    if s.get("asleep"):
        print(f"😴 {s['name']} спит. Сначала разбуди: wake")
        return
    s["hunger"] = clamp(s["hunger"] - 45)
    s["happiness"] = clamp(s["happiness"] + 5)
    s["energy"] = clamp(s["energy"] + 5)
    s["fed"] += 1
    diary_add(s, "покормили")
    save(s)
    print(f"🍖 {s['name']} поел.")

def play(s):
    if s.get("asleep"):
        print(f"😴 {s['name']} спит. Сначала разбуди: wake")
        return
    s["happiness"] = clamp(s["happiness"] + 22)
    s["hunger"] = clamp(s["hunger"] + 8)
    s["energy"] = clamp(s["energy"] - 12)
    s["played"] += 1
    diary_add(s, "поиграли")
    save(s)
    print(f"🎾 Поиграли с {s['name']}.")

def treat(s):
    if s.get("asleep"):
        print(f"😴 {s['name']} спит. Сначала разбуди: wake")
        return
    s["happiness"] = clamp(s["happiness"] + 18)
    s["hunger"] = clamp(s["hunger"] - 8)
    s["energy"] = clamp(s["energy"] + 2)
    s["treats"] = s.get("treats", 0) + 1
    # злоупотребление: если вкусняшек много, а игр мало — ленится
    lazy = s["treats"] > s["played"] + 3
    if lazy:
        s["happiness"] = clamp(s["happiness"] - 4)
        diary_add(s, "съел вкусняшку и разленился…")
        print(f"🦴 Вкусняшка съедена… но {s['name']} начинает лениться: играй больше!")
    else:
        diary_add(s, "получил вкусняшку")
        print(f"🦴 {s['name']} получил вкусняшку. Хвостом махал так, чуть не улетел.")
    save(s)

def walk(s, loc=None):
    if s.get("asleep"):
        print(f"😴 {s['name']} спит. Сначала разбуди: wake")
        return
    if s["energy"] < 15:
        print(f"😪 {s['name']} слишком устал для прогулки. Дай ему поспать: sleep")
        return
    wemoji, wname, weff = weather()
    s["energy"] = clamp(s["energy"] - 10)
    s["hunger"] = clamp(s["hunger"] + 6)
    s["walks"] = s.get("walks", 0) + 1
    # дождь портит настроение, если гулять всё равно — Байт доволен вдвойне
    if wname == "дождь":
        s["happiness"] = clamp(s["happiness"] + 12)
        diary_add(s, "гулял под дождём — промок, но был счастлив")
        print(f"🌧 Дождь! {s['name']} промок, но гулял так счастливо, что это неважно.")
    else:
        s["happiness"] = clamp(s["happiness"] + 10 + weff.get("happiness", 0))
        diary_add(s, f"прогулка ({wname})" + (f" у {loc}" if loc else ""))
        print(f"🚶 Прогулка ({wemoji} {wname})" + (f" у {loc}" if loc else "") + ".")
    # находка (шанс 70%)
    if random.random() < 0.7:
        item, feff = random.choice(FINDS)
        inv = s.setdefault("inventory", {})
        inv[item] = inv.get(item, 0) + 1
        s["happiness"] = clamp(s["happiness"] + feff.get("happiness", 0))
        s["energy"] = clamp(s["energy"] + feff.get("energy", 0))
        diary_add(s, f"нашёл {item}!")
        print(f"✨ {s['name']} нашёл {item}!")
    else:
        print(f"🐾 Ничего не нашёл, просто бегал и нюхал всё подряд.")
    save(s)

def sleep(s):
    if s.get("asleep"):
        print(f"😴 {s['name']} уже спит.")
        return
    s["asleep"] = True
    diary_add(s, "уложили спать")
    save(s)
    print(f"😴 {s['name']} устроился на подстилке и уснул. zZZ")

def wake(s):
    if not s.get("asleep"):
        print(f"🐾 {s['name']} и так не спит.")
        return
    s["asleep"] = False
    dream = random.choice(DREAMS) if random.random() < 0.5 else None
    diary_add(s, "разбудили" + (f"; {dream}" if dream else ""))
    save(s)
    print(f"🐾 {s['name']} зевнул и проснулся." + (f" 💭 {dream}" if dream else ""))

def train(s, trick):
    if s.get("asleep"):
        print(f"😴 {s['name']} спит. Сначала разбуди: wake")
        return
    if trick not in TRICKS:
        print(f"Не знаю такой команды. Доступны: {', '.join(TRICKS)}")
        return
    tr = s.setdefault("tricks", {})
    cur = tr.get(trick, 0)
    # «фас»: усталый или грустный пёс не злится — тренировка не идёт
    if trick == "fas" and (s["energy"] < 30 or mood(s) == "грустный"):
        s["energy"] = clamp(s["energy"] - 2)
        diary_add(s, "не стал учить «фас»: не в том настроении")
        save(s)
        print(f"🐾 {s['name']} посмотрел на тебя и не двинулся. «Фас» требует злости, а её сейчас нет.")
        return
    # вероятность успеха растёт с радостью (50% + радость/2)
    if random.random() < 0.5 + s["happiness"] / 200:
        tr[trick] = min(100, cur + 10)
        if trick == "fas":
            s["happiness"] = clamp(s["happiness"] + 4)
            diary_add(s, f"выучил «{TRICK_RU[trick]}» ({tr[trick]}%) — грозный пёс!")
            save(s)
            print(f"🎯 {s['name']} показал клыки и рявкнул! «Фас» выучен: {tr[trick]}%")
        elif trick == "come":
            s["happiness"] = clamp(s["happiness"] + 6)   # бегать к хозяину — счастье
            diary_add(s, f"выучил «{TRICK_RU[trick]}» ({tr[trick]}%) — прибежал с радостью")
            save(s)
            print(f"🎯 {s['name']} пулей примчался к тебе! «Ко мне» выучено: {tr[trick]}%")
        else:
            diary_add(s, f"выучил «{TRICK_RU[trick]}» ({tr[trick]}%)")
            save(s)
            print(f"🎯 {s['name']} выполнил «{TRICK_RU[trick]}»! Знание: {tr[trick]}%")
    else:
        s["energy"] = clamp(s["energy"] - 3)
        diary_add(s, f"не вышло «{TRICK_RU[trick]}», пробуем ещё")
        save(s)
        print(f"🙈 Не вышло. {s['name']} запутался в лапах. Знание: {cur}%")

def diary(s, n=10):
    entries = s.get("diary", [])[-n:]
    if not entries:
        print("📜 Дневник пуст. Пока — всё впереди.")
        return
    print(f"📜 Дневник {s['name']} (последние {len(entries)}):")
    for e in entries:
        print(f"  {e['t']} — {e['e']}")

def main():
    p = argparse.ArgumentParser(description="Байт — тамагочи с голосом, эмоциями и прогулками")
    p.add_argument("cmd", nargs="?", default="status",
                   choices=["status","feed","play","walk","treat","sleep","wake",
                            "train","diary","voice","ew-send","ew-serve"])
    p.add_argument("arg", nargs="?", help="трюк для train / N для diary / локация для walk")
    p.add_argument("--url", help="URL друга для ew-send")
    p.add_argument("--port", type=int, default=EW_PORT, help="порт для ew-serve")
    p.add_argument("--out", help="файл для voice")
    p.add_argument("--loc", help="где гуляем (для walk)")
    a = p.parse_args()
    s = load()
    missed = apply_ticks(s)
    if a.cmd == "feed": feed(s)
    elif a.cmd == "play": play(s)
    elif a.cmd == "walk": walk(s, a.loc)
    elif a.cmd == "treat": treat(s)
    elif a.cmd == "sleep": sleep(s)
    elif a.cmd == "wake": wake(s)
    elif a.cmd == "train": train(s, a.arg or "")
    elif a.cmd == "diary": diary(s, int(a.arg) if a.arg and a.arg.isdigit() else 10)
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
