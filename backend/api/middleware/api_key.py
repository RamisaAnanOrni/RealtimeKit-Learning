from django.http import JsonResponse
from django.conf import settings

class APIKeyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/internal/'):
            api_key = request.headers.get('X-API-KEY')
            expected_key = getattr(settings, 'STATIC_API_KEY', None)
            
            if not expected_key or api_key != expected_key:
                return JsonResponse({'detail': 'Invalid or missing Static API Key'}, status=401)

        return self.get_response(request)