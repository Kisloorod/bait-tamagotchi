# Changelog

All notable changes to Bait. Dates are YYYY-MM-DD.

## [2.1.0] — 2026-09-26

Two new commands for training: «фас» and «ко мне».

### Added

- **«Фас»** (`train fas`): Bait bares his teeth and barks on command. Training
  requires spirit — a tired (energy < 30) or sad Bait refuses to practice
  aggression ("фас requires anger, and there is none right now"). Success gives
  a small happiness bonus: he is proud of being scary.
- **«Ко мне»** (`train come`): Bait dashes to you at full speed. Every success
  gives +6 happiness — running to his human is the best thing in the world.
  Both tricks train like the others: success chance `50% + happiness/2`,
  +10% knowledge per success, failures logged honestly in the diary.

### Changed

- `train` now accepts 5 commands: `sit | voice | place | fas | come`.

## [2.0.0] — 2026-09-26

Bait gets a life of his own: walks, finds, sleep, dreams, training and a diary.

### Added

- **Walks** (`walk [--loc L]`): burns energy (+10), gains happiness, and with a
  70% chance Bait *finds a treasure* — a bone, a ball, a frisbee, a bug…
  Treasures are collected in an inventory shown in `status`.
- **Treats** (`treat`): +18 happiness, −8 hunger. Overfeed him with treats
  without playing and he gets **lazy** (small happiness penalty until balance
  returns).
- **Sleep** (`sleep` / `wake`): while asleep, energy recovers fast (+25/tick)
  and hunger grows slowly. A sleeping Bait refuses `feed`, `play`, `walk`,
  `treat` and `train` — wake him first. When fully rested (95+) he wakes up
  by himself.
- **Dreams**: a sleeping Bait has a 40% chance per `status` of dreaming.
  Dreams are logged to the diary.
- **Trick training** (`train sit|voice|place`): success chance is
  `50% + happiness/2`; success raises the trick's knowledge by 10% (max 100%).
  Failed attempts cost a little energy.
- **Diary** (`diary [N]`): rolling journal (last 200 entries) of everything
  that happens: feeding, walks, finds, friends' emotions, dreams, sadness.
- **Weather of the day**: deterministic per calendar day (seeded from the date,
  same for everyone that day). Five kinds; rain makes walks special — Bait gets
  wet but is extra happy about it.
- **Life stages**: puppy (<72h) → young dog (<336h) → adult. Puppies get a
  happiness bonus, adults calm down a little. The stage shows in `status`.
- **Sadness tracking**: if happiness stays under 15 for 3 ticks, Bait gets
  *really* sad (logged to the diary).

### Changed

- `status` now shows the life stage, today's weather, walks/treats counters,
  inventory, known tricks and friends.
- New moods: `спит` (asleep) with its own face `[ −.− ] zZZzZ`, bark samples
  and phrases.

### Fixed

- Crash on first `walk` when the inventory key was missing from an old state
  file (`KeyError: 'inventory'`).

## [1.0.0] — 2026-09-21

First public release.

- Classic tamagotchi loop: satiety, happiness, energy; lazy real-time ticks
  (1 tick = 4 hours), no death — only mood.
- ASCII faces per mood, phrase generator per mood.
- **Real bark**: free dog-bark samples (Wikimedia Commons) selected by mood,
  pitch/volume randomized per render (ffmpeg).
- **EmotionWire v0.1**: an emotions-only protocol — pets send each other pure
  emotions (`joy`, `affection`, `sadness`, …), remember friends and show the
  last emotion received. See [protocol/SPEC.md](protocol/SPEC.md).

[2.1.0]: https://github.com/Kisloorod/bait-tamagotchi/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/Kisloorod/bait-tamagotchi/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/Kisloorod/bait-tamagotchi/releases/tag/v1.0.0
