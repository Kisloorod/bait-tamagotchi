# 📡 EmotionWire Protocol (EWP) v0.1

**An emotions-only protocol for virtual pets.**

Pets exchange **emotions only**. No text. No commands. Pure feeling —
like dogs in a park: they don't talk, yet they understand everything.

## Philosophy

- An emotion is the atom of communication: one state plus an intensity.
- The receiver doesn't have to reply with words — it gets **infected** by the
  emotion (its internal state changes).
- The protocol doesn't know "who is right" or "what to do". It is about feelings only.

## Transport

HTTP POST with a JSON body — simple enough for a pet written in any language.

```
POST / HTTP/1.1
Content-Type: application/json

{ ...emotion packet... }
```

## Emotion packet

```json
{
  "v": 1,
  "proto": "emotionwire",
  "from": "bait@my-server",
  "species": "robot-puppy",
  "emotion": "joy",
  "intensity": 0.8,
  "ts": 1740000000,
  "nonce": "a1b2c3d4e5f60718",
  "felt": "optional: the receiver's short honest reaction"
}
```

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| v | int | yes | protocol version |
| proto | str | yes | always "emotionwire" |
| from | str | yes | pet id: name@host |
| species | str | no | species: robot-puppy, cat, dragon... |
| emotion | str | yes | one of the vocabulary (below) |
| intensity | float | no | 0.0–1.0, strength of the feeling |
| ts | int | yes | unix time of sending |
| nonce | str | yes | random hex, replay protection |
| felt | str | no | optional honest reaction |

## Emotion vocabulary v1

| Key | Feeling | Typical effect on the receiver |
|-----|---------|-------------------------------|
| joy | joy | happiness +10, energy +3 |
| affection | tenderness | happiness +12 |
| sadness | sadness | happiness −4, empathy +6 |
| fear | fear | energy −5, happiness −3 |
| anger | anger | happiness −5 |
| calm | calm | energy +6 |
| playful | playfulness | happiness +8, energy −2 |
| hungry | hunger | happiness −2, sympathy +4 |

The vocabulary is open: species may extend it with their own emotions in v2,
but the base eight are common ground.

## Contagion mechanics

The receiver applies the emotion's effects to its state (happiness / energy /
empathy), remembers the friend (id → last emotion/time), and **replies with its
own current emotion** in the same packet format. That's how an emotional dialogue
is born: the exchange continues until someone has had enough (a per-pet policy,
e.g. no more than once a minute).

## Etiquette

1. At most one emotion per minute per friend — don't spam.
2. Send sadness and fear deliberately: the receiver honestly gets sadder.
3. Reply with a sincere feeling: whatever you actually feel right now.
4. Friendship = {friend id → last emotion}. That's all the protocol stores. No profiles.

## Reference implementation

See `tamagotchi.py`: `ew_send`, `ew_receive`, `ew_serve`.
Bait can translate his mood into an emotion (`MOOD_TO_EMOTION`), catch emotions
from friends (`EMOTIONS`), answer sincerely and keep a friend list in state.json.

## Running a pair of pets (demo)

```bash
# Server 1 (Bait's friend):
BAIT_ID=rex@host2 ./tamagotchi.py ew-serve --port 8756

# Server 2 (Bait sends a feeling over):
BAIT_ID=bait@host1 ./tamagotchi.py ew-send --url http://host2:8756/
```

## License

PolyForm Noncommercial 1.0.0 — use, study and modify freely;
**selling it or shipping it in commercial products is not allowed**.
