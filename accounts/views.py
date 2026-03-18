from django.shortcuts import render, redirect
from accounts.models import DemoUser


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

        if mode == 'signup':
            if DemoUser.objects.filter(email=email).exists():
                return render(request, 'accounts/login.html', {
                    'mode': mode,
                    'next': next_url,
                    'error': 'An account with this email already exists. Please sign in.',
                    'email': email,
                })
            user = DemoUser(email=email)
            user.set_password(password)
            user.save()
            request.session['supabase_user'] = {
                'email': email,
                'id': str(user.id),
                'access_token': '',
            }
            return redirect(next_url if next_url.startswith('/') else '/')
        else:
            try:
                user = DemoUser.objects.get(email=email)
            except DemoUser.DoesNotExist:
                return render(request, 'accounts/login.html', {
                    'mode': mode,
                    'next': next_url,
                    'error': 'Invalid email or password.',
                    'email': email,
                })
            if not user.check_password(password):
                return render(request, 'accounts/login.html', {
                    'mode': mode,
                    'next': next_url,
                    'error': 'Invalid email or password.',
                    'email': email,
                })
            request.session['supabase_user'] = {
                'email': email,
                'id': str(user.id),
                'access_token': '',
            }
            return redirect(next_url if next_url.startswith('/') else '/')

    return render(request, 'accounts/login.html', {
        'mode': mode,
        'next': next_url,
    })


def logout_view(request):
    if request.method == 'POST':
        request.session.flush()
    return redirect('/login/')
