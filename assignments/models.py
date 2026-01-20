from django.db import models
from django.contrib.auth import get_user_model
from courses.models import Course, CourseMembership

User = get_user_model()


class Assignment(models.Model):
    """Sərbəst iş modeli"""
    STATUS_CHOICES = [
        ('active', 'Aktiv'),
        ('inactive', 'Deaktiv'),
        ('archived', 'Arxivləndi'),
    ]
    
    course = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name='assignments',
        verbose_name='Kurs'
    )
    title = models.CharField(max_length=255, verbose_name='Başlıq')
    description = models.TextField(blank=True, verbose_name='Təsvir')
    
    start_date = models.DateTimeField(
        verbose_name='Başlanğıc tarixi',
        help_text='Tələbələr bu tarixdən sonra cavab verə bilər'
    )
    deadline = models.DateTimeField(verbose_name='Son tarix')
    
    max_attempts = models.PositiveIntegerField(default=3, verbose_name='Maksimum cəhd')
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='active',
        verbose_name='Status'
    )
    
    # Tələbələr və ya qruplar
    assigned_students = models.ManyToManyField(
        User,
        blank=True,
        related_name='student_assignments',
        verbose_name='Tələbələr'
    )
    # Qrup seçimi CourseMembership-dən group_name-ə əsasən
    # assigned_groups field-i silindi, çünki Group modeli yoxdur
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Sərbəst İş'
        verbose_name_plural = 'Sərbəst İşlər'
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    @property
    def is_deadline_passed(self):
        from django.utils import timezone
        return timezone.now() > self.deadline
    
    def get_submissions_count(self):
        """Ümumi cavab sayı"""
        return self.submissions.count()
    
    def get_pending_submissions(self):
        """Yoxlanılmayan cavablar"""
        return self.submissions.filter(status='pending').count()
    
    def get_user_attempts(self, user):
        """İstifadəçinin cəhd sayı"""
        return self.submissions.filter(student=user).count()
    
    def can_user_submit(self, user):
        """İstifadəçi cavab verə bilərmi?"""
        if self.is_deadline_passed:
            return False
        if self.status != 'active':
            return False
        attempts = self.get_user_attempts(user)
        return attempts < self.max_attempts


class AssignmentSubmission(models.Model):
    """Sərbəst işə cavab modeli"""
    STATUS_CHOICES = [
        ('pending', 'Gözləyir'),
        ('graded', 'Qiymətləndirilib'),
        ('rejected', 'Rədd edilib'),
    ]
    
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name='Tapşırıq'
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='assignment_submissions',
        verbose_name='Tələbə'
    )
    content = models.TextField(verbose_name='Cavab')
    file = models.FileField(
        upload_to='assignments/submissions/',
        blank=True,
        null=True,
        verbose_name='Fayl'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Status'
    )
    grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Qiymət'
    )
    feedback = models.TextField(blank=True, verbose_name='Rəy')
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='graded_submissions',
        verbose_name='Qiymətləndirən'
    )
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Cavab'
        verbose_name_plural = 'Cavablar'
        unique_together = ['assignment', 'student', 'submitted_at']
    
    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"