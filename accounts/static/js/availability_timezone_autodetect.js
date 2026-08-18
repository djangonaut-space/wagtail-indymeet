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

    const browserOffset = getBrowserUtcOffsetLabel();
    if (!browserOffset) {
        return;
    }

    const hasMatchingOption = Array.from(timezoneSelect.options).some(
        (option) => option.value === browserOffset
    );

    if (hasMatchingOption) {
        timezoneSelect.value = browserOffset;
        // Notify listeners (e.g. the availability grid's own script) that
        // the timezone changed, since a programmatic `.value` assignment
        // does not fire a native "change" event.
        timezoneSelect.dispatchEvent(new Event("change", { bubbles: true }));
    }
});

function getBrowserUtcOffsetLabel() {
    const offsetMinutes = -new Date().getTimezoneOffset();
    const sign = offsetMinutes >= 0 ? "+" : "-";
    const abs = Math.abs(offsetMinutes);
    const hours = String(Math.floor(abs / 60)).padStart(2, "0");
    const minutes = String(abs % 60).padStart(2, "0");
    return `UTC${sign}${hours}:${minutes}`;
}
