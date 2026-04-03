from decimal import Decimal

from django.conf import settings
from django.db import models


class Group(models.Model):
    name = models.CharField(max_length=120)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_groups'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}"


class Participant(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='participants',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    color = models.CharField(max_length=32, blank=True)
    avatar = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}"


class Expense(models.Model):
    SPLIT_EQUAL = 'equal'
    SPLIT_AMOUNT = 'amount'
    SPLIT_PERCENT = 'percent'

    SPLIT_CHOICES = [
        (SPLIT_EQUAL, 'Equal'),
        (SPLIT_AMOUNT, 'Custom Amount'),
        (SPLIT_PERCENT, 'Percentage'),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='expenses')
    payer = models.ForeignKey(Participant, on_delete=models.PROTECT, related_name='paid_expenses')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    date = models.DateField()
    split_mode = models.CharField(max_length=12, choices=SPLIT_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} - {self.amount}"


class ExpenseSplit(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='splits')
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='splits')
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('expense', 'participant')

    def __str__(self):
        return f"{self.participant.name}"
