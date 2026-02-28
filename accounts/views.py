from django.shortcuts import render, redirect
from django.conf import settings

supabase = settings.SUPABASE_CLIENT


def login_view(request):
    mode = request.GET.get('mode', 'signin')
    next_url = request.GET.get('next', '/')

    if request.session.get('supabase_user'):
        return redirect(next_url)

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        mode = request.POST.get('mode', 'signin')
        next_url = request.POST.get('next', '/')

        # Server-side validation
        errors = {}

        if not email or '@' not in email or '.' not in email.split('@')[-1]:
            errors['email'] = 'Please enter a valid email address.'

        if not password:
            errors['password'] = 'Password is required.'
        elif mode == 'signup' and len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'

        if mode == 'signup' and not errors.get('password'):
            if password != confirm_password:
                errors['confirm_password'] = 'Passwords do not match.'

        if errors:
            return render(request, 'accounts/login.html', {
                'mode': mode,
                'next': next_url,
                'errors': errors,
                'email': email,
            })

        try:
            if mode == 'signup':
                response = supabase.auth.sign_up({'email': email, 'password': password})

                if response.user is None:
                    return render(request, 'accounts/login.html', {
                        'mode': mode,
                        'next': next_url,
                        'error': 'Signup failed. Please try again.',
                        'email': email,
                    })

                # Email confirmation required — don't log in yet
                if response.session is None:
                    return render(request, 'accounts/login.html', {
                        'mode': 'signin',
                        'next': next_url,
                        'success': 'Account created! Please check your email to confirm your account, then sign in.',
                        'email': email,
                    })

                # Supabase auto-confirmed (e.g. email confirmations disabled)
                request.session['supabase_user'] = {
                    'email': response.user.email,
                    'id': str(response.user.id),
                    'access_token': response.session.access_token,
                }
                return redirect(next_url if next_url.startswith('/') else '/')
            else:
                response = supabase.auth.sign_in_with_password({'email': email, 'password': password})

                if response.user is None:
                    return render(request, 'accounts/login.html', {
                        'mode': mode,
                        'next': next_url,
                        'error': 'Authentication failed. Please check your credentials.',
                        'email': email,
                    })

                request.session['supabase_user'] = {
                    'email': response.user.email,
                    'id': str(response.user.id),
                    'access_token': response.session.access_token if response.session else '',
                }
                return redirect(next_url if next_url.startswith('/') else '/')

        except Exception as e:
            error_msg = str(e)
            # Sanitize common Supabase error messages
            if 'Invalid login credentials' in error_msg:
                error_msg = 'Invalid email or password.'
            elif 'Email not confirmed' in error_msg:
                error_msg = 'Please confirm your email before signing in. Check your inbox for a confirmation link.'
            elif 'User already registered' in error_msg:
                error_msg = 'An account with this email already exists. Please sign in.'
            elif 'Password should be at least' in error_msg:
                error_msg = 'Password must be at least 8 characters.'
            else:
                error_msg = 'Something went wrong. Please try again.'

            return render(request, 'accounts/login.html', {
                'mode': mode,
                'next': next_url,
                'error': error_msg,
                'email': email,
            })

    return render(request, 'accounts/login.html', {
        'mode': mode,
        'next': next_url,
    })


def logout_view(request):
    if request.method == 'POST':
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
        request.session.flush()
    return redirect('/login/')
