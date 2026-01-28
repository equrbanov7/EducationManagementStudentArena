from django import forms
from .models import Project, ProjectSubmission


class ProjectForm(forms.ModelForm):
    """Kurs işi forması"""
    
    class Meta:
        model = Project
        fields = ['title', 'description', 'start_date', 'deadline', 'max_attempts', 'max_score', 'status']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kurs işinin adı'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Layihə haqqında təsvir...'
            }),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'deadline': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'max_attempts': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'value': 1
            }),
            'max_score': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'value': 100
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            })
        }
        labels = {
            'title': 'Layihə Adı',
            'description': 'Təsvir',
            'start_date': 'Başlanğıc tarixi',
            'deadline': 'Son tarix',
            'max_attempts': 'Maksimum cəhd',
            'max_score': 'Maksimum bal',
            'status': 'Status'
        }


class ProjectSubmissionForm(forms.ModelForm):
    """Layihə təqdim etmə forması"""
    
    class Meta:
        model = ProjectSubmission
        fields = ['content', 'file']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Layihəniz haqqında izah, linkler və s.',
                'required': True
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.zip,.pdf,.rar'
            })
        }
        labels = {
            'content': 'Layihə İzahatı',
            'file': 'Layihə Faylı (ZIP, PDF)'
        }


class GradeProjectSubmissionForm(forms.ModelForm):
    """Qiymətləndirmə forması"""
    
    class Meta:
        model = ProjectSubmission
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