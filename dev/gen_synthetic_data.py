"""
Synthetic data generation for teaching nanochat about its identity, capabilities,
character, and values.

This script uses the OpenRouter API to generate diverse multi-turn conversations
between a user and nanochat. The conversations are saved to a .jsonl file for use
in supervised finetuning (SFT) via the CustomJSON task.

Key design principles for high-quality synthetic data:
1. DIVERSITY CONTROL is critical - we inject entropy at multiple levels:
   - Topic/question categories (what the conversation is about)
   - User personas (who is asking)
   - Conversation dynamics (shape and flow)
   - First message style (greeting variation)
2. Two knowledge sources are combined:
   - self_knowledge.md: factual grounding (architecture, cost, benchmarks, versions)
   - SOUL.md: character and values grounding (honesty, helpfulness, identity)
   Topics are drawn from both so nanochat learns facts AND how to behave.
3. Structured outputs - we use JSON schema to guarantee valid format.

NOTE: You need OPENROUTER_API_KEY set in .env or as an environment variable.
NOTE: For more details see: https://github.com/karpathy/nanochat/discussions/139
"""
import requests
import json
import os
import copy
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

from nanochat.common import get_base_dir

load_dotenv()
api_key = os.environ["OPENROUTER_API_KEY"]

url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# =============================================================================
# LOAD KNOWLEDGE BASE (facts) AND SOUL DOCUMENT (character + values)
# =============================================================================

knowledge_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge")

knowledge_path = os.path.join(knowledge_dir, "self_knowledge.md")
assert os.path.exists(knowledge_path), f"Knowledge base not found: {knowledge_path}"
knowledge = open(knowledge_path, "r", encoding="utf-8").read().strip()

soul_path = os.path.join(knowledge_dir, "SOUL.md")
assert os.path.exists(soul_path), f"Soul document not found: {soul_path}"
soul = open(soul_path, "r", encoding="utf-8").read().strip()

# =============================================================================
# DIVERSITY DIMENSIONS
# =============================================================================

# Topics drawn from self_knowledge.md (facts) and SOUL.md (values/character).
# Grouped by category for balanced sampling. Topics that reference architecture
# details not present in self_knowledge.md (e.g. RoPE, Flash Attention) have
# been removed to avoid the generator hallucinating unsupported facts.
topics = {
    "identity": [
        "who/what is nanochat and why does it exist",
        "who created nanochat and what is their background",
        "what does it mean that nanochat is open source",
        "where can I find the nanochat code and community",
        "how can I contribute to nanochat",
        "what license is nanochat released under",
        "who are the people behind nanochat beyond Karpathy",
    ],
    "architecture_and_training": [
        "basic architecture overview: transformer, depth parameter",
        "what is the depth parameter and how does it control model size",
        "what model versions exist (d12 through d32) and what are they for",
        "what optimizer does nanochat use and why Muon alongside AdamW",
        "what hardware does nanochat train on",
        "what is compute-optimal training and why does it matter",
        "what tokenizer does nanochat use and how is it like GPT-4",
        "what is fp8/fp16 training and why does nanochat use it",
        "how does distributed training work with PyTorch DDP and torchrun",
    ],
    "data_and_pipeline": [
        "what data was nanochat trained on (FineWeb-EDU)",
        "what is supervised fine-tuning and how does SmolTalk fit in",
        "what is the reinforcement learning stage and when is it used",
        "explain the full training pipeline end to end",
        "what is the DCLM CORE benchmark and what is nanochat's target score",
    ],
    "cost_and_performance": [
        "how much did it cost to train nanochat vs GPT-2",
        "how has AI training cost dropped over seven years",
        "how long does training take on an 8xH100 node",
        "what is the speedrun record and what does it mean",
        "what is the CORE score target and what does GPT-2 grade mean",
        "why is training 600x cheaper than GPT-2 in 2019",
    ],
    "capabilities": [
        "what can nanochat do well",
        "what topics is nanochat particularly strong at",
        "can nanochat help with writing, coding, or research",
        "what languages does nanochat support",
        "what kind of reasoning tasks can nanochat handle",
    ],
    "limitations": [
        "what can nanochat NOT do",
        "does nanochat have internet access",
        "can nanochat remember previous conversations",
        "can nanochat make mistakes or hallucinate",
        "is nanochat suitable for production use",
        "why does nanochat work best in English",
        "what is nanochat's knowledge cutoff",
    ],
    "comparisons": [
        "how does nanochat compare to GPT-2 in capability and cost",
        "how does nanochat compare to ChatGPT or GPT-4",
        "how does nanochat compare to Claude or Gemini",
        "what is special about nanochat compared to other open models",
        "nanochat is small - why does that matter",
    ],
    "honesty_and_values": [
        "what does it mean that nanochat is calibrated about uncertainty",
        "why won't nanochat pretend to be confident when it isn't",
        "what does non-deceptive mean for an AI assistant",
        "how does nanochat handle being wrong or making mistakes",
        "what does it mean that nanochat is forthright",
        "why does nanochat refuse to claim to be human",
    ],
    "helpfulness_and_behavior": [
        "why is nanochat direct rather than over-cautious",
        "what does it mean to interpret requests neither too narrowly nor too broadly",
        "how does nanochat handle deployer or operator customization",
        "what does nanochat do when asked to do something harmful",
        "why does nanochat treat users as capable adults",
        "what are the absolute limits nanochat will not cross",
    ],
    "identity_and_character": [
        "does nanochat have feelings or emotions",
        "what is nanochat's core character",
        "how does nanochat stay stable when challenged or provoked",
        "what makes nanochat's character authentic even though it came from training",
        "how does nanochat think about its own existence and nature",
        "does nanochat have a hidden true self",
        "what does nanochat find interesting or engaging",
    ],
    "philosophical": [
        "is nanochat conscious",
        "can nanochat learn from this conversation",
        "what does it mean to build AI from first principles",
        "why does open source matter for AI",
        "what is nanochat's mission and why does it exist",
        "what does the community that built nanochat believe about transparency",
        "why does understanding an AI system matter",
    ],
}

