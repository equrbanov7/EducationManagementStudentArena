"""
projects/models.py
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from courses.models import Course

User = get_user_model()


class Project(models.Model):
    STATUS_CHOICES = [
        ('active', 'Aktiv'),
        ('inactive', 'Deaktiv'),
        ('archived', 'Arxivləndi'),
    ]
    
    course = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name='projects',
        verbose_name='Kurs'
    )
    title = models.CharField(max_length=255, verbose_name='Kurs İşi Adı')
    description = models.TextField(blank=True, verbose_name='Təsvir')
    start_date = models.DateTimeField(verbose_name='Başlanğıc tarixi')
    deadline = models.DateTimeField(verbose_name='Son tarix')
    max_attempts = models.PositiveIntegerField(default=1, verbose_name='Maksimum cəhd')
    max_score = models.PositiveIntegerField(default=100, verbose_name='Maksimum bal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    assigned_students = models.ManyToManyField(
        User,
        blank=True,
        related_name='student_projects',
        verbose_name='Tələbələr'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Kurs İşi'
        verbose_name_plural = 'Kurs İşləri'
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    @property
    def is_deadline_passed(self):
        return timezone.now() > self.deadline
    
    def get_submissions_count(self):
        return self.submissions.count()
    
    def get_pending_submissions(self):
        return self.submissions.filter(status='pending').count()
    
    def get_user_attempts(self, user):
        return self.submissions.filter(student=user).count()
    
    def can_user_submit(self, user):
        if self.is_deadline_passed:
            return False
        if self.status != 'active':
            return False
        return self.get_user_attempts(user) < self.max_attempts


class ProjectSubmission(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Gözləyir'),
        ('graded', 'Qiymətləndirilib'),
        ('rejected', 'Rədd edilib'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_submissions')
    content = models.TextField(verbose_name='Cavab / İzahat')
    file = models.FileField(upload_to='projects/submissions/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_project_submissions')
    
    class Meta:
        ordering = ['-submitted_at']