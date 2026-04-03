from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import Expense, ExpenseSplit, Group, Participant
from .utils import compute_shares


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participant
        fields = ['id', 'group', 'user', 'name', 'color', 'avatar', 'is_primary', 'created_at']
        read_only_fields = ['id', 'user', 'is_primary', 'created_at']


class GroupParticipantInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=120)
    color = serializers.CharField(max_length=32, required=False, allow_blank=True)
    avatar = serializers.CharField(max_length=255, required=False, allow_blank=True)


class GroupSerializer(serializers.ModelSerializer):
    participants = ParticipantSerializer(many=True, read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'owner', 'participants', 'created_at']
        read_only_fields = ['id', 'owner', 'created_at']


class GroupCreateSerializer(serializers.ModelSerializer):
    participants = GroupParticipantInputSerializer(many=True, required=False)

    class Meta:
        model = Group
        fields = ['id', 'name', 'participants', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_participants(self, value):
        if len(value) > 3:
            raise serializers.ValidationError('Max 3 participants allowed (excluding you).')
        return value

    @transaction.atomic
    def create(self, validated_data):
        participants = validated_data.pop('participants', [])
        owner = validated_data.pop('owner', None) or self.context['request'].user
        group = Group.objects.create(owner=owner, **validated_data)
        owner_name = owner.get_full_name().strip() or owner.email or owner.username
        Participant.objects.create(
            group=group,
            user=owner,
            name=owner_name,
            is_primary=True,
        )
        for participant in participants:
            Participant.objects.create(group=group, **participant)
        return group


class GroupUpdateSerializer(serializers.ModelSerializer):
    participants = GroupParticipantInputSerializer(many=True, required=False)

    class Meta:
        model = Group
        fields = ['id', 'name', 'participants', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_participants(self, value):
        if len(value) > 3:
            raise serializers.ValidationError('Max 3 participants allowed (excluding you).')
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        participants = validated_data.pop('participants', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()

        if participants is None:
            return instance

        existing = {
            participant.id: participant
            for participant in instance.participants.filter(is_primary=False)
        }
        primary_ids = set(
            instance.participants.filter(is_primary=True).values_list('id', flat=True)
        )
        seen_ids = set()

        for payload in participants:
            pid = payload.get('id')
            if pid in primary_ids:
                raise serializers.ValidationError('Primary participant cannot be edited here.')
            if pid:
                if pid in seen_ids:
                    raise serializers.ValidationError('Duplicate participant ids are not allowed.')
                participant = existing.get(pid)
                if not participant:
                    raise serializers.ValidationError('Participant does not belong to this group.')
                participant.name = payload['name']
                participant.color = payload.get('color', participant.color)
                participant.avatar = payload.get('avatar', participant.avatar)
                participant.save()
                seen_ids.add(pid)
            else:
                Participant.objects.create(
                    group=instance,
                    name=payload['name'],
                    color=payload.get('color', ''),
                    avatar=payload.get('avatar', ''),
                )

        removable = [
            participant
            for participant in existing.values()
            if participant.id not in seen_ids
        ]
        if removable:
            from django.db.models import Q

            for participant in removable:
                linked = Expense.objects.filter(
                    Q(payer_id=participant.id) | Q(splits__participant_id=participant.id),
                    group=instance,
                ).exists()
                if linked:
                    raise serializers.ValidationError(
                        'Cannot remove participant with linked expenses.'
                    )
            for participant in removable:
                participant.delete()

        return instance


class ExpenseSplitInputSerializer(serializers.Serializer):
    participant_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    percentage = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)


class ExpenseSerializer(serializers.ModelSerializer):
    splits = ExpenseSplitInputSerializer(many=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'group',
            'payer',
            'amount',
            'description',
            'date',
            'split_mode',
            'splits',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        group = attrs.get('group') or self.instance.group
        payer = attrs.get('payer') or self.instance.payer
        if payer.group_id != group.id:
            raise serializers.ValidationError('Payer must belong to the same group.')
        return attrs

    def _validate_splits(self, group, split_mode, splits, total):
        participant_ids = [s['participant_id'] for s in splits]
        if len(set(participant_ids)) != len(participant_ids):
            raise serializers.ValidationError('Duplicate participants in splits are not allowed.')
        valid_ids = set(group.participants.values_list('id', flat=True))
        invalid = [pid for pid in participant_ids if pid not in valid_ids]
        if invalid:
            raise serializers.ValidationError('All split participants must belong to the group.')

        split_payload = []
        for split in splits:
            split_payload.append(
                {
                    'participant_id': split['participant_id'],
                    'amount': split.get('amount'),
                    'percentage': split.get('percentage'),
                }
            )
        try:
            compute_shares(Decimal(total), split_mode, split_payload)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    @transaction.atomic
    def create(self, validated_data):
        splits = validated_data.pop('splits', [])
        expense = Expense.objects.create(**validated_data)
        self._save_splits(expense, splits)
        return expense

    @transaction.atomic
    def update(self, instance, validated_data):
        splits = validated_data.pop('splits', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if splits is not None:
            instance.splits.all().delete()
            self._save_splits(instance, splits)
        return instance

    def _save_splits(self, expense, splits):
        self._validate_splits(expense.group, expense.split_mode, splits, expense.amount)
        bulk = []
        for split in splits:
            bulk.append(
                ExpenseSplit(
                    expense=expense,
                    participant_id=split['participant_id'],
                    amount=split.get('amount'),
                    percentage=split.get('percentage'),
                )
            )
        ExpenseSplit.objects.bulk_create(bulk)


class ExpenseListSerializer(serializers.ModelSerializer):
    splits = ExpenseSplitInputSerializer(many=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'group',
            'payer',
            'amount',
            'description',
            'date',
            'split_mode',
            'splits',
            'created_at',
        ]
        read_only_fields = fields


class BalanceSerializer(serializers.Serializer):
    participant_id = serializers.IntegerField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)


class SettlementSerializer(serializers.Serializer):
    from_participant_id = serializers.IntegerField()
    to_participant_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    from_name = serializers.CharField(required=False)
    to_name = serializers.CharField(required=False)


class MintSenseRequestSerializer(serializers.Serializer):
    text = serializers.CharField()
    group_id = serializers.IntegerField(required=False)


class MintSenseResponseSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    description = serializers.CharField()
    date = serializers.DateField()
    split_mode = serializers.CharField()
    suggestions = serializers.ListField(child=serializers.CharField())
    payer_id = serializers.IntegerField(required=False)
    participant_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    split_values = serializers.DictField(child=serializers.DecimalField(max_digits=12, decimal_places=2), required=False)
