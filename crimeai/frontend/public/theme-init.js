// Applies the saved theme before first paint so the page never flashes the wrong one. Dark is the default.
try {
  if (localStorage.getItem('crimeai-theme') === 'light') document.documentElement.classList.remove('dark')
} catch (e) { /* storage unavailable: keep the default */ }
