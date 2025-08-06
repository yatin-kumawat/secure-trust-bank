document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("createForm");
  const submitBtn = document.getElementById("submitBtn");

  const is18OrOlder = (dobStr) => {
    if (!dobStr) return false;
    const dob = new Date(dobStr);
    const today = new Date();
    const age = today.getFullYear() - dob.getFullYear();
    const m = today.getMonth() - dob.getMonth();
    return age > 18 || (age === 18 && (m > 0 || (m === 0 && today.getDate() >= dob.getDate())));
  };

  const touchedFields = {};

  const markTouched = (fieldName) => {
    touchedFields[fieldName] = true;
  };

  const showError = (fieldName, isValid, value) => {
    const errorElement = document.getElementById(`${fieldName}Error`);
    if (!errorElement) return;

    if (!touchedFields[fieldName] || value === "") {
      errorElement.classList.add("hidden");
    } else {
      errorElement.classList.toggle("hidden", isValid);
    }
  };

  const validate = () => {
    const name = form.name.value.trim();
    const city = form.city.value.trim();
    const dob = form.dob.value;
    const gender = form.gender.value;
    const account = form.account.value;
    const amount = form.amount.value;
    const mobile = form.mobile.value.trim();
    const pin = form.pin.value.trim();
    const email = form.email.value.trim();

    const nameValid = /^[a-zA-Z ]{3,}$/.test(name);
    const cityValid = /^[a-zA-Z ]{2,}$/.test(city);
    const dobValid = is18OrOlder(dob);
    const genderValid = gender !== "";
    const accountValid = account === "Savings" || account === "Current";
    const amountNum = parseInt(amount);
    const amountValid = !isNaN(amountNum) && amountNum >= (account === "Current" ? 10000 : 1000);
    const mobileValid = /^[6-9]\d{9}$/.test(mobile);
    const pinValid = /^\d{4}$/.test(pin);
    const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

    // Show errors only if touched and input is not empty
    showError("name", nameValid, name);
    showError("city", cityValid, city);
    showError("dob", dobValid, dob);
    showError("gender", genderValid, gender);
    showError("account", accountValid, account);
    showError("amount", amountValid, amount);
    showError("mobile", mobileValid, mobile);
    showError("pin", pinValid, pin);
    showError("email", emailValid, email);

    const allValid = nameValid && cityValid && dobValid && genderValid && accountValid && amountValid && mobileValid && pinValid && emailValid;
    submitBtn.disabled = !allValid;
  };

  if (form) {
    const inputs = form.querySelectorAll("input, select");
    inputs.forEach((input) => {
      input.addEventListener("input", (e) => {
        if (e.target.name) markTouched(e.target.name);
        validate();
      });
      input.addEventListener("change", (e) => {
        if (e.target.name) markTouched(e.target.name);
        validate();
      });
    });
    validate(); // Initial run
  }


  // ✅ Table Search
  const searchInput = document.getElementById("searchInput");
  if (searchInput) {
    searchInput.value = ""; // Clear old value
    const rows = document.querySelectorAll("#tableBody tr");

    searchInput.addEventListener("input", function () {
      const searchTerm = this.value.toLowerCase();
      let matchCount = 0;

      rows.forEach((row) => {
        const text = row.textContent.toLowerCase();
        const match = text.includes(searchTerm);
        row.style.display = match ? "" : "none";
        if (match) matchCount++;
      });

      const existing = document.getElementById("noResultsRow");
      if (existing) existing.remove();

      if (matchCount === 0) {
        const tbody = document.getElementById("tableBody");
        const newRow = document.createElement("tr");
        newRow.id = "noResultsRow";
        newRow.innerHTML = `
          <td colspan="11" class="p-4 text-center text-red-500 font-semibold">
            🚫 No matching records found.
          </td>`;
        tbody.appendChild(newRow);
      }
    });

    // Trigger once to clear previous state
    const event = new Event("input");
    searchInput.dispatchEvent(event);
  }

  // ✅ Table Sorting
  let sortDirection = {};
  window.sortTable = function (columnIndex) {
    const tbody = document.getElementById("tableBody");
    const rows = Array.from(tbody.querySelectorAll("tr"));

    sortDirection[columnIndex] = !sortDirection[columnIndex];

    rows.sort((a, b) => {
      const aText = a.cells[columnIndex]?.innerText.trim() || "";
      const bText = b.cells[columnIndex]?.innerText.trim() || "";

      const clean = (val) => val.replace(/[₹,]/g, "").toLowerCase();
      const aVal = clean(aText);
      const bVal = clean(bText);

      const aNum = parseFloat(aVal);
      const bNum = parseFloat(bVal);

      if (!isNaN(aNum) && !isNaN(bNum)) {
        return sortDirection[columnIndex] ? aNum - bNum : bNum - aNum;
      } else {
        return sortDirection[columnIndex]
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }
    });

    rows.forEach((row) => tbody.appendChild(row));
  };
});
