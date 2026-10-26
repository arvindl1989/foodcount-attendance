// Shared behaviour for every page.

// Submit a form as soon as a [data-autosubmit] control changes
// (manager status filter, admin date picker).
document.addEventListener("change", function (event) {
  var el = event.target;
  if (el.matches && el.matches("[data-autosubmit]") && el.form && el.value) {
    el.form.submit();
  }
});
