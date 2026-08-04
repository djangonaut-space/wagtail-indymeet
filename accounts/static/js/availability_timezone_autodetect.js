document.addEventListener("DOMContentLoaded", () => {
    const slotsField = document.getElementById("id_slots");
    const timezoneSelect = document.getElementById("id_slots_timezone");

    if (!slotsField || !timezoneSelect) {
        return;
    }

    const slots = JSON.parse(slotsField.value);
    if (slots.length > 0) {
        return;
    }

    const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const hasMatchingOption = Array.from(timezoneSelect.options).some(
        (option) => option.value === browserTimezone
    );

    if (hasMatchingOption) {
        timezoneSelect.value = browserTimezone;
        // Notify listeners (e.g. the availability grid's own script) that
        // the timezone changed, since a programmatic `.value` assignment
        // does not fire a native "change" event.
        timezoneSelect.dispatchEvent(new Event("change", { bubbles: true }));
    }
});
