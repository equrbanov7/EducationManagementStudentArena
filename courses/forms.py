"""
courses/forms.py
────────────────
Kurs yaratma, redaksiya, mövzu əlavə etmə üçün formalar.

Nə üçün:
- HTML forma yaratmaq (Bootstrap stilləmə ilə)
- Validasiya (cleaners)
- CSRF protection (otomatik)
"""

from django import forms
from .models import Course, CourseTopic, CourseResource


# ════════════════════════════════════════════════════════════════════════════
# COURSE FORM (Kurs Yaratma/Redaksiya)
# ════════════════════════════════════════════════════════════════════════════

class CourseForm(forms.ModelForm):
    """
    Kurs yaratma/redaksiya forması.
    
    Nə edər:
    1. Müəllim kurs adı, təsviri, şəkli daxil edir
    2. Form validasiya edir (boşluqları yoxlayır)
    3. Kurs yaradılır/redaktə olunur
    
    Misal (Template):
    <form method="post">
        {{ form.title }}
        {{ form.description }}
        {{ form.cover_image }}
        <button>Kurs Yarat</button>
    </form>
    """
    
    class Meta:
        model = Course
        fields = ['title', 'description', 'cover_image', 'status']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kurs adı (məs: "Python Başlanğıc")',
                'required': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Kurs haqqında məlumat...',
                'rows': 4,
            }),
            'cover_image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'status': forms.Select(attrs={
                'class': 'form-control',
            }),
        }
    
    def clean_title(self):
        """Title validasiyası."""
        title = self.cleaned_data.get('title', '').strip()
        
        if len(title) < 3:
            raise forms.ValidationError('Kurs adı ən azı 3 simvol olmalıdır.')
        
        if len(title) > 255:
            raise forms.ValidationError('Kurs adı 255 simvoldan çox ola bilməz.')
        
        return title


# ════════════════════════════════════════════════════════════════════════════
# COURSE TOPIC FORM (Mövzu Əlavə Etmə)
# ════════════════════════════════════════════════════════════════════════════

class CourseTopicForm(forms.ModelForm):
    """
    Mövzu əlavə etmə forması.
    
    Nə edər:
    - Müəllim mövzu adı, sıra, açıqlaması daxil edir
    - Order otomatik hesablanır (sonuncu mövzu + 1)
    
    Misal:
    - Course: Python 101
    - Topic 1: Həftə 1: Giriş (order=1)
    - Topic 2: Həftə 2: Dəyişkənlər (order=2)
    """
    
    class Meta:
        model = CourseTopic
        fields = ['title', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Mövzu adı (məs: "Həftə 1: Giriş")',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Mövzu təsviri...',
            }),
        }
    
    def clean_title(self):
        """Title validasiyası."""
        title = self.cleaned_data.get('title', '').strip()
        
        if not title:
            raise forms.ValidationError('Mövzu adı boş ola bilməz.')
        
        return title


# ════════════════════════════════════════════════════════════════════════════
# COURSE RESOURCE FORM (Resurs Əlavə Etmə)
# ════════════════════════════════════════════════════════════════════════════

class CourseResourceForm(forms.ModelForm):
    """
    Resurs əlavə etmə forması (PDF, Link, Video, və s.).
    
    Nə edər:
    - Müəllim resurs adı, tipi, fayl/link daxil edir
    - Validasiya: Fayl varsa URL boş olmalı (və əksinə)
    
    Misal:
    - Resurs 1: "Python Dokumentasiyası" (URL)
    - Resurs 2: "Giriş Slaydları" (Fayl: PDF)
    """
    
    class Meta:
        model = CourseResource
        fields = ['title', 'description', 'resource_type', 'file', 'url', 'topic']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Resurs adı',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Açıqlama...',
            }),
            'resource_type': forms.Select(attrs={
                'class': 'form-control',
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.zip,.jpg,.png,.mp4',
            }),
            'url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com/...',
            }),
            'topic': forms.Select(attrs={
                'class': 'form-control',
            }),
        }
    
    def clean(self):
        """Fayl YA URL olmalı, ama ikisi bir vaxtda deyil."""
        cleaned_data = super().clean()
        file = cleaned_data.get('file')
        url = cleaned_data.get('url')
        
        if not file and not url:
            raise forms.ValidationError(
                'Fayl yüklə və ya URL linki əlavə et (ikisindən biri lazımdır).'
            )
        
        if file and url:
            raise forms.ValidationError(
                'Fayl VƏ URL bir vaxtda ola bilməz. Birini seç.'
            )
        
        return cleaned_data