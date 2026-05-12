/* Waqf Contractor Portal — JS */
'use strict';

document.addEventListener('DOMContentLoaded', function () {

  // ── Quantity stepper ────────────────────────────────────────
  document.querySelectorAll('.cp-qty-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      const input  = this.closest('.cp-qty-wrap').querySelector('.cp-qty-input');
      const step   = parseFloat(input.dataset.step || 0.5);
      let   val    = parseFloat(input.value || 0);
      if (this.dataset.action === 'inc') val = Math.round((val + step) * 100) / 100;
      if (this.dataset.action === 'dec') val = Math.max(0, Math.round((val - step) * 100) / 100);
      input.value = val;
      input.dispatchEvent(new Event('input'));
    });
  });

  // ── BOQ item selector ────────────────────────────────────────
  document.querySelectorAll('.cp-boq-option').forEach(opt => {
    opt.addEventListener('click', function () {
      document.querySelectorAll('.cp-boq-option').forEach(o => o.classList.remove('selected'));
      this.classList.add('selected');
      const hidden = document.getElementById('boq_id');
      if (hidden) hidden.value = this.dataset.id;

      // Update UOM display
      const uomEl = document.querySelector('.cp-qty-uom');
      if (uomEl) uomEl.textContent = this.dataset.uom || '';

      // Update remaining
      const remEl = document.getElementById('remaining-qty');
      if (remEl) remEl.textContent = this.dataset.remaining || '0';

      // Live value preview
      updateValuePreview();
    });
  });

  // ── Live value preview ────────────────────────────────────────
  function updateValuePreview() {
    const qtyInput   = document.querySelector('.cp-qty-input');
    const boqOpt     = document.querySelector('.cp-boq-option.selected');
    const previewEl  = document.getElementById('value-preview');
    if (!qtyInput || !boqOpt || !previewEl) return;

    const qty   = parseFloat(qtyInput.value  || 0);
    const price = parseFloat(boqOpt.dataset.price || 0);
    const val   = qty * price;
    previewEl.textContent = val.toLocaleString('ar-SA', {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    }) + ' ريال';
  }

  const qtyInputEl = document.querySelector('.cp-qty-input');
  if (qtyInputEl) qtyInputEl.addEventListener('input', updateValuePreview);

  // ── Photo upload preview ──────────────────────────────────────
  const photoInput = document.getElementById('photo-input');
  const photoZone  = document.getElementById('photo-zone');
  const photoGrid  = document.getElementById('photo-preview-grid');

  if (photoZone && photoInput) {
    photoZone.addEventListener('click', () => photoInput.click());

    photoZone.addEventListener('dragover', e => {
      e.preventDefault();
      photoZone.style.borderColor = 'var(--teal)';
    });

    photoZone.addEventListener('dragleave', () => {
      photoZone.style.borderColor = '';
    });

    photoZone.addEventListener('drop', e => {
      e.preventDefault();
      photoZone.style.borderColor = '';
      const dt = e.dataTransfer;
      if (dt.files.length) handleFiles(dt.files);
    });

    photoInput.addEventListener('change', function () {
      if (this.files.length) handleFiles(this.files);
    });
  }

  function handleFiles(files) {
    if (!photoGrid) return;
    Array.from(files).forEach(file => {
      if (!file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = e => {
        const img = document.createElement('img');
        img.src = e.target.result;
        img.className = 'cp-photo-thumb';
        img.alt = file.name;
        photoGrid.appendChild(img);
      };
      reader.readAsDataURL(file);
    });

    // Show count
    const countEl = document.getElementById('photo-count');
    if (countEl) {
      const total = (photoGrid ? photoGrid.querySelectorAll('img').length : 0) + files.length;
      countEl.textContent = total + ' صورة';
    }
  }

  // ── Success / error banners auto-dismiss ─────────────────────
  document.querySelectorAll('.cp-success, .cp-error').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity 0.4s';
      el.style.opacity    = '0';
      setTimeout(() => el.remove(), 400);
    }, 4000);
  });

  // ── Confirm before submit ─────────────────────────────────────
  const workForm = document.getElementById('work-log-form');
  if (workForm) {
    workForm.addEventListener('submit', function (e) {
      const boq = document.querySelector('.cp-boq-option.selected');
      const qty = parseFloat(document.querySelector('.cp-qty-input')?.value || 0);
      if (!boq) {
        e.preventDefault();
        showAlert('يرجى اختيار بند من جدول الكميات');
        return;
      }
      if (qty <= 0) {
        e.preventDefault();
        showAlert('يرجى إدخال الكمية المنفذة');
        return;
      }
      // Check remaining qty
      const remaining = parseFloat(boq.dataset.remaining || 0);
      if (qty > remaining * 1.1) {
        const confirmed = confirm(
          'الكمية المدخلة تتجاوز الكمية المتبقية بنسبة تزيد عن 10%.\n' +
          'سيُطلب منك إنشاء طلب تعديل كميات.\n\n' +
          'هل تريد المتابعة؟'
        );
        if (!confirmed) e.preventDefault();
      }
    });
  }

  function showAlert(msg) {
    const el = document.createElement('div');
    el.className = 'cp-error';
    el.textContent = msg;
    const container = document.querySelector('.cp-container');
    if (container) container.prepend(el);
    setTimeout(() => el.remove(), 3000);
  }

  // ── Certificate log checkboxes total ─────────────────────────
  document.querySelectorAll('.cert-log-check').forEach(chk => {
    chk.addEventListener('change', updateCertTotal);
  });

  function updateCertTotal() {
    let total = 0;
    document.querySelectorAll('.cert-log-check:checked').forEach(chk => {
      total += parseFloat(chk.dataset.value || 0);
    });
    const totalEl = document.getElementById('cert-total');
    if (totalEl) {
      totalEl.textContent = total.toLocaleString('ar-SA', {
        minimumFractionDigits: 2
      }) + ' ريال';
    }
  }
});
