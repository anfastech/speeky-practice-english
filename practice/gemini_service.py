import json
import re
import os
import time
import tempfile
from pathlib import Path
from django.conf import settings

from google import genai
from google.genai import types

client = genai.Client(api_key=settings.GEMINI_API_KEY)

# Model fallback chain
MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite-preview-06-17",
]


def extract_json(text):
    """Extract JSON object from text, stripping any markdown fences."""
    try:
        # Strip ```json ... ``` fences
        text = re.sub(r'```(?:json)?\s*', '', text).strip('`').strip()
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return None


def build_history_text(history):
    if not history:
        return "This is the very first message — no previous exchanges."
    lines = []
    for turn in history:
        label = "Student" if turn['role'] == 'user' else "AI (as persona)"
        lines.append(f"{label}: {turn['text']}")
    return "\n".join(lines)


def build_prompt(scenario, history, user_text=None):
    history_text = build_history_text(history)
    turn_number = len([t for t in history if t['role'] == 'user']) + 1
    is_last_turn = turn_number >= 3
    session_complete_val = "true" if is_last_turn else "false"

    if user_text is None:
        student_input_line = "THE STUDENT SPOKE (audio is attached — transcribe what you hear exactly):"
    else:
        student_input_line = f'THE STUDENT TYPED: "{user_text}"'

    final_note = (
        "This is the LAST turn. Set session_complete to true. Give a warm, encouraging final summary in feedback fields."
        if is_last_turn
        else f"This is turn {turn_number} of 3. Set session_complete to false. Keep the conversation going naturally."
    )

    prompt = f"""You are playing the role of: {scenario['ai_persona']}.
Character description: {scenario['ai_persona_description']}

SCENARIO: {scenario['situation_text']}

CONVERSATION HISTORY:
{history_text}

{student_input_line}

YOUR TASKS:
1. Respond naturally as the {scenario['ai_persona']} — short, conversational, 1-3 sentences
2. Evaluate the student's English: fluency, grammar, tone/politeness
3. Give one Manglish (Malayalam-English mix) tip — like a helpful friend would say it
4. Suggest 1-2 better phrases with English phonetic guide (stress in CAPITALS)

RULES:
- Always be warm and encouraging. Never harsh or discouraging.
- Manglish tip: mix Malayalam words naturally (e.g. "Ingane parayumbol more polite aakum: ...")
- Score: 60-100 range for reasonable attempts. Only below 60 for very poor effort.
- Phonetic example: "could I have" → "kud AY hav"
- {final_note}

RESPOND IN THIS EXACT JSON FORMAT ONLY (no markdown, no code blocks, no extra text):
{{
  "student_said": "exact words the student said",
  "ai_reply": "your natural response as {scenario['ai_persona']}",
  "session_complete": {session_complete_val},
  "manglish_hint": "short encouraging tip mixing Malayalam and English",
  "feedback": {{
    "overall_score": 75,
    "fluency": "one sentence feedback on speaking flow",
    "grammar": "one specific grammar tip",
    "tone": "one sentence on politeness / tone",
    "better_phrases": [
      {{"phrase": "better way to say it", "phonetic": "BEH-ter WAY tuh SAY it"}}
    ]
  }}
}}"""
    return prompt


def _call_gemini_text(prompt):
    """Call Gemini with text-only prompt, trying model fallbacks."""
    for model_id in MODELS:
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=prompt
            )
            if response and response.text:
                result = extract_json(response.text)
                if result:
                    return result
                print(f"[SPEEKY] {model_id} returned non-JSON: {response.text[:200]}")
        except Exception as e:
            print(f"[SPEEKY] {model_id} failed: {e}")
            continue
    return None


def _call_gemini_audio(prompt, file_part):
    """Call Gemini with prompt + audio file part, trying model fallbacks."""
    for model_id in MODELS:
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=[prompt, file_part]
            )
            if response and response.text:
                result = extract_json(response.text)
                if result:
                    return result
                print(f"[SPEEKY] {model_id} returned non-JSON: {response.text[:200]}")
        except Exception as e:
            print(f"[SPEEKY] {model_id} failed: {e}")
            continue
    return None


def chat_with_text(scenario, history, user_text):
    """Process a text turn and return structured feedback."""
    prompt = build_prompt(scenario, history, user_text)
    result = _call_gemini_text(prompt)

    if result:
        # Ensure student_said is set to what they typed
        if not result.get('student_said'):
            result['student_said'] = user_text
        return result

    return _fallback_response(user_text)


def chat_with_audio(scenario, history, audio_file):
    """Upload audio to Gemini, transcribe + evaluate in one call."""
    # Detect MIME type
    content_type = getattr(audio_file, 'content_type', '') or ''
    if not content_type or content_type == 'application/octet-stream':
        ext = os.path.splitext(audio_file.name or '')[1].lower()
        mime_map = {
            '.webm': 'audio/webm', '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4',
            '.ogg': 'audio/ogg', '.flac': 'audio/flac',
        }
        content_type = mime_map.get(ext, 'audio/webm')

    # Write to temp file
    suffix = '.webm' if 'webm' in content_type else '.wav'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        for chunk in audio_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    uploaded = None
    try:
        upload_config = types.UploadFileConfig(mime_type=content_type)
        uploaded = client.files.upload(file=Path(tmp_path), config=upload_config)

        # Wait for processing
        for _ in range(20):
            if uploaded.state.name != "PROCESSING":
                break
            time.sleep(1)
            uploaded = client.files.get(name=uploaded.name)

        if uploaded.state.name == "FAILED":
            raise RuntimeError("Gemini audio processing failed")

        file_part = types.Part.from_uri(
            file_uri=uploaded.uri,
            mime_type=content_type
        )

        prompt = build_prompt(scenario, history, user_text=None)
        result = _call_gemini_audio(prompt, file_part)

        if result:
            return result

        raise RuntimeError("No valid JSON from Gemini audio models")

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        if uploaded:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass


def _fallback_response(user_text=""):
    return {
        "student_said": user_text,
        "ai_reply": "Sorry, I couldn't process that. Could you try again?",
        "session_complete": False,
        "manglish_hint": "Worries venda! Oru kooree try cheyyuka.",
        "feedback": {
            "overall_score": 50,
            "fluency": "Please try again",
            "grammar": "Please try again",
            "tone": "Please try again",
            "better_phrases": []
        }
    }
