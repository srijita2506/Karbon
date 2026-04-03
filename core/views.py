from decimal import Decimal

from django.db.models import Q
import csv
import re
from datetime import date, timedelta

from django.http import HttpResponse
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Expense, Group, Participant
from .serializers import (
    BalanceSerializer,
    ExpenseListSerializer,
    ExpenseSerializer,
    GroupCreateSerializer,
    GroupUpdateSerializer,
    GroupSerializer,
    MintSenseRequestSerializer,
    MintSenseResponseSerializer,
    ParticipantSerializer,
    SettlementSerializer,
)
from .utils import compute_balances, compute_contributions, compute_settlements


class GroupViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Group.objects.filter(owner=self.request.user).order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ['create']:
            return GroupCreateSerializer
        if self.action in ['update', 'partial_update']:
            return GroupUpdateSerializer
        return GroupSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'])
    def balance(self, request, pk=None):
        group = self.get_object()
        expenses = (
            group.expenses.all()
            .select_related('payer')
            .prefetch_related('splits')
        )
        balances = compute_balances(expenses)
        participant_names = {
            participant.id: participant.name for participant in group.participants.all()
        }
        balance_payload = []
        for participant in group.participants.all():
            balance_payload.append(
                {
                    'participant_id': participant.id,
                    'balance': balances.get(participant.id, Decimal('0.00')),
                }
            )
        settlements = compute_settlements(balances)
        for settlement in settlements:
            settlement['from_name'] = participant_names.get(settlement['from_participant_id'], '')
            settlement['to_name'] = participant_names.get(settlement['to_participant_id'], '')
        return Response(
            {
                'balances': BalanceSerializer(balance_payload, many=True).data,
                'settlements': SettlementSerializer(settlements, many=True).data,
            }
        )

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        group = self.get_object()
        expenses = (
            group.expenses.all()
            .select_related('payer')
            .prefetch_related('splits')
        )
        total_spent = sum((expense.amount for expense in expenses), Decimal('0.00'))
        balances = compute_balances(expenses)
        contributions = compute_contributions(expenses)

        owner_participant = (
            group.participants.filter(user=request.user).first()
            or group.participants.filter(is_primary=True).first()
        )
        user_balance = balances.get(owner_participant.id, Decimal('0.00')) if owner_participant else Decimal('0.00')
        owed_by_user = -user_balance if user_balance < 0 else Decimal('0.00')
        owed_to_user = user_balance if user_balance > 0 else Decimal('0.00')

        participant_payload = []
        for participant in group.participants.all():
            contrib = contributions.get(participant.id, {'paid': Decimal('0.00'), 'share': Decimal('0.00')})
            participant_payload.append(
                {
                    'participant_id': participant.id,
                    'name': participant.name,
                    'paid': contrib['paid'],
                    'share': contrib['share'],
                    'balance': balances.get(participant.id, Decimal('0.00')),
                }
            )

        return Response(
            {
                'total_spent': total_spent,
                'owed_by_user': owed_by_user,
                'owed_to_user': owed_to_user,
                'participants': participant_payload,
            }
        )

    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        group = self.get_object()
        expenses = (
            group.expenses.all()
            .select_related('payer')
            .prefetch_related('splits__participant')
            .order_by('-date', '-created_at')
        )
        balances = compute_balances(expenses)
        participant_names = {
            participant.id: participant.name for participant in group.participants.all()
        }

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename=\"splitmint_{group.id}.csv\"'
        writer = csv.writer(response)

        writer.writerow(['Group', group.name])
        writer.writerow([])
        writer.writerow(['Expenses'])
        writer.writerow(['id', 'date', 'description', 'amount', 'payer', 'split_mode', 'participants'])

        for expense in expenses:
            participant_list = []
            for split in expense.splits.all():
                participant_list.append(participant_names.get(split.participant_id, str(split.participant_id)))
            writer.writerow(
                [
                    expense.id,
                    expense.date.isoformat(),
                    expense.description,
                    f"{expense.amount:.2f}",
                    participant_names.get(expense.payer_id, expense.payer_id),
                    expense.split_mode,
                    ', '.join(participant_list),
                ]
            )

        writer.writerow([])
        writer.writerow(['Balances'])
        writer.writerow(['participant', 'balance'])
        for participant_id, balance in balances.items():
            writer.writerow([participant_names.get(participant_id, participant_id), f"{balance:.2f}"])

        return response


class ParticipantViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ParticipantSerializer

    def get_queryset(self):
        return Participant.objects.filter(group__owner=self.request.user).order_by('created_at')

    def perform_create(self, serializer):
        group = serializer.validated_data['group']
        if group.owner_id != self.request.user.id:
            raise PermissionDenied('You do not own this group.')
        if group.participants.filter(is_primary=False).count() >= 3:
            raise PermissionDenied('Max 3 participants allowed (excluding you).')
        serializer.save()

    def perform_update(self, serializer):
        participant = self.get_object()
        if serializer.validated_data.get('group') and serializer.validated_data['group'].id != participant.group_id:
            raise PermissionDenied('Cannot change participant group.')
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        participant = self.get_object()
        if participant.is_primary:
            raise PermissionDenied('Primary participant cannot be removed.')
        linked = Expense.objects.filter(
            Q(payer_id=participant.id) | Q(splits__participant_id=participant.id)
        ).exists()
        if linked:
            return Response(
                {'detail': 'Cannot remove participant with linked expenses.'},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


class ExpenseViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Expense.objects.filter(group__owner=self.request.user).order_by('-date', '-created_at')
        group_id = self.request.query_params.get('group')
        participant_id = self.request.query_params.get('participant')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        amount_min = self.request.query_params.get('amount_min')
        amount_max = self.request.query_params.get('amount_max')
        search = self.request.query_params.get('search')

        if group_id:
            qs = qs.filter(group_id=group_id)
        if participant_id:
            qs = qs.filter(Q(splits__participant_id=participant_id) | Q(payer_id=participant_id)).distinct()
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if amount_min:
            qs = qs.filter(amount__gte=amount_min)
        if amount_max:
            qs = qs.filter(amount__lte=amount_max)
        if search:
            qs = qs.filter(description__icontains=search)

        return qs

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ExpenseListSerializer
        return ExpenseSerializer

    def perform_create(self, serializer):
        group = serializer.validated_data['group']
        if group.owner_id != self.request.user.id:
            raise PermissionDenied('You do not own this group.')
        serializer.save()


class MintSenseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MintSenseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data['text']
        group_id = serializer.validated_data.get('group_id')

        amount_match = re.search(r'(\d+(?:\.\d{1,2})?)', text)
        amount = Decimal(amount_match.group(1)) if amount_match else Decimal('0.00')

        description = text.strip()[:120] if text.strip() else 'MintSense expense'
        text_lower = text.lower()

        split_mode = 'equal'
        if 'percent' in text_lower or '%' in text_lower:
            split_mode = 'percent'
        elif 'amount' in text_lower or 'custom' in text_lower:
            split_mode = 'amount'
        elif 'equal' in text_lower or 'equally' in text_lower:
            split_mode = 'equal'

        parsed_date = date.today()
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if date_match:
            try:
                parsed_date = date.fromisoformat(date_match.group(1))
            except ValueError:
                parsed_date = date.today()
        elif 'yesterday' in text_lower:
            parsed_date = date.today() - timedelta(days=1)
        elif 'tomorrow' in text_lower:
            parsed_date = date.today() + timedelta(days=1)

        payer_id = None
        participant_ids = []
        split_values = {}
        if group_id:
            group = Group.objects.filter(id=group_id, owner=request.user).prefetch_related('participants').first()
            if not group:
                return Response({'detail': 'Group not found.'}, status=status.HTTP_404_NOT_FOUND)

            participants = list(group.participants.all())
            participant_lookup = {p.name.lower(): p for p in participants}

            matched = []
            for name, participant in participant_lookup.items():
                if name and name in text_lower:
                    matched.append(participant)

            participant_ids = [p.id for p in matched] if matched else [p.id for p in participants]

            if 'i paid' in text_lower or 'i spent' in text_lower or 'i bought' in text_lower:
                primary = next((p for p in participants if p.user_id == request.user.id), None)
                if not primary:
                    primary = next((p for p in participants if p.is_primary), None)
                if primary:
                    payer_id = primary.id

            if payer_id is None:
                for name, participant in participant_lookup.items():
                    if f'paid by {name}' in text_lower or f'{name} paid' in text_lower:
                        payer_id = participant.id
                        break

            ratio = re.search(r'(\d{1,3})\s*/\s*(\d{1,3})', text_lower)
            if ratio and len(participant_ids) >= 2:
                left = int(ratio.group(1))
                right = int(ratio.group(2))
                if left + right > 0:
                    split_mode = 'percent'
                    split_values = {
                        str(participant_ids[0]): Decimal(left),
                        str(participant_ids[1]): Decimal(right),
                    }
            else:
                percent_matches = re.findall(r'(\d{1,3})\s*%', text_lower)
                if percent_matches and len(percent_matches) >= 2:
                    percents = [int(value) for value in percent_matches[: len(participant_ids)]]
                    if sum(percents) > 0:
                        split_mode = 'percent'
                        split_values = {
                            str(pid): Decimal(value)
                            for pid, value in zip(participant_ids, percents)
                        }
                elif 'split' in text_lower:
                    split_segment = text_lower.split('split', 1)[1]
                    if 'between' in split_segment:
                        split_segment = split_segment.split('between', 1)[0]
                    inline_numbers = re.findall(r'\b(\d{1,3})\b', split_segment)
                    if inline_numbers and len(inline_numbers) >= 2:
                        percents = [int(value) for value in inline_numbers[: len(participant_ids)]]
                        if sum(percents) > 0:
                            split_mode = 'percent'
                            split_values = {
                                str(pid): Decimal(value)
                                for pid, value in zip(participant_ids, percents)
                            }

        suggestions = [
            "Confirm the payer and participants before saving.",
            "Adjust split mode if this wasn't an equal share.",
        ]

        payload = {
            'amount': amount,
            'description': description,
            'date': parsed_date.isoformat(),
            'split_mode': split_mode,
            'suggestions': suggestions,
        }
        if payer_id:
            payload['payer_id'] = payer_id
        if participant_ids:
            payload['participant_ids'] = participant_ids
        if split_values:
            payload['split_values'] = split_values

        return Response(MintSenseResponseSerializer(payload).data, status=status.HTTP_200_OK)
