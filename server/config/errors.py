"""Error pages: friendly HTML for people, JSON for /api/ callers."""
from django.conf import settings
from django.http import HttpResponseServerError, JsonResponse
from django.shortcuts import render
from django.template import loader

ERRORS = {
    400: ('bad_request', '잘못된 요청입니다', '요청 내용을 확인할 수 없습니다. 주소를 다시 확인하거나 처음 화면에서 다시 시작해 주세요.'),
    403: ('permission_denied', '접근 권한이 없습니다', '이 페이지를 볼 수 있는 권한이 없거나 보안 확인이 만료되었습니다. 다시 로그인한 뒤 시도해 주세요.'),
    404: ('not_found', '페이지를 찾을 수 없습니다', '입력한 주소가 잘못되었거나 페이지가 이동 또는 삭제되었습니다.'),
}


def _is_api(request):
    return request.path.startswith('/api/')


def error_response(request, status):
    code, title, message = ERRORS[status]
    if _is_api(request):
        response = JsonResponse({'error': code}, status=status)
    else:
        response = render(request, 'errors/error.html', {'status': status, 'title': title, 'message': message},
                          status=status)
    response.friendly_error_page = True
    return response


def bad_request(request, exception=None):
    return error_response(request, 400)


def permission_denied(request, exception=None):
    return error_response(request, 403)


def page_not_found(request, exception=None):
    return error_response(request, 404)


def server_error(request):
    # No context processors here: whatever failed (DB, session) must not break the error page itself.
    if _is_api(request):
        return JsonResponse({'error': 'server_error'}, status=500)
    return HttpResponseServerError(loader.get_template('errors/500.html').render())


class FriendlyNotFoundMiddleware:
    """With DEBUG on, Django shows its technical 404 page (URL list) instead of handler404.
    Show the same page people get in production, so testing on this PC matches real use."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (settings.DEBUG and response.status_code == 404 and not getattr(response, 'friendly_error_page', False)
                and not getattr(response, 'streaming', False)
                and response.get('Content-Type', '').startswith('text/html')):
            return page_not_found(request)
        return response