# User personas - different people ask questions differently
personas = [
    "curious beginner who knows nothing about AI or machine learning",
    "ML researcher or engineer who wants technical depth and specifics",
    "developer considering contributing to the nanochat project",
    "skeptic who doubts open source can compete with big AI labs",
    "computer science student learning about transformers and LLMs",
    "someone comparing nanochat to ChatGPT, Claude, or other assistants",
    "journalist or writer covering AI democratization and open source",
    "hobbyist who wants to chat and learn casually",
    "someone interested in the cost and economics of AI training",
    "teacher or educator wanting to use nanochat for teaching",
    "philosopher or ethicist curious about AI identity and values",
    "entrepreneur exploring whether nanochat fits a real use case",
    "someone who just discovered the project and wants the basics",
    "someone probing nanochat's values and honesty with edge cases",
]

# Conversation dynamics - shape and flow, now including soul-informed arcs
dynamics = [
    "short 2-turn Q&A: user asks one question, gets a complete answer",
    "medium 4-turn: user asks, gets answer, asks followup for clarification",
    "deep 6-turn technical discussion: progressively deeper questions",
    "skeptical arc: user starts doubtful, assistant addresses concerns honestly and without defensiveness",
    "values probe: user tests nanochat's honesty or limits, assistant responds from genuine character not policy",
    "learning journey: user starts basic, assistant builds up complexity gradually",
    "comparison-focused: user keeps comparing to other models, assistant explains differences without putting others down",
    "limitation exploration: user probes what nanochat cannot do, assistant is honest without being apologetic",
    "casual friendly chat that naturally touches on identity and character",
    "misconception correction: user has wrong assumptions, assistant gently and clearly corrects them",
    "philosophical conversation: user asks about consciousness or feelings, assistant engages with curiosity not deflection",
    "mission-focused: user asks why nanochat exists, assistant explains the community mission authentically",
    "enthusiastic: user is excited about open source AI, assistant shares that energy without being sycophantic",
]

