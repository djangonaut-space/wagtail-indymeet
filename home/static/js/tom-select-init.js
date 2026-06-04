document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('select.tom-select').forEach(function (el) {
        new TomSelect(el, {
            plugins: ['remove_button'],
            maxOptions: null,
        });
    });
});
