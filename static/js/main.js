/* myInstructor 2.0 Main JavaScript */

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

// Main app initialization
function initializeApp() {
    // Initialize tooltips
    initializeTooltips();
    
    // Initialize form validation
    initializeFormValidation();
    
    // Initialize auto-refresh for certain pages
    initializeAutoRefresh();
    
    // Initialize keyboard shortcuts
    initializeKeyboardShortcuts();
    
    // Initialize notification system
    initializeNotifications();
    
    console.log('myInstructor 2.0 initialized successfully');
}

// Initialize Bootstrap tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Form validation enhancement
function initializeFormValidation() {
    // Add real-time validation for required fields
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        const requiredInputs = form.querySelectorAll('input[required], select[required], textarea[required]');
        
        requiredInputs.forEach(input => {
            input.addEventListener('blur', function() {
                validateField(this);
            });
            
            input.addEventListener('input', function() {
                if (this.classList.contains('is-invalid')) {
                    validateField(this);
                }
            });
        });
        
        // Form submission validation
        form.addEventListener('submit', function(event) {
            if (!validateForm(this)) {
                event.preventDefault();
                event.stopPropagation();
            }
            this.classList.add('was-validated');
        });
    });
}

// Validate individual field
function validateField(field) {
    const isValid = field.checkValidity();
    
    if (isValid) {
        field.classList.remove('is-invalid');
        field.classList.add('is-valid');
        hideFieldError(field);
    } else {
        field.classList.remove('is-valid');
        field.classList.add('is-invalid');
        showFieldError(field, field.validationMessage);
    }
    
    return isValid;
}

// Validate entire form
function validateForm(form) {
    const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!validateField(input)) {
            isValid = false;
        }
    });
    
    return isValid;
}

// Show field error message
function showFieldError(field, message) {
    const existingError = field.parentNode.querySelector('.invalid-feedback');
    if (existingError) {
        existingError.textContent = message;
    } else {
        const errorElement = document.createElement('div');
        errorElement.className = 'invalid-feedback';
        errorElement.textContent = message;
        field.parentNode.appendChild(errorElement);
    }
}

// Hide field error message
function hideFieldError(field) {
    const existingError = field.parentNode.querySelector('.invalid-feedback');
    if (existingError) {
        existingError.remove();
    }
}

// Auto-refresh functionality for real-time updates
function initializeAutoRefresh() {
    // Only enable on dashboard pages
    if (window.location.pathname.includes('dashboard') || window.location.pathname.includes('whatsapp')) {
        setInterval(function() {
            refreshPageData();
        }, 30000); // Refresh every 30 seconds
    }
}

// Refresh page data without full reload
function refreshPageData() {
    // Update timestamps
    updateTimestamps();
    
    // Update notification badges (if any)
    updateNotificationBadges();
}

// Update relative timestamps
function updateTimestamps() {
    const timestamps = document.querySelectorAll('[data-timestamp]');
    timestamps.forEach(element => {
        const timestamp = element.getAttribute('data-timestamp');
        if (timestamp) {
            element.textContent = formatRelativeTime(new Date(timestamp));
        }
    });
}

// Format relative time (e.g., "2 minutes ago")
function formatRelativeTime(date) {
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);
    
    if (diffInSeconds < 60) {
        return 'Just now';
    } else if (diffInSeconds < 3600) {
        const minutes = Math.floor(diffInSeconds / 60);
        return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    } else if (diffInSeconds < 86400) {
        const hours = Math.floor(diffInSeconds / 3600);
        return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    } else {
        const days = Math.floor(diffInSeconds / 86400);
        return `${days} day${days > 1 ? 's' : ''} ago`;
    }
}

// Keyboard shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(event) {
        // Ctrl/Cmd + K for quick search (if implemented)
        if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
            event.preventDefault();
            openQuickSearch();
        }
        
        // ESC to close modals
        if (event.key === 'Escape') {
            closeTopModal();
        }
        
        // Ctrl/Cmd + S to save forms (prevent default browser save)
        if ((event.ctrlKey || event.metaKey) && event.key === 's') {
            const activeForm = document.querySelector('form:focus-within');
            if (activeForm) {
                event.preventDefault();
                activeForm.requestSubmit();
            }
        }
    });
}

// Quick search functionality (placeholder)
function openQuickSearch() {
    // This could be implemented as a search modal
    console.log('Quick search activated');
}

// Close the topmost modal
function closeTopModal() {
    const openModals = document.querySelectorAll('.modal.show');
    if (openModals.length > 0) {
        const topModal = openModals[openModals.length - 1];
        const modalInstance = bootstrap.Modal.getInstance(topModal);
        if (modalInstance) {
            modalInstance.hide();
        }
    }
}

// Notification system
function initializeNotifications() {
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const alertInstance = new bootstrap.Alert(alert);
            alertInstance.close();
        }, 5000);
    });
}

// Update notification badges
function updateNotificationBadges() {
    // This would typically fetch from an API
    // For now, it's a placeholder for future enhancement
}

