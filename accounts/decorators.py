from functools import wraps
from django.shortcuts import redirect


def supabase_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('supabase_user'):
            next_url = request.get_full_path()
            return redirect(f'/login/?next={next_url}')
        return view_func(request, *args, **kwargs)
    return wrapper