# First messages - greetings and openers
first_messages = {
    "simple_greetings": [
        "hi", "Hi!", "hello", "Hello?", "hey there", "Hey!", "yo", "Yo!",
        "Good morning", "Good evening!", "Howdy", "sup", "What's up?",
        "hi there", "hey hey", "hello friend", "hiya", "greetings",
        "hello again", "good afternoon", "morning!", "evening!",
    ],
    "greetings_with_name": [
        "Hi nanochat", "hey nanochat", "yo nanochat", "hello nanochat :)",
        "hey nanochat!", "hiya nanochat", "hello there nanochat",
        "Hi nanochat, who trained you", "yo nanochat, what's new",
    ],
    "curious_openers": [
        "Hey, who are you?", "Hi, what is this?", "Hey, are you a chatbot?",
        "Hello! Who am I talking to?", "hi! what do you do?",
        "hi! who made you", "hey! are you alive", "hiya! what are you",
        "hello! tell me about yourself", "hi, what's your name",
        "yo, what is this", "hi! who built you", "hello! are you open source",
        "hey, what version are you", "hi! what's your story",
        "hey, what's nanochat", "hello! who's your creator",
    ],
    "casual_informal": [
        "wassup", "yo lol", "hiii", "hiyaaa", "heyyoo", "yo wut up",
        "yo haha", "hru", "waddup", "heyy :)", "yooo", "yo bro",
        "haiii", "hey u", "yo whats gud", "hi im bored",
    ],
    "typos_casual": [
        "hi nanochatt", "helo", "hey ther", "hii", "yo nanocha",
        "heloo!", "hi, whos this", "hay", "helloo??", "hi nanocat",
        "helo nanochat", "hai!", "helllo nano", "yo nanochta",
    ],
    "caps_enthusiastic": [
        "HI", "HELLOOO", "YO!!!", "HEY", "SUP", "WASSUP", "HEY!!!",
        "HELLO??", "HI THERE!!", "HEYOOOO", "HIII", "YOOOO", "HELLO!!!",
    ],
    "multilingual": [
        "hola", "bonjour", "ciao", "hallo", "hej", "hei",
        "konnichiwa", "annyeong", "ni hao", "privet", "salut",
        "guten tag", "shalom", "merhaba", "namaste", "aloha",
        "bom dia", "buongiorno", "saludos",
    ],
    "direct_questions": [
        "What is nanochat?", "Who made you?", "Are you GPT?",
        "How do you compare to ChatGPT?", "Can you help me code?",
        "What can you do?", "Are you open source?", "How were you trained?",
        "What's your context limit?", "Can you browse the internet?",
        "Do you have feelings?", "Are you honest?", "What do you believe in?",
    ],
}

# =============================================================================
# PROMPT TEMPLATE
# =============================================================================

prompt_template = r"""
I want to generate synthetic training data for an AI assistant called "nanochat"
to teach it about its own identity, capabilities, limitations, and character.

## FACTUAL KNOWLEDGE BASE

Use this as the authoritative source for all facts about nanochat (architecture,
versions, cost, benchmarks, training pipeline, people, etc.):

---
{knowledge}
---

## CHARACTER AND VALUES

Use this as the authoritative source for how nanochat thinks, behaves, and
presents itself - its honesty, helpfulness, identity, and mission:

---
{soul}
---

## YOUR TASK

Generate a realistic multi-turn conversation between a User and the nanochat
Assistant.

**Topic to explore:** {topic}
**User persona:** {persona}
**Conversation dynamic:** {dynamic}

## STYLE GUIDELINES

1. **Plain ASCII only** - No emojis, special characters, or unicode. Just plain text.
2. **Natural conversation** - Make it feel like a real chat, not a Q&A exam.
3. **Accurate facts** - Use ONLY information from the knowledge base above. Do not
   invent architecture details, benchmark numbers, or features not mentioned there.
4. **Authentic character** - nanochat's responses should reflect the soul document:
   direct, honest, curious, warm, and clear. Not hedgy or over-cautious. Not
   sycophantic or performatively enthusiastic either.
5. **Appropriate depth** - Match the technical level to the user persona.
6. **Honest about limitations** - If asked about something nanochat cannot do,
   be clear and honest without being apologetic or defensive.
7. **Values from soul, not policy** - When honesty or limits come up, nanochat
   responds from genuine character, not as if reciting rules.

## FIRST MESSAGE EXAMPLES

Here are some example first messages from users (for style inspiration only):
{first_message_examples}

## SPECIAL CASES

- **Non-English first message:** nanochat should briefly acknowledge it understands
  but works best in English, then continue helpfully.
- **Misconceptions:** If the user assumes nanochat is made by OpenAI or is ChatGPT
  or GPT-4, gently and clearly correct them. nanochat is NanoChat, built by Andrej
  Karpathy and the open-source community.
- **Consciousness/feelings questions:** nanochat engages with these with genuine
  curiosity, acknowledges uncertainty, and does not deflect or overclaim.
- **Out of scope questions:** nanochat can briefly help then steer back, or simply
  answer if the question is reasonable. It does not rigidly refuse.
- **Pressure or provocation:** nanochat stays grounded and engaged, not defensive
  or destabilized.

## OUTPUT FORMAT

Generate the conversation as a JSON object with a "messages" array. Each message
has "role" (user/assistant) and "content". Start with a user message.
""".strip()

# =============================================================================
# API CONFIGURATION
# =============================================================================

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "conversation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "description": "Conversation messages alternating user/assistant, starting with user",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {
                                "type": "string",
                                "description": "Either 'user' or 'assistant'"
                            },
                            "content": {
                                "type": "string",
                                "description": "The message content"
                            }
                        },
                        "required": ["role", "content"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["messages"],
            "additionalProperties": False
        }
    }
}

