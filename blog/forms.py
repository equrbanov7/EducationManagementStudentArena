# forms.py
from django import forms

class SubscriptionForm(forms.Form):
    email = forms.EmailField(
        required=True,
        label='', # Etiket lazım deyil, placeholder istifadə edəcəyik
        widget=forms.EmailInput(attrs={
            'placeholder': 'Email ünvanınızı daxil edin...',
            'class': 'form-control', # Bootstrap və ya öz CSS-imiz üçün
            'id': 'emailInput'
        })
    )
    # Əgər gələcəkdə ad/soyad da istəsəniz bura əlavə edə bilərsiniz.
    
