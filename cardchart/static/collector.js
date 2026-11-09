(() => {
  document.querySelectorAll('.collector-art img').forEach(image => {
    const showFallback = () => {
      if (image.hidden) return;
      image.hidden = true;
      const label = document.createElement('span');
      label.className = 'placeholder';
      label.textContent = 'Image unavailable';
      image.after(label);
    };
    image.addEventListener('error', showFallback);
    if (image.complete && !image.naturalWidth) showFallback();
  });
  document.querySelectorAll('[data-goal-cover]').forEach(image => {
    const showFallback = () => { image.hidden = true; image.nextElementSibling.hidden = false; };
    image.addEventListener('error', showFallback);
    if (image.complete && !image.naturalWidth) showFallback();
  });
  document.querySelectorAll('[data-open-dialog]').forEach(button => {
    const dialog = document.getElementById(button.dataset.openDialog);
    if (!dialog) return;
    let scrollY = 0;
    button.addEventListener('click', () => { scrollY = window.scrollY; dialog.showModal(); });
    dialog.querySelector('[data-close-dialog]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => { window.scrollTo(window.scrollX, scrollY); button.focus({preventScroll: true}); });
    const select = dialog.querySelector('[data-version]');
    if (select) select.addEventListener('change', () => {
      const option = select.selectedOptions[0];
      dialog.querySelector('[data-price]').textContent = option.dataset.gbp ? `\u2248 \u00a3${option.dataset.gbp}${option.dataset.eur ? ` (\u20ac${option.dataset.eur})` : ''}` : 'Price unavailable';
      const link = dialog.querySelector('[data-market-link]');
      link.hidden = !option.dataset.cardmarketUrl;
      if (option.dataset.cardmarketUrl) link.href = option.dataset.cardmarketUrl;
      else link.removeAttribute('href');
    });
  });
})();
