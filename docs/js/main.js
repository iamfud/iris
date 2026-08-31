// Iris Docs Site — Navigation & Interactivity

(function() {
  'use strict';

  // Mobile menu toggle
  const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
  const navLinks = document.querySelector('.nav-links');

  if (mobileMenuBtn && navLinks) {
    mobileMenuBtn.addEventListener('click', function() {
      navLinks.classList.toggle('open');
      mobileMenuBtn.setAttribute('aria-expanded', navLinks.classList.contains('open'));
    });

    // Close on link click
    navLinks.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        navLinks.classList.remove('open');
        mobileMenuBtn.setAttribute('aria-expanded', 'false');
      });
    });

    // Close on outside click
    document.addEventListener('click', e => {
      if (!navLinks.contains(e.target) && !mobileMenuBtn.contains(e.target)) {
        navLinks.classList.remove('open');
        mobileMenuBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  // Active nav link highlighting
  const navItems = document.querySelectorAll('.nav-links a[href^="#"]');
  const sections = Array.from(navItems).map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);

  function updateActiveNav() {
    const scrollPos = window.scrollY + 100;
    let active = null;

    sections.forEach((section, i) => {
      if (section && section.offsetTop <= scrollPos && section.offsetTop + section.offsetHeight > scrollPos) {
        active = navItems[i];
      }
    });

    navItems.forEach(item => item.classList.toggle('active', item === active));
  }

  window.addEventListener('scroll', updateActiveNav, { passive: true });
  updateActiveNav();

  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href');
      if (targetId === '#') return;
      
      const target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        const headerOffset = 80;
        const elementPosition = target.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
        
        window.scrollTo({
          top: offsetPosition,
          behavior: 'smooth'
        });

        // Update URL without scroll
        history.pushState(null, '', targetId);
      }
    });
  });

  // TOC active highlighting (for setup page)
  const tocLinks = document.querySelectorAll('.toc a[href^="#"]');
  const tocSections = Array.from(tocLinks).map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);

  function updateActiveToc() {
    const scrollPos = window.scrollY + 120;
    let active = null;

    tocSections.forEach((section, i) => {
      if (section && section.offsetTop <= scrollPos && section.offsetTop + section.offsetHeight > scrollPos) {
        active = tocLinks[i];
      }
    });

    tocLinks.forEach(item => item.classList.toggle('active', item === active));
  }

  if (tocLinks.length) {
    window.addEventListener('scroll', updateActiveToc, { passive: true });
    updateActiveToc();
  }

  // Copy code blocks
  document.querySelectorAll('pre code').forEach(block => {
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';
    btn.setAttribute('aria-label', 'Copy code to clipboard');
    btn.style.cssText = `
      position: absolute;
      top: 8px;
      right: 8px;
      padding: 6px 12px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--fg-muted);
      font-size: 0.75rem;
      font-weight: 500;
      cursor: pointer;
      opacity: 0;
      transition: all 0.2s;
    `;
    
    const pre = block.parentElement;
    pre.style.position = 'relative';
    pre.appendChild(btn);

    pre.addEventListener('mouseenter', () => btn.style.opacity = '1');
    pre.addEventListener('mouseleave', () => btn.style.opacity = '0');

    btn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(block.textContent);
        btn.textContent = 'Copied!';
        btn.style.color = 'var(--accent)';
        setTimeout(() => {
          btn.textContent = 'Copy';
          btn.style.color = '';
        }, 2000);
      } catch (err) {
        btn.textContent = 'Failed';
        setTimeout(() => btn.textContent = 'Copy', 2000);
      }
    });
  });

  // Scroll reveal animation
  const revealElements = document.querySelectorAll('.card, .content-block, .step');
  
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

  revealElements.forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    revealObserver.observe(el);
  });

  // Keyboard navigation for TOC
  document.addEventListener('keydown', e => {
    if (e.key === '/' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      const searchInput = document.querySelector('.search-input');
      if (searchInput) searchInput.focus();
    }
  });

  // Announce current section to screen readers on nav
  let lastAnnounced = null;
  function announceSection() {
    if (sections.length === 0) return;
    const scrollPos = window.scrollY + 100;
    for (const section of sections) {
      if (section && section.offsetTop <= scrollPos && section.offsetTop + section.offsetHeight > scrollPos) {
        if (section.id && section.id !== lastAnnounced) {
          lastAnnounced = section.id;
          // Could use aria-live region here if needed
        }
        break;
      }
    }
  }

  window.addEventListener('scroll', announceSection, { passive: true });

})();