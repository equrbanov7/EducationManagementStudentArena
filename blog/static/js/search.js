
  const blogContainer = document.getElementById("blogContainer");
  const searchInput = document.getElementById("searchInput");

  const cards = Array.from(blogContainer.querySelectorAll(".blog-card"));

  searchInput.addEventListener("input", (e) => {
    const searchTerm = e.target.value.toLowerCase().trim();

    cards.forEach((card) => {
      const title = card.querySelector(".card-title").innerText.toLowerCase();
      const excerpt = card
        .querySelector(".card-excerpt")
        .innerText.toLowerCase();

      const matches =
        title.includes(searchTerm) || excerpt.includes(searchTerm);

      // Uyğun gəlməyənləri gizlədirik
      card.style.display = matches ? "" : "none";
    });
  });
