// ========== UTILITY FUNCTIONS ==========

/**
 * Show a toast notification
 */
function showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `alert-custom alert-${type} fade-in`;
    toast.style.position = 'fixed';
    toast.style.top = '20px';
    toast.style.right = '20px';
    toast.style.maxWidth = '400px';
    toast.style.zIndex = '9999';
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, duration);
}

/**
 * Format date to readable format
 */
function formatDate(dateString) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-US', options);
}

/**
 * Format time to HH:MM format
 */
function formatTime(timeString) {
    if (!timeString) return '';
    const [hours, minutes] = timeString.split(':');
    return `${hours}:${minutes}`;
}

/**
 * Get status badge HTML
 */
function getStatusBadge(status) {
    const badgeMap = {
        'free': '<span class="badge-custom badge-success">🟢 Free</span>',
        'busy': '<span class="badge-custom badge-danger">🔴 Busy</span>',
        'away': '<span class="badge-custom badge-warning">🟡 Away</span>',
        'in_class': '<span class="badge-custom badge-info">🔵 In Class</span>',
        'pending': '<span class="badge-custom badge-warning">⏳ Pending</span>',
        'confirmed': '<span class="badge-custom badge-success">✓ Confirmed</span>',
        'engaged': '<span class="badge-custom badge-info">▶️ Engaged</span>',
        'cancelled': '<span class="badge-custom badge-danger">✗ Cancelled</span>'
    };
    return badgeMap[status] || `<span class="badge-custom">${status}</span>`;
}

/**
 * Format countdown timer
 */
function formatCountdown(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    }
    return `${minutes}m ${secs}s`;
}

/**
 * Validate email format
 */
function isValidEmail(email) {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
}

/**
 * Validate VVCE email
 */
function isValidVVCEEmail(email) {
    return email.endsWith('@vvce.ac.in');
}

/**
 * Debounce function for search inputs
 */
function debounce(func, delay) {
    let timeoutId;
    return function (...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
}

/**
 * Get current time in HH:MM format
 */
function getCurrentTime() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
}

/**
 * Get current date in YYYY-MM-DD format
 */
function getCurrentDate() {
    const now = new Date();
    return now.toISOString().split('T')[0];
}

/**
 * Add hours to time
 */
function addHoursToTime(timeString, hours) {
    const [h, m] = timeString.split(':').map(Number);
    const newHours = (h + hours) % 24;
    return `${String(newHours).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/**
 * Check if time has passed
 */
function hasTimePassed(dateString, timeString) {
    const bookingDateTime = new Date(`${dateString}T${timeString}`);
    return new Date() > bookingDateTime;
}

/**
 * Calculate minutes between two times
 */
function minutesBetween(dateString, timeString) {
    const bookingDateTime = new Date(`${dateString}T${timeString}`);
    const now = new Date();
    return Math.floor((bookingDateTime - now) / 60000);
}

// ========== LOCAL STORAGE HELPERS ==========

/**
 * Save to localStorage
 */
function saveToLocalStorage(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
        console.error('Storage quota exceeded', e);
    }
}

/**
 * Get from localStorage
 */
function getFromLocalStorage(key) {
    try {
        const item = localStorage.getItem(key);
        return item ? JSON.parse(item) : null;
    } catch (e) {
        console.error('Error reading from storage', e);
        return null;
    }
}

/**
 * Remove from localStorage
 */
function removeFromLocalStorage(key) {
    localStorage.removeItem(key);
}

// ========== API HELPERS ==========

/**
 * Make a GET request
 */
async function apiGet(url) {
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('API GET Error:', error);
        showToast('Error loading data', 'danger');
        return null;
    }
}

/**
 * Make a POST request
 */
async function apiPost(url, data) {
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('API POST Error:', error);
        showToast('Error sending data', 'danger');
        return null;
    }
}

/**
 * Make a PUT request
 */
async function apiPut(url, data) {
    try {
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('API PUT Error:', error);
        showToast('Error updating data', 'danger');
        return null;
    }
}

/**
 * Make a DELETE request
 */
async function apiDelete(url) {
    try {
        const response = await fetch(url, { method: 'DELETE' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('API DELETE Error:', error);
        showToast('Error deleting data', 'danger');
        return null;
    }
}

// ========== DOM HELPERS ==========

/**
 * Toggle class on element
 */
function toggleClass(elementId, className) {
    const element = document.getElementById(elementId);
    if (element) element.classList.toggle(className);
}

/**
 * Add class to element
 */
function addClass(elementId, className) {
    const element = document.getElementById(elementId);
    if (element) element.classList.add(className);
}

/**
 * Remove class from element
 */
function removeClass(elementId, className) {
    const element = document.getElementById(elementId);
    if (element) element.classList.remove(className);
}

/**
 * Hide element
 */
function hideElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) element.classList.add('hidden');
}

/**
 * Show element
 */
function showElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) element.classList.remove('hidden');
}

/**
 * Set element text
 */
function setText(elementId, text) {
    const element = document.getElementById(elementId);
    if (element) element.textContent = text;
}

/**
 * Set element HTML
 */
function setHTML(elementId, html) {
    const element = document.getElementById(elementId);
    if (element) element.innerHTML = html;
}

// ========== FORM HELPERS ==========

/**
 * Get form data as object
 */
function getFormData(formId) {
    const form = document.getElementById(formId);
    const formData = new FormData(form);
    const data = {};
    for (let [key, value] of formData.entries()) {
        data[key] = value;
    }
    return data;
}

/**
 * Reset form
 */
function resetForm(formId) {
    const form = document.getElementById(formId);
    if (form) form.reset();
}

/**
 * Set form errors
 */
function setFormErrors(formId, errors) {
    const form = document.getElementById(formId);
    const errorElements = form.querySelectorAll('.error-message');
    errorElements.forEach(el => el.remove());
    
    Object.entries(errors).forEach(([field, message]) => {
        const input = form.querySelector(`[name="${field}"]`);
        if (input) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.style.color = '#ef4444';
            errorDiv.style.fontSize = '12px';
            errorDiv.style.marginTop = '4px';
            errorDiv.textContent = message;
            input.parentElement.appendChild(errorDiv);
        }
    });
}

// ========== EXPORT FOR USE IN MODULES ==========
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        showToast,
        formatDate,
        formatTime,
        getStatusBadge,
        formatCountdown,
        isValidEmail,
        isValidVVCEEmail,
        debounce,
        getCurrentTime,
        getCurrentDate,
        addHoursToTime,
        hasTimePassed,
        minutesBetween,
        saveToLocalStorage,
        getFromLocalStorage,
        removeFromLocalStorage,
        apiGet,
        apiPost,
        apiPut,
        apiDelete,
        toggleClass,
        addClass,
        removeClass,
        hideElement,
        showElement,
        setText,
        setHTML,
        getFormData,
        resetForm,
        setFormErrors
    };
}
