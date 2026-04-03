from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


class CoreFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='owner@example.com',
            email='owner@example.com',
            password='StrongPass123',
            first_name='Owner',
        )
        login = self.client.post(
            '/api/auth/login/',
            {'email': 'owner@example.com', 'password': 'StrongPass123'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        token = login.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_group_participants_and_expenses_flow(self):
        group_payload = {
            'name': 'Weekend Trip',
            'participants': [
                {'name': 'Riya'},
                {'name': 'Sam'},
            ],
        }
        response = self.client.post('/api/groups/', group_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        groups = self.client.get('/api/groups/')
        self.assertEqual(groups.status_code, status.HTTP_200_OK)
        group = groups.data[0]
        group_id = group['id']
        self.assertEqual(len(group['participants']), 3)

        participant_ids = [p['id'] for p in group['participants']]
        payer_id = participant_ids[0]
        split_payload = [{'participant_id': pid} for pid in participant_ids]

        expense_payload = {
            'group': group_id,
            'payer': payer_id,
            'amount': '1200.00',
            'description': 'Stay',
            'date': '2026-04-03',
            'split_mode': 'equal',
            'splits': split_payload,
        }
        expense_response = self.client.post('/api/expenses/', expense_payload, format='json')
        self.assertEqual(expense_response.status_code, status.HTTP_201_CREATED)

        balance = self.client.get(f'/api/groups/{group_id}/balance/')
        self.assertEqual(balance.status_code, status.HTTP_200_OK)
        self.assertIn('settlements', balance.data)
        if balance.data['settlements']:
            settlement = balance.data['settlements'][0]
            self.assertIn('from_name', settlement)
            self.assertIn('to_name', settlement)

        summary = self.client.get(f'/api/groups/{group_id}/summary/')
        self.assertEqual(summary.status_code, status.HTTP_200_OK)
        self.assertEqual(summary.data['total_spent'], '1200.00')

    def test_participant_remove_blocked_with_expense(self):
        group_payload = {
            'name': 'Dinner',
            'participants': [
                {'name': 'Alex'},
            ],
        }
        response = self.client.post('/api/groups/', group_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        group = self.client.get('/api/groups/').data[0]
        group_id = group['id']
        primary = next(p for p in group['participants'] if p['is_primary'])
        secondary = next(p for p in group['participants'] if not p['is_primary'])

        expense_payload = {
            'group': group_id,
            'payer': primary['id'],
            'amount': '500.00',
            'description': 'Dinner',
            'date': '2026-04-03',
            'split_mode': 'equal',
            'splits': [
                {'participant_id': primary['id']},
                {'participant_id': secondary['id']},
            ],
        }
        expense_response = self.client.post('/api/expenses/', expense_payload, format='json')
        self.assertEqual(expense_response.status_code, status.HTTP_201_CREATED)

        update_payload = {
            'name': 'Dinner',
            'participants': [],
        }
        update_response = self.client.put(
            f'/api/groups/{group_id}/',
            update_payload,
            format='json',
        )
        self.assertEqual(update_response.status_code, status.HTTP_400_BAD_REQUEST)

        delete_response = self.client.delete(f"/api/participants/{secondary['id']}/")
        self.assertEqual(delete_response.status_code, status.HTTP_409_CONFLICT)

    def test_mintsense_endpoint(self):
        group_payload = {
            'name': 'MintSense Group',
            'participants': [
                {'name': 'Alex'},
            ],
        }
        response = self.client.post('/api/groups/', group_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        group_id = response.data['id']

        response = self.client.post(
            '/api/mintsense/',
            {'text': 'I paid 450 for snacks yesterday 60/40', 'group_id': group_id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['amount'], '450.00')
        self.assertEqual(response.data['split_mode'], 'percent')
        self.assertIn('payer_id', response.data)
        self.assertIn('participant_ids', response.data)
        self.assertIn('split_values', response.data)
