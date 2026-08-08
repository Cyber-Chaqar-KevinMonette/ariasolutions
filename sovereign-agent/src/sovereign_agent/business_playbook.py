"""business_playbook.py — curated secular business/leadership/negotiation
frameworks, deterministic and keyword-routed (same discipline as
consumer_law_companion.py / real_estate_strategy.py) rather than free-form
LLM generation.

Source: adapted from Ryan Blair's "Billion-Dollar Playbook" (AlterCall),
a free coaching deck Kevin was given. Reviewed the full 69-page deck
2026-08-02 and kept only the secular business/leadership/communication/
negotiation content. All prayer, confession, oath-to-the-Creator, and
scripture-citation material was deliberately left out per explicit user
direction (not softened or rephrased into euphemism — omitted entirely).
Individual entries below note where a bullet was dropped or reworded for
the same reason. This does not touch mos_canon.py or any values/behavior
gate — it is reference knowledge Aria can look up, not doctrine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


__all__ = ["Framework", "SOURCE_NOTE", "PLAYBOOK", "CATEGORIES", "find_frameworks"]

SOURCE_NOTE = (
    "Adapted from Ryan Blair's Billion-Dollar Playbook (AlterCall); "
    "religious content omitted per user direction."
)


@dataclass(frozen=True)
class Framework:
    name: str
    category: str
    steps: tuple[str, ...]
    principles: tuple[str, ...]
    keywords: tuple[str, ...]
    source: str = SOURCE_NOTE


PLAYBOOK: tuple[Framework, ...] = (
    Framework(
        name="Purpose Statement",
        category="purpose",
        steps=(
            "What problem do you love to solve?",
            "What makes you take a stand?",
            "You are most qualified to serve the person you used to be.",
            "What combination of values points to what you can do for others?",
            "My purpose is to ___ for people, so they can ___.",
            "I am ___ who guides people to ___.",
            "I help people go from (pain) ___ to (pleasure) ___ by way of (new way) ___ without (old way) ___.",
            "I do ___ so that ___.",
        ),
        principles=(
            "Purpose first!",
            '"Your life is your message." — Gandhi',
            "I am who I am today, because I was who I was yesterday.",
            "Your desire has a desire.",
            "Take required action and inspired action will come.",
            "You're either taking action from inspiration or desperation.",
        ),
        keywords=("purpose", "mission statement", "why", "purpose statement"),
    ),
    Framework(
        name="Restriction (Discipline Building)",
        category="discipline",
        steps=(
            "Restriction builds willpower, self-control and discipline.",
            "You have to restrict small light for big light — say no to something so you can say yes to something better.",
            "Write out your goals. What do you have to restrict to get there?",
            "Start small — what is one thing you need to restrict to become more disciplined?",
            "How long are you going to restrict it for?",
            "What do you have to gain by restricting it?",
        ),
        principles=(
            "New level. New devil.",
            "Suffering is a great teacher.",
            "Concentration leads to mastery, distraction leads to misery.",
            "If it's important you'll find a way, if not you'll find an excuse.",
            "If you can't learn to love small lessons, you'll learn to love big ones.",
            "Restriction + sharing = manifestation.",
        ),
        keywords=("restriction", "discipline", "willpower", "self-control", "habit"),
    ),
    Framework(
        name="Gamify Your Growth",
        category="discipline",
        steps=(
            "Stepping out of your comfort zone = 10 points.",
            "Restrict a reaction = 10 points.",
            "Healing a trigger = 20 points.",
            "Random act of kindness = 20 points.",
            "Fill your cup = 10 points.",
            "Giving without desire to receive = 20 points.",
            "Treating others as you'd want to be treated = 20 points.",
            "Restricting small light for big light = 10 points.",
            "Forgiving = 15 points.",
            "Sharing light = 20 points.",
            "Removing distractions = 20 points.",
            "Action: write your gamification list now. Minimum goal = 100 points a day for 90 days consecutively.",
        ),
        principles=(
            "Healing = growth & growth = healing.",
            "Lessons repeat, until they are learned.",
            "Work on your triggers so they don't work on you.",
            "You can't serve from an empty cup.",
            "I am the light I see in others.",
        ),
        keywords=("gamify", "gamification", "points system", "growth game", "habit tracker"),
    ),
    Framework(
        name="Leadership Commitment (Oath)",
        category="leadership-commitment",
        steps=(
            "Only commit to what you will honor.",
            "Add body elements — what will you physically do to honor this?",
            "Add mind elements — what will you think/focus on?",
            "Add soul/inner-life elements — what does this mean to who you are?",
            "Add role elements — what does this require of you in your role?",
            "Add your vows — state them plainly.",
        ),
        principles=(
            "Answer the call.",
            "Duty is ours; results are not fully in our control.",
            "Integrity is the discipline to act on your principles.",
            "Learn to know yourself.",
            "A commitment you keep builds trust and self-respect; breaking it costs both.",
        ),
        keywords=("oath", "commitment", "leadership commitment", "vows"),
    ),
    Framework(
        name="How to Think",
        category="communication",
        steps=("Beliefs", "Values", "Principles", "Emotions"),
        principles=(
            "Adopt the belief that expands you the most.",
            "Labels are for shampoo.",
            "Be aware of BBC: belief broadcasting.",
            "Learn to think for yourself.",
            "The antidote to a negative thought is a positive thought. The cure is to eliminate the "
            "misconception or limiting belief that originated the thought in the first place.",
            "The truth is simple.",
            "Choose your frequency.",
            "Don't filter with fear.",
            "Mindfulness is injury free.",
        ),
        keywords=("how to think", "beliefs", "mindset", "thinking"),
    ),
    Framework(
        name="How to Speak",
        category="communication",
        steps=("Language", "L.A.R.A. — Listen, Affirm, Respond & Ask", "Conflict", "I/We framing"),
        principles=(
            "Find the love in each conversation.",
            "There's love in each encounter; you must learn to receive it.",
            "Tell better stories.",
            "My incoherence creates incoherence in others.",
        ),
        keywords=("how to speak", "lara", "communication style", "listening"),
    ),
    Framework(
        name="How to Act",
        category="communication",
        steps=("Practices.", "Presence.", "Priorities."),
        principles=(
            "Do, be, do, be, do.",
            "Actions = intentions minus misconceptions.",
            "Do everything you should do, then focus on everything you could do.",
            "Stay in the pocket.",
            "The source of truth is the calendar.",
            "Do the dishes.",
            '"When going through hell, keep going." — Churchill',
        ),
        keywords=("how to act", "practices", "presence", "priorities", "execution"),
    ),
    Framework(
        name="How to Forgive",
        category="forgiveness",
        steps=(
            "Consider: be honest — are you willing to forgive?",
            'Accept: "I accept that this happened."',
            "Acknowledge: journal the who, what, when, where, and how — be objective.",
            'Identify the Hook: what storyline are you clinging to? (e.g. "No one ever values me.")',
            "Identify the Price: what is this costing you? (energy, health, relationships, joy)",
            "Transmute: what do you want the pain to become? (empathy, growth, strength, softness)",
            "Extract: what lessons have you earned? Who have you become as a result?",
            "Repair: what does repair look like? If you're not ready, cultivate self-compassion.",
            "Compassion: put yourself in their shoes — write their story with empathy.",
            "Release: write a forgiveness letter to yourself and one to those who've wronged you.",
            "Visualize: see the bitterness turning to sweetness, the heaviness lifting.",
            "Practice daily: micro-forgiveness — forgive the small things.",
            "Teach: model forgiveness for your family, friends, and children.",
        ),
        principles=(
            "Forgiveness is not about the other person. It's about freeing yourself.",
            "Forgiveness does not require reconciliation or condoning bad behavior.",
            "We don't forgive because they deserve it; we forgive to create more light.",
            '"Forgiveness does not change the past, but it does enlarge the future." — Paul Boose',
            "Holding onto resentment only increases your own suffering. Healing is feeling.",
        ),
        keywords=("forgive", "forgiveness", "resentment", "letting go"),
    ),
    Framework(
        name="Apology",
        category="communication",
        steps=(
            "Be genuine and show remorse.",
            "Make space for the other person's process.",
            "Be specific about what you are sorry for.",
            "Explain how you have changed because of this mistake.",
            "Explain why this mistake will not happen again.",
            "Honor their process — don't make them feel wrong for not receiving the apology immediately.",
            "Commit to working together to heal the relationship.",
        ),
        principles=("The best apology is changed behavior.",),
        keywords=("apology", "sorry", "repair relationship", "how to apologize"),
    ),
    Framework(
        name="Communicating in Difficult Times",
        category="communication",
        steps=(
            "Begin with the end in mind.",
            "Be aware of your body and state before engaging.",
            "Listen with the desire to understand.",
            "Ask open-ended questions.",
            "Don't be attached to an outcome.",
            "Don't compare experiences — they want to share theirs, not hear yours.",
            "If you can't be present, excuse yourself.",
            "Avoid emotionally charged text/email — prefer in person, call, or voicenote.",
            'Avoid "you told me that already" — say "I remember you sharing."',
            'Before speaking, ask "is there anything else?"',
        ),
        principles=(
            "Correct with kindness.",
            "Listen to the notes behind the music.",
            "Share your truth with love and compassion.",
            "Connect before you direct and correct.",
            "Have the meeting before the meeting.",
            "Focus on facts.",
            "Never make matters worse.",
        ),
        keywords=("difficult conversation", "hard conversation", "conflict communication"),
    ),
    Framework(
        name="Reality Bridge (Breaking Through the Ego)",
        category="conflict",
        steps=(
            "Open your heart and let them off the hook.",
            "Take responsibility for your part of the problem.",
            "Let go of being right.",
            "Admit you may be wrong.",
            "Show you care — say no with an open heart.",
            "Hear no with an open heart.",
            'When attacked, the ego says: "That didn\'t happen" (denial), "You\'re making this bigger than '
            'it needs to be" (minimization), "This isn\'t my fault" (blame), "I have every right because '
            'you did Y" (justification).',
            'The heart instead says: "A story I made up is...", "I may be hallucinating...", "I might be '
            'misunderstanding...", "I\'m confused...", "May I have permission to share?"',
        ),
        principles=(
            "Be a reality bridge.",
            "Internal conflict = external conflict.",
            "Learn to say no with an open heart.",
            "If you take the high road it will never be crowded.",
            "The ego is undefeated.",
            "To solve a problem, all parties to it must take responsibility.",
            "The conflicts I have within myself are the root cause of the conflicts I have with others.",
            "Reset expectations frequently.",
            "It's not who's right, it's what's right.",
        ),
        keywords=("ego", "conflict resolution", "reality bridge", "defensive", "blame"),
    ),
    Framework(
        name="The 5 Levels of Trust",
        category="trust",
        steps=(
            "Level 1 — Risk Assessment: basic safety check, no red flags, move on.",
            "Level 2 — Evidence of Alignment: respect boundaries, gather data to see if trust can deepen.",
            "Level 3 — Consistency: observe actions over time, integrity and congruence matter.",
            "Level 4 — Courage: deeper vulnerability, emotional attunement, mutual support.",
            "Level 5 — Total Commitment: full trust, unconditional support, a sense of oneness.",
            "Few relationships reach Level 5 — these are the most precious ones.",
            "Don't mistake intensity for intimacy — true trust builds gradually.",
            "Boundaries and forgiveness: slow down; forgiveness is given, trust is earned.",
            "Compassion is action — show care through consistent deeds.",
        ),
        principles=(
            "Trust has levels.",
            "Show your thorns.",
            "The lower-self loves company; loneliness comes from bad company.",
            "Healing is painful.",
            "When you harm yourself, you invite others to harm you as well.",
            "Stop expecting honesty from those who lie to themselves.",
        ),
        keywords=("trust", "relationship levels", "building trust", "levels of trust"),
    ),
    Framework(
        name="Ignorance or Arrogance",
        category="leadership",
        steps=(
            "Ignorance: not knowing — gaps in skill, awareness, or information.",
            "Arrogance: thinking you already know — ego that resists feedback or growth.",
            "Every failure, conflict, missed opportunity, or burnout pattern traces back to one of these two.",
            "The cure: humility, curiosity, willingness to grow.",
        ),
        principles=(
            "I don't know, is the best philosophy.",
            "Question assumptions.",
            "Today's liberating insight becomes tomorrow's jail.",
            "When you stop learning, you start suffering.",
            '"No problem can be solved from the same level of consciousness that created it." — Einstein',
            '"Beware of unearned wisdom." — Jung',
        ),
        keywords=("ignorance", "arrogance", "humility", "failure analysis", "root cause"),
    ),
    Framework(
        name="TRACC (Crisis / Alignment Communication)",
        category="communication",
        steps=(
            "Truth — here's what we're up against.",
            "Resolve — we're going to get through it.",
            "Approach — here's how.",
            "Contribution — here's what I need from you.",
            "Commitment — can I count on you?",
        ),
        principles=(),
        keywords=("tracc", "crisis communication", "team alignment", "rally the team"),
    ),
    Framework(
        name="E3 (Energy, Execution, Excellence)",
        category="excellence",
        steps=(
            "Energy.",
            "Execution.",
            "Excellence.",
            "What. How. Who. Due date.",
        ),
        principles=(
            "If true = do.",
            "If it takes 2 minutes, do it now.",
            "Make things easy when times are hard, make things hard when times are easy.",
            "Excellence sells itself.",
            '"If you don\'t have time to do it right, when will you have time to do it over?" — Coach Wooden',
            "Replay the tape.",
            "Can you? Will you? By when?",
            "Execution is knowing what to do, how to do it, and having the integrity to do it.",
            "Plan your work, work your plan, stick to the plan.",
        ),
        keywords=("e3", "energy execution excellence", "accountability", "task ownership"),
    ),
    Framework(
        name="Elon Musk's 5-Step Algorithm",
        category="engineering",
        steps=(
            "1. Question the Requirements — 'your requirements are definitely dumb.' Challenge every "
            "assumption, even from experts. Ask: should this exist at all?",
            "2. Remove Unnecessary Steps — try hard to delete the part or process. Ruthlessly eliminate "
            "steps that don't add clear value; test the system after each deletion.",
            "3. Simplify and Optimize — only simplify or optimize AFTER questioning and deleting. Don't "
            "polish a process that should've been eliminated.",
            "4. Accelerate Time-to-Learning — shorten feedback cycles, but only after fixing the earlier "
            "steps; speed amplifies errors if done too early.",
            "5. Automate Last — automation should be the final step, not the first. Automating too early "
            "makes inefficiencies permanent; only automate simplified, proven processes.",
            "Sequence matters: Question → Delete → Simplify → Accelerate → Automate. Doing these out of "
            "order locks in inefficiencies.",
        ),
        principles=(
            '"If you need a machine and don\'t buy it, you\'ll pay for the machine and won\'t have it." '
            "— Henry Ford",
            "Simplicity is the ultimate sophistication.",
            "Seek simplicity. Iterate and innovate.",
            '"Never let a good crisis go to waste." — Churchill',
        ),
        keywords=("elon musk", "five step", "5-step", "simplify", "automate", "engineering process",
                  "systems design", "algorithm"),
    ),
    Framework(
        name="Team Leadership",
        category="leadership",
        steps=(
            "Be solution oriented, not problem oriented.",
            "Listen.",
            "Take action.",
            "Know the elements of a great leader.",
            "Set your intention.",
            "Commit to become your best.",
            "Eliminate your distractions.",
            "Prioritize by impact.",
            "Turn your routines into rituals.",
            "Train your attention.",
            "Execute responsibly.",
        ),
        principles=(
            "Help people help more people.",
            "Leadership is caring. Caring is planning.",
            "Responsibility = responsiveness.",
            "You train your people, or they will train you.",
            "Own your role.",
            "If you present a problem without a solution, you have become the problem.",
        ),
        keywords=("team leadership", "leading people", "management", "leadership"),
    ),
    Framework(
        name="Org & Strategy Frameworks (PSP / 3 P's / 70-20-10 / SMP=HPC)",
        category="strategy",
        steps=(
            "PSP: People + Structure + Process — integrate everything.",
            "3 P's: Projects, Programs, Products — if it doesn't scale, it doesn't sell.",
            "70-20-10: 70% on the core, 20% adjacent to the core, 10% on venture bets that could fail.",
            "SMP=HPC: Structure + Metrics × Purpose = High-Performance Culture.",
        ),
        principles=(
            "Integrate everything.",
            "If it doesn't scale, it doesn't sell.",
            "Every strategy has a half-life — ride the wave up, find a new wave on the way down.",
            "Know your input vs output ratio.",
            "The path is math.",
        ),
        keywords=("org design", "business structure", "resource allocation", "strategy", "high-performance culture"),
    ),
    Framework(
        name="A-Player Profile (Hiring Rubric)",
        category="hiring",
        steps=(
            "Seeking capacity + desire + purpose.",
            "Aim high — get people capable of doing significantly more volume than you're doing now.",
            "Look for serious hobbies.",
            "Find evidence of strong work ethic.",
            "'Who's right' vs 'what's right' attitude.",
            "Awareness of higher-self vs lower-self.",
            "Growth is their love language.",
            "Willing and capable of learning new skills.",
            "Loyal to the mission.",
            "They create meaning in the mundane.",
            "They celebrate challenges as an opportunity to grow.",
            "They solve problems with process.",
            "They attract and recruit other A-Players.",
            "They put the company first.",
            "They love winning — on time, on budget — and hate losing.",
            "They have a 5-year and 10-year vision.",
        ),
        principles=(
            "You must be radically self-reliant, responsible, extremely efficient, honest, and humble "
            "to work at a high level.",
            'When interviewing, just say "tell me more" and "how did you do it?"',
            "New person, new team.",
            "When you lower your standards, you lose the winners. When you raise your standards, you "
            "lose the losers.",
        ),
        keywords=("hiring", "a-player", "interviewing", "recruiting", "team building"),
    ),
    Framework(
        name="Negotiation — Prep & Mindset",
        category="negotiation",
        steps=(
            "Be prepared to walk away — it builds congruency and confidence, and signals your "
            "boundaries are firm.",
            "Master the language of agreement — your counterpart is testing your boundaries; "
            "compliment the attempt, hold firm.",
            "Always ask for a discount — it humbles you and reveals their price integrity.",
            "Deploy the contrast principle — let them experience the higher-priced option first so "
            "the lower-priced one feels lighter by comparison.",
            "Prepare pattern interrupts — aligned humor, naming excuses, shifting low energy to high.",
            "Prepare for C.R.A.P. — Criticism, Rejection, Antagonist, Pressure.",
            "Motion creates emotion — mirror body language, tone, and emotion.",
            "Set your state before each negotiation — clear distractions, assume you'll get the win, "
            "become fully present and focused, remind yourself of your why.",
        ),
        principles=(
            "Never let money stop you from executing on a good idea.",
            "Champions have short memories.",
            "The person who is most present and congruent wins.",
        ),
        keywords=("negotiation prep", "negotiating mindset", "walk away", "contrast principle"),
    ),
    Framework(
        name="Negotiation — Listening & Confirming",
        category="negotiation",
        steps=(
            "Listen with the intent to understand before sharing anything about your offering or pricing.",
            "Find out what they're seeking to gain and what they're afraid of losing.",
            "Explore their ideal outcome, then their lowest acceptable expectation.",
            "Confirm you understand all their needs by summarizing them.",
            "Confirm confidently that you can meet their needs before discussing price.",
            "Ask great questions (What / When / Why) to shift out of presentation mode.",
        ),
        principles=(
            "Facts tell, stories sell — stories move understanding from the conscious into the "
            "subconscious mind.",
            "In every conversation a sale is being made — either they're selling you, or you're "
            "selling them.",
            "The person who asks questions controls the conversation.",
        ),
        keywords=("negotiation listening", "discovery questions", "needs assessment", "active listening"),
    ),
    Framework(
        name="Negotiation — Closing",
        category="negotiation",
        steps=(
            "Pre-frame known objections before they're raised.",
            "Answer unspoken safety questions (how will this look/feel, is this safe, is it worth it) "
            "with stories and testimonials.",
            "Deploy silence deliberately — the first person to speak after an offer loses ground.",
            "Ask questions that surface a clarifying 'no' to get to the real objection.",
            "Summarize the agreement before closing — no summary, no agreement.",
            "Assert and honor deadlines; under-promise and over-deliver.",
            "Ask directly for the sale.",
            "Send paperwork within minutes of a yes — close the gap before motivation fades.",
            "Follow up on commitments within 12-24 hours.",
            "Celebrate only once funds have arrived — signing and funding are not the same thing.",
            "Use edification — introduce people and products with two or three facts and a feeling.",
        ),
        principles=(
            "Aim for an 85-90% success rate as the benchmark of a skilled negotiator.",
            "If you don't ask for the sale, you won't get the sale.",
            "We often celebrate too early.",
        ),
        keywords=("negotiation closing", "closing the deal", "follow up", "deadlines", "sales close"),
    ),
    Framework(
        name="Value Ladder",
        category="pricing",
        steps=(
            "People pay if it helps them make or save money.",
            "People pay if it helps them save time, or make time.",
            "People pay if it helps them reduce risk.",
            "People pay if it helps them elevate status.",
        ),
        principles=(
            "You don't build your business, your customers do.",
            "Know who is NOT your customer.",
        ),
        keywords=("value ladder", "pricing", "offer design", "customer value"),
    ),
)

CATEGORIES: frozenset[str] = frozenset(fw.category for fw in PLAYBOOK)


def _contains_phrase(haystack: str, needle: str) -> bool:
    """Whole-word/phrase containment, not raw substring — plain substring
    matching false-positived "ego" inside "negotiation" (e-g-o is a literal
    substring of n-e-g-o-t-i-a-t-i-o-n), pulling the wrong framework into
    every negotiation query. Word-boundary regex avoids that class of bug."""
    if not needle:
        return False
    return re.search(r"\b" + re.escape(needle) + r"\b", haystack) is not None


def find_frameworks(query: str, category: str | None = None) -> list[Framework]:
    """Keyword-match query against framework names/keywords, optionally filtered by category.

    Returns every match (unlike consumer_law_companion's single-best-match), since a user
    question may reasonably touch several frameworks (e.g. "negotiation" matches all three
    negotiation entries). An empty query with a category set browses that whole category.
    No match returns an empty list — the caller decides how to say so.

    Raises ValueError for an unrecognized category — a typo'd category (e.g. "negotiations")
    would otherwise silently return an empty list indistinguishable from a real no-match."""
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r} — valid categories: {sorted(CATEGORIES)}")
    lowered = (query or "").lower().strip()
    out = []
    for fw in PLAYBOOK:
        if category and fw.category != category:
            continue
        if not lowered:
            if category:
                out.append(fw)
            continue
        if (any(_contains_phrase(lowered, kw) or _contains_phrase(kw, lowered) for kw in fw.keywords)
                or _contains_phrase(fw.name.lower(), lowered)):
            out.append(fw)
    return out
