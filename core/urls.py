from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ExpenseViewSet, GroupViewSet, MintSenseView, ParticipantViewSet

router = DefaultRouter()
router.register('groups', GroupViewSet, basename='group')
router.register('participants', ParticipantViewSet, basename='participant')
router.register('expenses', ExpenseViewSet, basename='expense')

urlpatterns = [
    path('', include(router.urls)),
    path('mintsense/', MintSenseView.as_view(), name='mintsense'),
]