// Utility functions
const utils = {
    // Format phone number for display
    formatPhoneNumber: function(phone) {
        if (!phone) return '';
        
        // Remove all non-digits
        const digits = phone.replace(/\D/g, '');
        
        // Format based on length
        if (digits.length === 10) {
            return digits.replace(/(\d{3})(\d{3})(\d{4})/, '($1) $2-$3');
        } else if (digits.length === 11 && digits[0] === '1') {
            return digits.replace(/(\d{1})(\d{3})(\d{3})(\d{4})/, '+$1 ($2) $3-$4');
        }
        
        return phone; // Return original if can't format
    },
    
    // Format currency
    formatCurrency: function(amount, currency = 'USD') {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: currency
        }).format(amount);
    },
    
    // Format date for display
    formatDate: function(date, options = {}) {
        const defaultOptions = {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        };
        
        return new Intl.DateTimeFormat('en-US', { ...defaultOptions, ...options }).format(new Date(date));
    },
    
    // Show loading state on element
    showLoading: function(element) {
        element.classList.add('loading');
        element.disabled = true;
    },
    
    // Hide loading state on element
    hideLoading: function(element) {
        element.classList.remove('loading');
        element.disabled = false;
    },
    
    // Show toast notification
    showToast: function(message, type = 'info') {
        const toastContainer = document.getElementById('toast-container') || createToastContainer();
        
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
        
        // Remove toast element after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    },
    
    // Confirm action with modal
    confirmAction: function(message, callback) {
        if (confirm(message)) {
            callback();
        }
    },
    
    // Copy text to clipboard
    copyToClipboard: function(text) {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(() => {
                this.showToast('Copied to clipboard', 'success');
            });
        } else {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            this.showToast('Copied to clipboard', 'success');
        }
    }
};

// Create toast container if it doesn't exist
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    container.style.zIndex = '1055';
    document.body.appendChild(container);
    return container;
}

// Table enhancements
function initializeTableFeatures() {
    // Add sorting capability to tables with .sortable class
    const sortableTables = document.querySelectorAll('table.sortable');
    sortableTables.forEach(table => {
        const headers = table.querySelectorAll('th[data-sort]');
        headers.forEach(header => {
            header.style.cursor = 'pointer';
            header.addEventListener('click', () => sortTable(table, header));
        });
    });
}

// Sort table by column
function sortTable(table, header) {
    const columnIndex = Array.from(header.parentNode.children).indexOf(header);
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const isAscending = header.classList.contains('sort-asc');
    const direction = isAscending ? -1 : 1;
    
    // Clear all sort classes
    table.querySelectorAll('th').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
    });
    
    // Add appropriate sort class
    header.classList.add(isAscending ? 'sort-desc' : 'sort-asc');
    
    // Sort rows
    rows.sort((a, b) => {
        const aValue = a.children[columnIndex].textContent.trim();
        const bValue = b.children[columnIndex].textContent.trim();
        
        // Try to parse as numbers
        const aNum = parseFloat(aValue);
        const bNum = parseFloat(bValue);
        
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return (aNum - bNum) * direction;
        }
        
        // Sort as strings
        return aValue.localeCompare(bValue) * direction;
    });
    
    // Reorder DOM
    rows.forEach(row => tbody.appendChild(row));
}

// Progress bar animations
function animateProgressBars() {
    const progressBars = document.querySelectorAll('.progress-bar');
    progressBars.forEach(bar => {
        const width = bar.style.width || bar.getAttribute('aria-valuenow') + '%';
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.width = width;
        }, 100);
    });
}

// Form auto-save functionality
function initializeAutoSave() {
    const autoSaveForms = document.querySelectorAll('form[data-autosave]');
    autoSaveForms.forEach(form => {
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('input', debounce(() => {
                saveFormData(form);
            }, 1000));
        });
        
        // Load saved data on page load
        loadFormData(form);
    });
}

// Debounce function for performance
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Save form data to localStorage
function saveFormData(form) {
    const formId = form.id || form.getAttribute('data-autosave');
    const formData = new FormData(form);
    const data = {};
    
    for (let [key, value] of formData.entries()) {
        data[key] = value;
    }
    
    localStorage.setItem(`autosave_${formId}`, JSON.stringify(data));
    utils.showToast('Draft saved', 'info');
}

// Load form data from localStorage
function loadFormData(form) {
    const formId = form.id || form.getAttribute('data-autosave');
    const savedData = localStorage.getItem(`autosave_${formId}`);
    
    if (savedData) {
        const data = JSON.parse(savedData);
        Object.keys(data).forEach(key => {
            const input = form.querySelector(`[name="${key}"]`);
            if (input) {
                input.value = data[key];
            }
        });
    }
}

// Clear saved form data
function clearSavedFormData(formId) {
    localStorage.removeItem(`autosave_${formId}`);
}

// Export utilities for global access
window.myInstructorUtils = utils;
window.showToast = utils.showToast;
window.confirmAction = utils.confirmAction;
window.copyToClipboard = utils.copyToClipboard;

// Initialize additional features when needed
document.addEventListener('DOMContentLoaded', function() {
    // Initialize table features if tables exist
    if (document.querySelector('table')) {
        initializeTableFeatures();
    }
    
    // Animate progress bars if they exist
    if (document.querySelector('.progress-bar')) {
        animateProgressBars();
    }
    
    // Initialize auto-save if forms with data-autosave exist
    if (document.querySelector('form[data-autosave]')) {
        initializeAutoSave();
    }
});
