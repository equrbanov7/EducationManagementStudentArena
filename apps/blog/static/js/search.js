// 1. Debounce funksiyası (Gözləmə rejimi)
    // Bu funksiya istifadəçi yazmağı dayandırana qədər gözləyir
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

  // 2. Axtarış funksiyası
  function performSearch() {
      const searchInput = document.getElementById('searchInput');
      const query = searchInput.value;
      const gridContainer = document.querySelector('.home-left-column'); // Dəyişəcək hissə
      
      // Vizual effekt: Axtarış gedərkən şəffaflığı azalt
      gridContainer.style.opacity = '0.5';
      gridContainer.style.transition = 'opacity 0.3s';

      // URL-i hazırlayırıq (Məs: /?q=python&page=1)
      const url = new URL(window.location.href);
      url.searchParams.set('q', query);
      url.searchParams.set('page', 1); // Axtarış edəndə həmişə 1-ci səhifəyə qayıt

      // Brauzerin URL sətrini dəyişirik (Səhifə yenilənmədən)
      window.history.pushState({}, '', url);

      // 3. Arxa plana (Backend-ə) sorğu göndəririk
      fetch(url)
          .then(response => response.text())
          .then(html => {
              // Gələn HTML mətnini DOM-a çeviririk
              const parser = new DOMParser();
              const doc = parser.parseFromString(html, 'text/html');
              
              // Təzə səhifədən bizə lazım olan hissəni tapırıq
              const newContent = doc.querySelector('.home-left-column').innerHTML;
              
              // Köhnə hissəni təzəsi ilə əvəz edirik
              gridContainer.innerHTML = newContent;
              
              // Vizual effekti qaytarırıq
              gridContainer.style.opacity = '1';
          })
          .catch(error => {
              console.error('Xəta:', error);
              gridContainer.style.opacity = '1';
          });
  }

  // 4. Inputa "dinləyici" qoşuruq
  const searchInput = document.getElementById('searchInput');
  
  // 1500ms (1.5 saniyə) debounce tətbiq edirik
  searchInput.addEventListener('input', debounce(performSearch, 1000));