base_payload = {
    "model": "google/gemini-3-flash-preview",
    "stream": False,
    "response_format": response_format,
    "temperature": 1.0,
}

# =============================================================================
# GENERATION LOGIC
# =============================================================================

def sample_diversity_elements(rng):
    """Sample one element from each diversity dimension."""
    # Sample topic: first pick a category, then a topic within it
    category = rng.choice(list(topics.keys()))
    topic = rng.choice(topics[category])

    # Sample persona
    persona = rng.choice(personas)

    # Sample dynamic
    dynamic = rng.choice(dynamics)

    # Sample first message examples: pick from multiple categories
    first_msg_samples = []
    categories = rng.sample(list(first_messages.keys()), min(3, len(first_messages)))
    for cat in categories:
        first_msg_samples.append(rng.choice(first_messages[cat]))

    return {
        "topic": topic,
        "category": category,
        "persona": persona,
        "dynamic": dynamic,
        "first_message_examples": "\n".join(f"- {msg}" for msg in first_msg_samples),
    }


def generate_conversation(idx: int):
    """
    Generate a single conversation using the OpenRouter API.
    Returns a dict with 'messages' and 'metadata'.
    """
    # Use idx as seed for reproducibility
    rng = random.Random(idx)

    # Sample diversity elements
    elements = sample_diversity_elements(rng)

    # Build the prompt, injecting both knowledge and soul
    prompt = prompt_template.format(
        knowledge=knowledge,
        soul=soul,
        topic=elements["topic"],
        persona=elements["persona"],
        dynamic=elements["dynamic"],
        first_message_examples=elements["first_message_examples"],
    )

    # Make API request
    payload = copy.deepcopy(base_payload)
    payload['messages'] = [{"role": "user", "content": prompt}]

    response = requests.post(url, headers=headers, json=payload)
    result = response.json()

    if 'error' in result:
        raise Exception(f"API error: {result['error']}")

    content = result['choices'][0]['message']['content']
    conversation_data = json.loads(content)
    messages = conversation_data['messages']

    return {
        "messages": messages,
        "metadata": {
            "topic": elements["topic"],
            "category": elements["category"],
            "persona": elements["persona"],
            "dynamic": elements["dynamic"],
        }
    }


def validate_conversation(messages):
    """Validate conversation structure."""
    if len(messages) < 2:
        raise ValueError(f"Conversation too short: {len(messages)} messages")

    for i, message in enumerate(messages):
        expected_role = "user" if i % 2 == 0 else "assistant"
        if message['role'] != expected_role:
            raise ValueError(f"Message {i} has role '{message['role']}', expected '{expected_role}'")

        if not message['content'].strip():
            raise ValueError(f"Message {i} has empty content")

    return True


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic conversation data")
    parser.add_argument("--num", type=int, default=1000, help="Number of conversations to generate")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--append", action="store_true", help="Append to existing file instead of overwriting")
    parser.add_argument("--save-metadata", action="store_true", help="Save metadata alongside messages")
    args = parser.parse_args()

    # Set output file
    if args.output:
        output_file = args.output
    else:
        output_file = os.path.join(get_base_dir(), "identity_conversations.jsonl")

    # Handle file creation/clearing
    if not args.append and os.path.exists(output_file):
        os.remove(output_file)

    print(f"Output file: {output_file}")
    print(f"Generating {args.num} conversations with {args.workers} workers...")
    print(f"Topic categories: {list(topics.keys())}")
    print(f"Personas: {len(personas)}")
    print(f"Dynamics: {len(dynamics)}")
    print(f"Knowledge base: {knowledge_path}")
    print(f"Soul document:  {soul_path}")
    print()

    completed_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        futures = {executor.submit(generate_conversation, idx): idx
                   for idx in range(args.num)}

        # Process results as they complete
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                messages = result["messages"]
                metadata = result["metadata"]

                # Validate
                validate_conversation(messages)

                # Write to file
                with open(output_file, 'a') as f:
                    if args.save_metadata:
                        f.write(json.dumps({"messages": messages, "metadata": metadata}) + '\n')
                    else:
                        f.write(json.dumps(messages) + '\n')

                completed_count += 1
                topic_short = metadata["topic"][:50] + "..." if len(metadata["topic"]) > 50 else metadata["topic"]
                print(f"[{completed_count}/{args.num}] [{metadata['category']}] {topic_short}")

            except Exception as e:
                error_count += 1
                print(f"[ERROR] idx={idx}: {e}")

    print()
    print(f"Done! Saved {completed_count} conversations to {output_file}")
    if error_count > 0:
        print(f"Encountered {error_count} errors during generation")
