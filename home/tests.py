from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override


class HomePageTests(TestCase):
    def test_home_page_contains_platform_workflow(self):
        with override('fa'):
            response = self.client.get(reverse('home:home'))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'dh-workflow')
            self.assertContains(response, 'از فایل خام تا دیتاست قابل اعتماد')
            self.assertContains(response, '#landingWorkflow')
            self.assertContains(response, '#landingIntegrations')
            self.assertContains(response, '#landingStart')
            self.assertContains(response, 'روند کار')
            self.assertNotContains(response, 'تیم ما')
            self.assertNotContains(response, 'نظرات مشتریان')

    def test_home_page_uses_the_same_complete_layout_in_english(self):
        self.client.cookies['datahub_language'] = 'en'
        with override('en'):
            response = self.client.get(reverse('home:home'))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'From raw files to a trusted dataset')
            self.assertContains(response, 'How it works')
            self.assertContains(response, 'Integrations')
            self.assertContains(response, 'Get started')
            self.assertContains(response, 'Frequently asked questions')
