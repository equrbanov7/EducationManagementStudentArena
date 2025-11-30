document.addEventListener('DOMContentLoaded', function() {
    // Modal elementləri
    const editModal = document.getElementById('editModal');
    const deleteModal = document.getElementById('deleteModal');
    const warningModal = document.getElementById('warningModal');
    
    // Edit modal elementləri
    const editForm = document.getElementById('editForm');
    const editTitle = document.getElementById('editTitle');
    const editCategory = document.getElementById('editCategory');
    const editExcerpt = document.getElementById('editExcerpt');
    const editContent = document.getElementById('editContent');
    const saveEditBtn = document.getElementById('saveEdit');
    const cancelEditBtn = document.getElementById('cancelEdit');
    const closeEditModalBtn = document.getElementById('closeEditModal');
    
    // Delete modal elementləri
    const deleteTitleSpan = document.getElementById('deleteTitle');
    const confirmDeleteBtn = document.getElementById('confirmDelete');
    const cancelDeleteBtn = document.getElementById('cancelDelete');
    
    // Warning modal elementləri
    const stayOnModalBtn = document.getElementById('stayOnModal');
    const discardChangesBtn = document.getElementById('discardChanges');
    
    // State idarəetməsi
    let currentPostId = null;
    let originalFormData = {};
    let hasUnsavedChanges = false;
    let pendingClose = false;

    // ============= EDIT FUNKSIONALLARI =============
    
    // Edit düyməsinə klik (yalnız post kartındakı düymələr)
    document.querySelectorAll('.js-edit-post').forEach(btn => {
        btn.addEventListener('click', function() {
            currentPostId = this.dataset.postId;
            const title = this.dataset.title || '';
            const content = this.dataset.content || '';
            const category = this.dataset.category || '';
            const excerpt = this.dataset.excerpt || '';
            
            // Formu doldur
            editTitle.value = title;
            editContent.value = content;
            editCategory.value = category;
            editExcerpt.value = excerpt;
            
            // Orijinal datanı saxla
            originalFormData = {
                title: title,
                content: content,
                category: category,
                excerpt: excerpt
            };
            
            hasUnsavedChanges = false;
            saveEditBtn.disabled = true;
            saveEditBtn.classList.remove('active');
            
            showModal(editModal);
        });
    });
    
    // Form dəyişikliklərini izlə
    const formInputs = [editTitle, editCategory, editExcerpt, editContent];
    formInputs.forEach(input => {
        input.addEventListener('input', checkForChanges);
    });
    
    function checkForChanges() {
        const currentData = {
            title: editTitle.value.trim(),
            content: editContent.value.trim(),
            category: editCategory.value,
            excerpt: editExcerpt.value.trim()
        };
        
        hasUnsavedChanges = (
            currentData.title !== originalFormData.title ||
            currentData.content !== originalFormData.content ||
            currentData.category !== originalFormData.category ||
            currentData.excerpt !== originalFormData.excerpt
        );
        
        if (hasUnsavedChanges) {
            saveEditBtn.disabled = false;
            saveEditBtn.classList.add('active');
        } else {
            saveEditBtn.disabled = true;
            saveEditBtn.classList.remove('active');
        }
    }
    
    // Formu submit et
    editForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        if (!hasUnsavedChanges || !currentPostId) return;
        
        const formData = new FormData(editForm);
        
        try {
            const response = await fetch(`/blog/post/${currentPostId}/edit/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                hasUnsavedChanges = false;
                hideModal(editModal);
                location.reload();
            } else {
                alert('Xəta baş verdi: ' + (data.message || 'Naməlum xəta'));
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Əlaqə xətası baş verdi');
        }
    });
    
    // Edit modalı bağlama cəhdləri
    function attemptCloseEditModal() {
        if (hasUnsavedChanges) {
            pendingClose = true;
            showModal(warningModal);
        } else {
            hideModal(editModal);
        }
    }
    
    cancelEditBtn.addEventListener('click', attemptCloseEditModal);
    closeEditModalBtn.addEventListener('click', attemptCloseEditModal);
    
    // Overlay-ə klik edəndə
    editModal.addEventListener('click', function(e) {
        if (e.target === editModal) {
            attemptCloseEditModal();
        }
    });
    
    // Warning modal davranışları
    stayOnModalBtn.addEventListener('click', function() {
        hideModal(warningModal);
        pendingClose = false;
    });
    
    discardChangesBtn.addEventListener('click', function() {
        hasUnsavedChanges = false;
        hideModal(warningModal);
        hideModal(editModal);
        pendingClose = false;
    });

    // ============= DELETE FUNKSIONALLARI =============
    
    // Delete düyməsinə klik (yalnız post kartındakı delete düymələri)
    document.querySelectorAll('.js-open-delete').forEach(btn => {
        btn.addEventListener('click', function() {
            currentPostId = this.dataset.postId;
            const title = this.dataset.title || '';
            
            deleteTitleSpan.textContent = title;
            showModal(deleteModal);
        });
    });
    
    // Silməni təsdiqlə
    confirmDeleteBtn.addEventListener('click', async function() {
        if (!currentPostId) return;

        try {
            const response = await fetch(`/blog/post/${currentPostId}/delete/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                hideModal(deleteModal);
                location.reload();
            } else {
                alert('Xəta baş verdi: ' + (data.message || 'Naməlum xəta'));
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Əlaqə xətası baş verdi');
        }
    });
    
    // Delete modalı bağla
    cancelDeleteBtn.addEventListener('click', function() {
        hideModal(deleteModal);
    });
    
    deleteModal.addEventListener('click', function(e) {
        if (e.target === deleteModal) {
            hideModal(deleteModal);
        }
    });

    // ============= HELPER FUNKSIYALAR =============
    
    function showModal(modal) {
        if (!modal) return;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
    
    function hideModal(modal) {
        if (!modal) return;
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
    
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    
    // ESC düyməsi ilə modalları bağla
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            if (warningModal.classList.contains('active')) {
                hideModal(warningModal);
            } else if (editModal.classList.contains('active')) {
                attemptCloseEditModal();
            } else if (deleteModal.classList.contains('active')) {
                hideModal(deleteModal);
            }
        }
    });
});
