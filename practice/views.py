import json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .scenarios import SCENARIOS, DAILY_SCENARIOS, INTERVIEW_SCENARIOS
from .gemini_service import chat_with_text, chat_with_audio
from accounts.decorators import supabase_login_required


@supabase_login_required
def home(request):
    return render(request, 'practice/home.html', {
        'daily_scenarios': DAILY_SCENARIOS,
        'interview_scenarios': INTERVIEW_SCENARIOS,
    })


@supabase_login_required
def session(request, scenario_id):
    scenario = SCENARIOS.get(scenario_id)
    if not scenario:
        return redirect('home')

    # Reset session when arriving at a new scenario (or same scenario fresh start)
    if request.GET.get('reset') == '1' or request.session.get('scenario_id') != scenario_id:
        request.session['scenario_id'] = scenario_id
        request.session['history'] = []
        request.session['turn_count'] = 0
        request.session['session_complete'] = False
        request.session.modified = True

    return render(request, 'practice/session.html', {
        'scenario': scenario,
        'session_complete': request.session.get('session_complete', False),
    })


@supabase_login_required
@require_http_methods(["POST"])
def chat_api(request, scenario_id):
    scenario = SCENARIOS.get(scenario_id)
    if not scenario:
        return JsonResponse({'error': 'Scenario not found'}, status=404)

    if request.session.get('session_complete', False):
        return JsonResponse({'error': 'Session already complete. Reload to try again.'}, status=400)

    history = request.session.get('history', [])

    try:
        if 'audio' in request.FILES:
            audio_file = request.FILES['audio']
            result = chat_with_audio(scenario, history, audio_file)
        else:
            data = json.loads(request.body)
            user_text = data.get('text', '').strip()
            if not user_text:
                return JsonResponse({'error': 'No input provided'}, status=400)
            result = chat_with_text(scenario, history, user_text)

        # Update session history (keep it compact — text only)
        student_said = result.get('student_said', '')
        ai_reply = result.get('ai_reply', '')
        history.append({'role': 'user', 'text': student_said})
        history.append({'role': 'ai', 'text': ai_reply})

        request.session['history'] = history
        request.session['turn_count'] = request.session.get('turn_count', 0) + 1

        if result.get('session_complete', False):
            request.session['session_complete'] = True

        request.session.modified = True

        return JsonResponse({'success': True, **result})

    except Exception as e:
        print(f"[SPEEKY] Chat API error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@supabase_login_required
@require_http_methods(["POST"])
def reset_session(request, scenario_id):
    request.session['scenario_id'] = scenario_id
    request.session['history'] = []
    request.session['turn_count'] = 0
    request.session['session_complete'] = False
    request.session.modified = True
    return JsonResponse({'success': True})
