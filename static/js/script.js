const navbar = document.getElementById("navbar");
let lastScrollY = window.scrollY;

window.addEventListener("scroll", () => {
    const currentScrollY = window.scrollY;

    if (navbar) {
        navbar.classList.toggle("nav-solid", currentScrollY > 24);
        navbar.classList.toggle("nav-hidden", currentScrollY > lastScrollY && currentScrollY > 160);
    }

    document.querySelectorAll(".parallax-section").forEach((section) => {
        const offset = Math.round(currentScrollY * 0.16);
        section.style.backgroundPosition = `center ${offset}px`;
    });

    lastScrollY = Math.max(currentScrollY, 0);
});

const revealObserver = new IntersectionObserver(
    (entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add("visible");
                revealObserver.unobserve(entry.target);
            }
        });
    },
    { threshold: 0.16 }
);

document.querySelectorAll(".reveal").forEach((element) => {
    revealObserver.observe(element);
});

document.querySelectorAll('a[href^="#"], .smooth-link').forEach((link) => {
    link.addEventListener("click", (event) => {
        const href = link.getAttribute("href");
        if (!href || !href.startsWith("#")) {
            return;
        }

        const target = document.querySelector(href);
        if (!target) {
            return;
        }

        event.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
});

document.querySelectorAll(".flash").forEach((flash) => {
    setTimeout(() => {
        flash.style.opacity = "0";
        flash.style.transform = "translateY(-8px)";
        setTimeout(() => flash.remove(), 300);
    }, 6500);
});
