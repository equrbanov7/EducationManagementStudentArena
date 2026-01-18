/**
 * forms.js
 * ────────
 * Form işləmə funksiyaları (AJAX, validation, və s.)
 * 
 * Nə edər:
 * - Form error göstərmə
 * - Loading state
 * - Form validation
 */

/**
 * Form error-larını göstər
 * 
 * @param {string} containerId - Error container ID
 * @param {object} errors - Errors {field: [messages]}
 */
function showFormErrors(containerId, errors) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    let errorHtml = '<strong>Xətalar:</strong><ul class="mb-0">';
    
    Object.keys(errors).forEach(field => {
        const messages = errors[field];
        if (Array.isArray(messages)) {
            messages.forEach(msg => {
                errorHtml += `<li>${msg}</li>`;
            });
        } else {
            errorHtml += `<li>${messages}</li>`;
        }
    });
    
    errorHtml += '</ul>';
    
    container.innerHTML = errorHtml;
    container.classList.remove('d-none');
    
    // Scroll to error
    container.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/**
 * Form error-larını silin
 * 
 * @param {string} containerId - Error container ID
 */
function clearFormErrors(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.innerHTML = '';
        container.classList.add('d-none');
    }
}

/**
 * Form input-unu disable/enable et (loading state)
 * 
 * @param {HTMLFormElement} form - Form element
 * @param {boolean} disabled - Disable yoxsa enable
 */
function setFormDisabled(form, disabled) {
    const inputs = form.querySelectorAll('input, textarea, select, button');
    inputs.forEach(input => {
        if (input.type !== 'hidden') {
            input.disabled = disabled;
        }
    });
}

/**
 * Form submission handling (AJAX)
 * 
 * @param {HTMLFormElement} form - Form element
 * @param {string} successCallback - Success function
 * @param {string} errorCallback - Error function
 */
function handleFormSubmit(form, successCallback, errorCallback) {
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const formData = new FormData(this);
        const actionUrl = this.action;
        
        // Disable inputs
        setFormDisabled(this, true);
        
        // Loading button
        const submitBtn = this.querySelector('button[type="submit"]');
        const originalText = submitBtn ? submitBtn.innerHTML : '';
        if (submitBtn) {
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gözləyin...';
        }
        
        fetch(actionUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (successCallback) {
                    window[successCallback](data);
                }
            } else {
                if (errorCallback) {
                    window[errorCallback](data);
                }
            }
        })
        .catch(error => {
            console.error('Form submission error:', error);
            notify('Xəta baş verdi. Lütfən yenidən cəhd edin.', 'error');
        })
        .finally(() => {
            // Enable inputs
            setFormDisabled(this, false);
            
            // Reset button
            if (submitBtn) {
                submitBtn.innerHTML = originalText;
            }
        });
    });
}

/**
 * Dinamik input validation
 * 
 * @param {HTMLInputElement} input - Input element
 * @param {function} validatorFn - Validator function
 */
function addInputValidator(input, validatorFn) {
    input.addEventListener('blur', function() {
        const isValid = validatorFn(this.value);
        
        if (!isValid) {
            this.classList.add('is-invalid');
            this.classList.remove('is-valid');
        } else {
            this.classList.remove('is-invalid');
            this.classList.add('is-valid');
        }
    });
}

/**
 * Email validation
 * 
 * @param {string} email - Email string
 * @returns {boolean} - Is valid
 */
function isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

/**
 * URL validation
 * 
 * @param {string} url - URL string
 * @returns {boolean} - Is valid
 */
function isValidURL(url) {
    try {
        new URL(url);
        return true;
    } catch (e) {
        return false;
    }
}

/**
 * Form data to object conversion
 * 
 * @param {FormData} formData - FormData object
 * @returns {object} - Plain object
 */
function formDataToObject(formData) {
    const object = {};
    formData.forEach((value, key) => {
        if (object.hasOwnProperty(key)) {
            if (!Array.isArray(object[key])) {
                object[key] = [object[key]];
            }
            object[key].push(value);
        } else {
            object[key] = value;
        }
    });
    return object;
}