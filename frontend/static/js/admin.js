/**
 * Admin Panel JavaScript - Optimized Version
 */
document.addEventListener('DOMContentLoaded', () => {

    console.log('Admin JS started');
    
    // Проверка всех meta-тегов
    const metaTags = document.querySelectorAll('meta');
    console.log('Meta tags found:', metaTags.length);
    metaTags.forEach(meta => {
        console.log('Meta:', meta.getAttribute('name'), meta.getAttribute('content'));
    });
    
    // 1. Menu Highlighting
    const highlightActiveMenu = () => {
        const currentPath = window.location.pathname;
        document.querySelectorAll('.nav-link').forEach(link => {
            const linkPath = link.getAttribute('href');
            const isActive = linkPath === currentPath || 
                           (linkPath !== '/' && currentPath.startsWith(linkPath));
            link.classList.toggle('active', isActive);
            
            if (isActive) {
                const dropdown = link.closest('.dropdown');
                dropdown?.querySelector('.dropdown-toggle').classList.add('active');
            }
        });
    };

    // 2. Enhanced Form Handling
    const setupFormHandlers = () => {
        document.querySelectorAll('form').forEach(form => {
            // Общая валидация для всех форм
            form.addEventListener('submit', function(e) {
                // Для формы трек-номера - своя обработка
                if (this.id === 'trackingForm') {
                    e.preventDefault(); // Отменяем стандартную отправку
                    
                    const trackNumber = this.querySelector('#trackNumber').value.trim();
                    if (!trackNumber) {
                        alert('Please enter tracking number');
                        return;
                    }
                    
                    // Показываем индикатор загрузки
                    const submitBtn = this.querySelector('button[type="submit"]');
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';
                    
                    // AJAX-отправка
                    fetch('/orders/ship', {
                        method: 'POST',
                        body: new FormData(this)
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            window.location.reload();
                        } else {
                            alert(data.message || 'Error updating order');
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = 'Mark as Shipped';
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('An error occurred');
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = 'Mark as Shipped';
                    });
                    
                    return;
                }
                
                // Стандартная обработка для других POST-форм
                if (form.method.toUpperCase() === 'POST') {
                    if (!this.checkValidity()) {
                        e.preventDefault();
                        const invalidFields = this.querySelectorAll(':invalid');
                        invalidFields[0]?.focus();
                        return;
                    }
                    
                    if (this.classList.contains('delete-form') && 
                        !confirm('Are you sure you want to delete this?')) {
                        e.preventDefault();
                    }
                }
            });
            
            // Стилизация невалидных полей
            form.querySelectorAll('input, select, textarea').forEach(field => {
                field.addEventListener('invalid', () => {
                    field.classList.add('is-invalid');
                });
                field.addEventListener('input', () => {
                    if (field.checkValidity()) {
                        field.classList.remove('is-invalid');
                    }
                });
            });
        });
    };

    // 3. Dropdown Management
    const setupDropdowns = () => {
        document.addEventListener('click', (e) => {
            const isDropdown = e.target.closest('.dropdown');
            document.querySelectorAll('.dropdown-menu').forEach(menu => {
                menu.style.display = isDropdown ? '' : 'none';
            });
        });
    };

    // 4. Flash Messages Handling (IMPROVED)
    const setupFlashMessages = () => {
        const alerts = document.querySelectorAll('.alert');
        if (alerts.length) {
            // Auto-dismiss after 5 seconds
            alerts.forEach(alert => {
                setTimeout(() => {
                    alert.style.transition = 'opacity 0.5s ease-out';
                    alert.style.opacity = '0';
                    setTimeout(() => alert.remove(), 500);
                }, 5000);
                
                // Manual dismiss
                const closeBtn = alert.querySelector('.btn-close');
                if (closeBtn) {
                    closeBtn.addEventListener('click', () => {
                        alert.style.transition = 'opacity 0.3s ease-out';
                        alert.style.opacity = '0';
                        setTimeout(() => alert.remove(), 300);
                    });
                }
            });
            
            // Clear flash from session after display
            if (window.location.search.indexOf('flash_cleared') === -1) {
                fetch('/clear-flash', { method: 'POST' })
                    .then(() => {
                        const url = new URL(window.location);
                        url.searchParams.set('flash_cleared', '1');
                        window.history.replaceState({}, '', url);
                    })
                    .catch(console.error);
            }
        }
    };

    // 5. Journal Operations
    const setupJournalOperations = () => {
        // Delete confirmation with loading state
        document.querySelectorAll('.delete-journal-form').forEach(form => {
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                const button = this.querySelector('button[type="submit"]');
                const originalText = button.innerHTML;
                
                if (confirm('Are you sure you want to delete this journal?')) {
                    button.disabled = true;
                    button.innerHTML = `
                        <span class="spinner-border spinner-border-sm" role="status"></span>
                        Deleting...
                    `;
                    
                    // Submit form after confirmation
                    setTimeout(() => {
                        this.submit();
                    }, 300);
                }
            });
        });
    };

    // 6. Journal ID Validation
    const setupJournalIdValidation = () => {
        const journalIdInput = document.getElementById('journal_id');
        if (!journalIdInput) return;

        journalIdInput.addEventListener('blur', debounce(async () => {
            const id = journalIdInput.value.trim();
            if (!id) return;

            try {
                const response = await fetch(`/api/check_journal_id/${id}`);
                const data = await response.json();
                
                if (data.exists) {
                    alert('This journal ID is already taken!');
                    journalIdInput.focus();
                }
            } catch (error) {
                console.error('Journal ID check error:', error);
            }
        }, 500));
    };

    // Helper Functions
    const debounce = (func, delay) => {
        let timeout;
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), delay);
        };
    };

    const showAlert = (message, type = 'success') => {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.style.position = 'fixed';
        alertDiv.style.top = '20px';
        alertDiv.style.right = '20px';
        alertDiv.style.zIndex = '9999';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.parentNode.removeChild(alertDiv);
            }
        }, 5000);
    };

    const setupOrderShipping = () => {
        document.addEventListener('click', async (e) => {
            if (e.target.classList.contains('mark-shipped')) {
                const orderId = e.target.dataset.orderId;
                const row = e.target.closest('tr');
                
                const trackNumber = prompt('Введите трек-номер для заказа #' + orderId);
                if (!trackNumber) return;
                
                const originalBtnHTML = e.target.innerHTML;
                e.target.disabled = true;
                e.target.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';
                
                try {
                    const response = await fetch('/orders/ship', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            order_id: parseInt(orderId),
                            track_number: trackNumber
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        row.remove();
                        alert(`Заказ #${orderId} успешно отмечен как отправленный!`);
                    } else {
                        throw new Error(data.message || 'Ошибка сервера');
                    }
                } catch (error) {
                    console.error('Error:', error);
                    alert(error.message || 'Произошла ошибка при обновлении заказа');
                    e.target.disabled = false;
                    e.target.innerHTML = originalBtnHTML;
                }
            }
        });
    };

    // функция для инициализации кнопок редактирования
    const initEditTrackingButtons = () => {
        document.querySelectorAll('.edit-tracking').forEach(btn => {
            btn.addEventListener('click', function() {
                const orderId = this.dataset.orderId;
                const currentTracking = this.dataset.currentTracking || '';
                
                document.getElementById('modalOrderId').textContent = orderId;
                document.getElementById('newTrackingNumber').value = currentTracking;
                
                const editModal = new bootstrap.Modal(document.getElementById('editTrackingModal'));
                editModal.show();
            });
        });
    };

    // Initialize all handlers
    highlightActiveMenu();
    setupFormHandlers();
    setupDropdowns();
    setupFlashMessages();
    setupJournalOperations();
    setupJournalIdValidation();
    setupOrderShipping();
    initEditTrackingButtons();

    console.log('Admin JS initialized');
});