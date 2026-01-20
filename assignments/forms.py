from django import forms
from .models import Assignment, AssignmentSubmission


class AssignmentForm(forms.ModelForm):
    """Sərbəst iş forması"""
    
    class Meta:
        model = Assignment
        fields = ['title', 'description', 'deadline', 'max_attempts', 'status']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Sərbəst işin başlığı'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Təsvir...'
            }),
            'deadline': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'max_attempts': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'value': 3
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            })
        }
        labels = {
            'title': 'Başlıq',
            'description': 'Təsvir',
            'deadline': 'Son tarix',
            'max_attempts': 'Maksimum cəhd',
            'status': 'Status'
        }


class AssignmentSubmissionForm(forms.ModelForm):
    """Cavab göndərmə forması"""
    
    class Meta:
        model = AssignmentSubmission
        fields = ['content', 'file']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Cavabınızı buraya yazın...',
                'required': True
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt,.zip'
            })
        }
        labels = {
            'content': 'Cavabınız',
            'file': 'Fayl (opsional)'
        }


class GradeSubmissionForm(forms.ModelForm):
    """Qiymətləndirmə forması"""
    
    class Meta:
        model = AssignmentSubmission
        fields = ['grade', 'feedback', 'status']
        widgets = {
            'grade': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': 0,
                'max': 100,
                'placeholder': '0-100'
            }),
            'feedback': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Tələbəyə rəy yazın...'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            })
        }
        labels = {
            'grade': 'Qiymət',
            'feedback': 'Rəy',
            'status': 'Status'
        }