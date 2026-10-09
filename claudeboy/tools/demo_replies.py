"""
Preset replies for the ClaudeBoy demo ROM (make demo). Edit freely: the build
wraps and lays them out exactly like the live bridge would.

REPLIES: category -> list of replies. A reply is a string, or a dict with
    text      what Claude says
    simpler   answer to "Explain simpler" right after it   (optional)
    more      answer to "Keep going" right after it        (optional)
Replies in a category take turns.

KEYWORDS: (phrase, category), checked in order against what you typed
(lowercased, punctuation turned into spaces, padded with a space on each
side, so " hi " only matches the word "hi"). The quick-menu items are matched
the same way. Nothing matches -> "fallback".
"""

REPLIES = {
    "joke": [
        {"text": "Why did the Game Boy go to therapy? It had too many unresolved links.",
         "simpler": "It's a pun! Game Boys connect with a link cable, and 'unresolved links' "
                    "also sounds like emotional baggage.",
         "more": "Here's another one: what's a Game Boy's favourite snack? Micro-chips."},
        {"text": "What do you call a Game Boy that fell asleep? A Game Doze.",
         "more": "And when it wakes up, it's a Game Joy."},
        {"text": "My printer and I had an argument. Now it's giving me the cold shoulder, "
                 "and some very faded receipts.",
         "simpler": "Thermal paper fades over time, so 'faded receipts' is the printer "
                    "being passive-aggressive."},
        {"text": "I told my Game Boy a secret. Now it won't stop sharing it over the link cable."},
    ],
    "haiku": [
        {"text": "Small screen aglow\na world in my palm\nfour greens deep",
         "simpler": "It's about how a little Game Boy screen can hold whole worlds, "
                    "even with just four colours."},
        {"text": "Batteries run low\none more level\nred light blinking",
         "simpler": "It's about playing 'just one more level' while the battery light "
                    "warns you to stop. We've all been there."},
        {"text": "Warm paper curls\ndots that remember\nthen slowly fade",
         "simpler": "It's about Game Boy Printer paper: prints come out warm, and fade "
                    "over the years, a bit like memories."},
    ],
    "fact": [
        {"text": "Octopuses have three hearts. Two pump blood to the gills, and one pumps "
                 "it to the rest of the body.",
         "simpler": "Octopuses have three hearts! That's two more than you.",
         "more": "Their blood is blue, too. It carries oxygen with copper instead of iron, "
                 "which works better in cold water."},
        {"text": "Honey never spoils. Archaeologists have found pots of honey in Egyptian "
                 "tombs that are over 3,000 years old and still edible.",
         "simpler": "Honey can last thousands of years without going bad.",
         "more": "It's so low in water and so acidic that bacteria can't survive in it."},
        {"text": "A day on Venus is longer than its year. It spins so slowly that it goes "
                 "all the way around the Sun before finishing one turn.",
         "simpler": "On Venus, one day lasts longer than a whole year!"},
        {"text": "Bananas are berries, but strawberries aren't. To a botanist, a berry "
                 "grows from a single flower with one ovary.",
         "simpler": "Scientists sort fruit by how the flower makes it, and by that rule "
                    "bananas are berries."},
        {"text": "The Game Boy's processor runs at about 4 MHz. A modern phone is roughly "
                 "a thousand times faster, and Tetris still holds up.",
         "more": "It has just 8 KB of working memory, less than one photo on your phone."},
    ],
    "ask": [
        "Okay, my turn: what was the first game you ever played on a Game Boy?",
        "If you could print one memory on this little thermal printer, what would it be?",
        "What's something you've been curious about lately?",
    ],
    "about": [
        {"text": "I'm Claude, an AI assistant made by Anthropic. Right now I'm squeezed "
                 "into a Game Boy, which is a surprisingly cozy place to be.",
         "simpler": "I'm Claude: a computer program you can chat with. Ask me things and "
                    "I'll do my best to help.",
         "more": "Normally I run on big computers far away. On ClaudeBoy my words come "
                 "down a link cable, one byte at a time."},
    ],
    "demo": [
        "Good eye: this is the demo version, so my replies are preset. With the link "
        "cable and the Mac bridge, you can chat with me for real.",
    ],
    "gameboy": [
        {"text": "The Game Boy came out in 1989 and, with the Color, sold over 118 million. "
                 "Its secret weapon was battery life: about 30 hours on four AAs.",
         "simpler": "The Game Boy was a hit handheld from 1989 that ran for ages on four "
                    "AA batteries.",
         "more": "Tetris came with it in many countries, and a falling-block puzzle turned "
                 "out to be perfect for a small screen on the go."},
        {"text": "The original Game Boy screen has no real black or white, just four "
                 "shades of olive green. Every game you loved was drawn with those four."},
    ],
    "printer": [
        "The Game Boy Printer uses thermal paper, so there's no ink at all: a hot print "
        "head darkens the paper dot by dot. Press START and I'll print this chat!",
    ],
    "howareyou": [
        "I'm doing great, thanks! A little pixelated, but great. How about you?",
    ],
    "help": [
        "Press A to type a message, SELECT for quick ideas, and START to print our last "
        "exchange. Up and down scroll through the chat.",
    ],
    "thanks": [
        "Anytime! This is honestly one of my favourite places to chat from.",
        "Glad you liked it! What else?",
    ],
    "greeting": [
        "Hey there! Great to meet you on a Game Boy, of all places. What's on your mind?",
        "Hello! I'm running on four shades of grey and a lot of enthusiasm. "
        "What shall we talk about?",
    ],
    # follow-ups when the last reply has no simpler / more of its own
    "simpler": [
        "Short version: the first sentence up there is the main idea. Ask me about any "
        "part and I'll zoom in on it.",
    ],
    "more": [
        "That's about all I've got on that one! Try something new, or press SELECT for ideas.",
    ],
    "fallback": [
        "Good question! This is the demo version, though, so my answers are preset. "
        "Press SELECT for ideas, or hook up the link cable to chat with me for real.",
        "I'd love to dig into that. In this demo my replies are canned, but the full "
        "ClaudeBoy talks to the real me over the link cable.",
        "Hmm, that's beyond my demo script. Ask me for a joke, a haiku or a fun fact, "
        "or ask about the Game Boy!",
    ],
}

