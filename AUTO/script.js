// --- Навігація SPA табів ---
const sections = document.querySelectorAll('.tab-section');
const navLinks = document.querySelectorAll('.nav-link');

function switchTab(hash) {
    let toShow = document.querySelector(`#${hash}`);
    if (!toShow) {
        toShow = document.getElementById('home'); // default
        hash = 'home';
    }
    sections.forEach(s => s.classList.remove('active'));
    toShow.classList.add('active');
    navLinks.forEach(link => link.classList.toggle('active', link.getAttribute('href').slice(1) === hash));
    window.location.hash = hash;
}

navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const hash = link.getAttribute('href').slice(1);
        switchTab(hash);
    });
});
// Відкриваємо потрібну вкладку при завантаженні
window.addEventListener('DOMContentLoaded', () => {
    let initial = window.location.hash.substring(1);
    switchTab(initial);
});

// --- КНОПКА Привіт ---
document.getElementById('hello-btn').addEventListener('click', function() {
    alert('Привіт! Вітаю на сайті!');
});

// --- Карта України / Tooltip / Modal ---
const map = document.getElementById('ukraine-map');
const tooltip = document.getElementById('tooltip');
const modal = document.getElementById('modal');
const modalBody = document.getElementById('modal-body');
const modalClose = document.querySelector('.modal-close');
const mapRegions = map.querySelectorAll('.region');

const regionInfo = {
    'Київська область': 'Київська область — центр України, столиця Україна — місто Київ.',
    'Львівська область': 'Львівська область — архітектурна перлина зі Львовом та карпатською природою.',
    'Одеська область': 'Одеська область — морське узбережжя, порт Одеса і багата кухня.',
    'Харківська область': 'Харківська область — науковий і освітній центр на сході країни.',
};

mapRegions.forEach(region => {
    region.addEventListener('mousemove', e => {
        const name = region.dataset.region;
        tooltip.innerText = name;
        tooltip.classList.add('active');
        const bounds = map.getBoundingClientRect();
        tooltip.style.left = (e.clientX - bounds.left + 20) + 'px';
        tooltip.style.top = (e.clientY - bounds.top - 14) + 'px';
        region.classList.add('active');
    });
    region.addEventListener('mouseleave', () => {
        tooltip.classList.remove('active');
        region.classList.remove('active');
    });
    region.addEventListener('click', e => {
        e.stopPropagation();
        const name = region.dataset.region;
        modalBody.innerHTML = `<h3>${name}</h3><p>${regionInfo[name] || 'Немає інформації.'}</p>`;
        modal.classList.add('show');
    });
});
modalClose.onclick = () => modal.classList.remove('show');
window.onclick = e => {
    if (e.target === modal) modal.classList.remove('show');
};

// --- Галерея: слайдер ---
const galleryImgs = document.querySelectorAll('.gallery-img');
const leftArrow = document.querySelector('.gallery-arrow.left');
const rightArrow = document.querySelector('.gallery-arrow.right');
let galleryIdx = 0;
function showGallery(idx) {
    galleryImgs.forEach((img, i) => img.classList.toggle('active', i === idx));
}
function galleryPrev() {
    galleryIdx = (galleryIdx - 1 + galleryImgs.length) % galleryImgs.length;
    showGallery(galleryIdx);
}
function galleryNext() {
    galleryIdx = (galleryIdx + 1) % galleryImgs.length;
    showGallery(galleryIdx);
}
leftArrow.addEventListener('click', galleryPrev);
rightArrow.addEventListener('click', galleryNext);

// --- Форма зворотного звʼязку ---
const contactForm = document.getElementById('contact-form');
if (contactForm) {
    contactForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const name = contactForm.name.value.trim();
        const email = contactForm.email.value.trim();
        const msg = contactForm.msg.value.trim();
        const successDiv = document.getElementById('contact-success');
        if (name && email && msg) {
            successDiv.textContent = 'Дякуємо за звернення, ' + name + '! Ми звʼяжемося найближчим часом.';
            contactForm.reset();
            setTimeout(() => successDiv.textContent = '', 4000);
        } else {
            successDiv.textContent = 'Заповніть усі поля!';
            successDiv.style.color = 'red';
            setTimeout(() => {
                successDiv.textContent = '';
                successDiv.style.color = '#2196f3';
            }, 2000);
        }
    });
}
