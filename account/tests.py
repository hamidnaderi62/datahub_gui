import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings


User = get_user_model()


class AuthenticationFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='active-user',
            email='active@example.test',
            password='SafePassword123!',
            is_active=True,
        )

    def test_login_form_has_working_csrf_protection(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST='localhost')
        response = client.get('/account/login')
        self.assertEqual(response.status_code, 200)
        token = re.search(
            rb'name="csrfmiddlewaretoken" value="([^"]+)"',
            response.content,
        ).group(1).decode()
        response = client.post(
            '/account/login',
            {
                'username': self.user.username,
                'password': 'SafePassword123!',
                'csrfmiddlewaretoken': token,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_registration_creates_inactive_user_and_redirects(self):
        client = Client(HTTP_HOST='localhost')
        response = client.post(
            '/account/register',
            {
                'username': 'pending-user',
                'email': 'pending@example.test',
                'password1': 'SafePassword123!',
                'password2': 'SafePassword123!',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/account/login')
        pending = User.objects.get(username='pending-user')
        self.assertFalse(pending.is_active)
