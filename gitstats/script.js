const themeSelect = document.getElementById('theme');

// Get the current theme from local storage
const currentTheme = localStorage.getItem('theme');

// If a theme is stored in local storage, apply it to the page
if (currentTheme) {
  document.body.style.color = getThemeColor(currentTheme);
  document.body.style.backgroundColor = getThemeBackgroundColor(currentTheme);
}

// Add an event listener to the theme select element
themeSelect.addEventListener('change', () => {
  const theme = themeSelect.value;
  // Store the selected theme in local storage
  localStorage.setItem('theme', theme);
  // Apply the selected theme to the page
  document.body.style.color = getThemeColor(theme);
  document.body.style.backgroundColor = getThemeBackgroundColor(theme);
});

// Helper functions to get the theme color and background color
function getThemeColor(theme) {
  switch (theme) {
    case 'default':
      return 'black';
    case 'green':
      return 'black';
    default:
      return 'black';
  }
}

function getThemeBackgroundColor(theme) {
  switch (theme) {
    case 'default':
      return '#ffffff';
    case 'green':
      return '#dfd';
    default:
      return '#ffffff';
  }
}
