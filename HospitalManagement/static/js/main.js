// ==================================================
// Hospital Management System - Client Interactions
// ==================================================

document.addEventListener("DOMContentLoaded", function () {

    // Mobile sidebar toggle
    const toggleBtn = document.getElementById("sidebarToggle");
    const sidebar = document.getElementById("sidebar");

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", function () {
            sidebar.classList.toggle("show");
        });

        document.addEventListener("click", function (event) {
            const isClickInside = sidebar.contains(event.target) || toggleBtn.contains(event.target);
            if (!isClickInside && sidebar.classList.contains("show")) {
                sidebar.classList.remove("show");
            }
        });
    }

    // Auto-dismiss alerts after 6 seconds
    document.querySelectorAll(".alert").forEach(function (alertEl) {
        setTimeout(function () {
            if (window.bootstrap) {
                const bsAlert = window.bootstrap.Alert.getOrCreateInstance(alertEl);
                bsAlert.close();
            }
        }, 6000);
    });

});
