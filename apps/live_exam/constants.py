"""
Shared live exam avatar, accessory, and reaction constants.
"""

from __future__ import annotations

PLAYER_GET_READY_SECONDS = 4.0
PLAYER_QUESTION_INTRO_SECONDS = 5.0
PLAYER_QUESTION_PUBLISH_GRACE_SECONDS = 1.0
PLAYER_RESULT_SECONDS = 3.5
PLAYER_LEADERBOARD_SECONDS = 5.0
PLAYER_REVEAL_TRANSITION_SECONDS = PLAYER_RESULT_SECONDS + PLAYER_LEADERBOARD_SECONDS

DEFAULT_AVATAR_KEY = "avatar_1"
DEFAULT_ACCESSORY_KEY = "accessory_none"

AVATARS = [
    ("avatar_1", "fox"),
    ("avatar_2", "panda"),
    ("avatar_3", "lion"),
    ("avatar_4", "tiger"),
    ("avatar_5", "koala"),
    ("avatar_6", "pig"),
    ("avatar_7", "frog"),
    ("avatar_8", "octopus"),
    ("avatar_9", "monkey"),
    ("avatar_10", "unicorn"),
    ("avatar_11", "rabbit"),
    ("avatar_12", "hamster"),
    ("avatar_13", "wolf"),
    ("avatar_14", "polar_bear"),
    ("avatar_15", "red_panda"),
    ("avatar_16", "mint_rabbit"),
]

ACCESSORIES = [
    (DEFAULT_ACCESSORY_KEY, "none"),
    ("glasses", "glasses"),
    ("cap", "cap"),
    ("crown", "crown"),
    ("mask", "mask"),
    ("sparkles", "sparkles"),
    ("bowtie", "bowtie"),
    ("headphones", "headphones"),
    ("flower", "flower"),
    ("pirate_patch", "pirate_patch"),
    ("halo", "halo"),
]

REACTIONS = [
    ("like", "👍"),
    ("clap", "👏"),
    ("love", "❤️"),
    ("laugh", "😂"),
    ("think", "🤔"),
]

AVATAR_KEYS = [key for key, _ in AVATARS]
ACCESSORY_KEYS = [key for key, _ in ACCESSORIES]
REACTION_KEYS = [key for key, _ in REACTIONS]


def build_wait_room_catalog() -> dict[str, object]:
    return {
        "defaultAvatarKey": DEFAULT_AVATAR_KEY,
        "defaultAccessoryKey": DEFAULT_ACCESSORY_KEY,
        "avatarKeys": AVATAR_KEYS,
        "accessoryKeys": ACCESSORY_KEYS,
        "reactionKeys": REACTION_KEYS,
    }