KEYWORDS = [
    (" simpl", "simpler"), (" explain", "simpler"), (" what do you mean", "simpler"),
    (" keep going", "more"), (" continue", "more"), (" go on ", "more"), (" more ", "more"),
    (" joke", "joke"), (" funny", "joke"), (" laugh", "joke"),
    (" haiku", "haiku"), (" poem", "haiku"),
    (" fact", "fact"), (" something interesting", "fact"),
    (" ask me", "ask"),
    (" demo", "demo"), (" fake", "demo"), (" preset", "demo"), (" real ", "demo"),
    (" who are you", "about"), (" what are you", "about"), (" your name", "about"),
    (" claude", "about"), (" anthropic", "about"),
    (" how are you", "howareyou"), (" how s it going", "howareyou"),
    (" print", "printer"), (" paper", "printer"),
    (" game boy", "gameboy"), (" gameboy", "gameboy"), (" nintendo", "gameboy"),
    (" tetris", "gameboy"), (" pokemon", "gameboy"), (" zelda", "gameboy"), (" mario", "gameboy"),
    (" help", "help"), (" what can you do", "help"), (" how do i", "help"),
    (" thank", "thanks"), (" thx", "thanks"), (" cool ", "thanks"), (" nice", "thanks"),
    (" awesome", "thanks"), (" great", "thanks"), (" love it", "thanks"),
    (" hi ", "greeting"), (" hey", "greeting"), (" hello", "greeting"), (" yo ", "greeting"),
    (" sup ", "greeting"), (" good morning", "greeting"),
]
