document.addEventListener('DOMContentLoaded', () => {
    
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const closeBtn = document.getElementById('sidebar-close');
  
    const btnInstructions = document.getElementById('btn-instructions');
    const btnAbout = document.getElementById('btn-about');
  
    const pageInstructions = document.getElementById('page-instructions');
    const pageAbout = document.getElementById('page-about');
  
    
    function openSidebar(pageId) {
    
      sidebar.classList.add('open');
      overlay.classList.add('active');
  
    
      if (pageId === 'instructions') {
        pageInstructions.style.display = 'block';
        pageAbout.style.display = 'none';
      } else if (pageId === 'about') {
        pageInstructions.style.display = 'none';
        pageAbout.style.display = 'block';
      }
    }
  
    
    function closeSidebar() {
      sidebar.classList.remove('open');
      overlay.classList.remove('active');
    }
  
    
    btnInstructions.addEventListener('click', () => openSidebar('instructions'));
    btnAbout.addEventListener('click', () => openSidebar('about'));
    
    closeBtn.addEventListener('click', closeSidebar);
    overlay.addEventListener('click', closeSidebar);
});